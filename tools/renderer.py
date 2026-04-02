#!/usr/bin/env python3
"""
Chowdown Renderer — Module 5
Fills template slots from content-brief.json and asset-manifest.json.
Processes {% include %}, {% for %}, {% if %} directives.

Usage:
    python3 tools/renderer.py --dir output/CLIENT/

Reads: config.json, content-brief.json, asset-manifest.json from output dir.
Output: all index.html files filled with content.
"""

import argparse
import json
import os
import re
from pathlib import Path

# Simple vs complex section threshold (defined in code, not interpretation)
# Simple: max 3 CSS properties, no grid, no carousel, no multi-column
COMPLEX_CSS_INDICATORS = {'grid', 'carousel', 'multi-column', 'columns', 'flex-wrap', 'slideshow'}
MAX_SIMPLE_CSS_PROPS = 3

# Known client slugs for contamination check
KNOWN_CLIENT_SLUGS = [
    'liberty-collective',
    'westfield-collective',
]

# Global constant
REVIEWS_WORKER_URL = 'https://reviews.chowdown.workers.dev/api/reviews'


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def render(output_dir):
    output_dir = Path(output_dir)
    config = load_json(output_dir / 'config.json')
    brief = load_json(output_dir / 'content-brief.json')
    manifest = load_json(output_dir / 'asset-manifest.json')

    if not config:
        print('ERROR: config.json not found in output directory')
        return

    print(f'\n=== Rendering: {config["client"]["name"]} ===')

    # Find all index.html files
    html_files = list(output_dir.rglob('index.html'))
    print(f'Found {len(html_files)} pages to render\n')

    contamination_warnings = []

    for html_path in html_files:
        page_path = '/' + str(html_path.parent.relative_to(output_dir)) + '/'
        if page_path == '/./' or page_path == '//':
            page_path = '/'

        print(f'Rendering: {page_path}')

        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # Get page content from brief
        page_brief = brief.get('pages', {}).get(page_path, {})

        # Process includes
        html = process_includes(html, output_dir)

        # Process conditionals
        html = process_conditionals(html, config, page_brief)

        # Process loops
        html = process_loops(html, config, page_brief)

        # Fill config slots
        html = fill_config_slots(html, config)

        # Fill page-specific slots
        html = fill_page_slots(html, page_brief, page_path, config)

        # Fill asset paths from manifest (character for character)
        html = fill_asset_paths(html, manifest)

        # Insert content-pending markers
        html = mark_pending_content(html)

        # Check for external link contamination
        warnings = check_contamination(html, page_path)
        if warnings:
            contamination_warnings.extend(warnings)
            for w in warnings:
                html = html.replace(
                    w['url'],
                    f'{w["url"]}<!-- WARNING: possible contamination — contains "{w["slug"]}" -->'
                )

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

    # Report contamination
    if contamination_warnings:
        print(f'\n!!! CONTAMINATION WARNINGS ({len(contamination_warnings)}) !!!')
        for w in contamination_warnings:
            print(f'  {w["page"]}: {w["url"]} (contains "{w["slug"]}")')
    else:
        print('\nNo contamination detected.')

    print(f'\n=== Render complete: {len(html_files)} pages ===\n')


def process_includes(html, output_dir):
    """Process {% include "path" %} directives — inline component HTML."""
    template_dir = Path(__file__).parent.parent / 'template'

    def replace_include(match):
        path = match.group(1)
        include_path = template_dir / path
        if include_path.exists():
            with open(include_path, 'r', encoding='utf-8') as f:
                return f.read()
        return f'<!-- INCLUDE NOT FOUND: {path} -->'

    pattern = re.compile(r'\{%\s*include\s+"([^"]+)"\s*%\}')
    # Run multiple passes for nested includes
    for _ in range(3):
        new_html = pattern.sub(replace_include, html)
        if new_html == html:
            break
        html = new_html
    return html


def process_conditionals(html, config, page_brief):
    """Process {% if expr %} ... {% else %} ... {% endif %} blocks."""
    # Simple single-level conditionals
    pattern = re.compile(
        r'\{%\s*if\s+(.+?)\s*%\}(.*?)(?:\{%\s*else\s*%\}(.*?))?\{%\s*endif\s*%\}',
        re.DOTALL
    )

    def eval_condition(expr):
        expr = expr.strip()

        # Handle == comparison
        if '==' in expr:
            left, right = expr.split('==', 1)
            left_val = resolve_path(left.strip(), config, page_brief)
            right_val = right.strip().strip('"').strip("'")
            return str(left_val) == right_val

        # Handle 'or' operator
        if ' or ' in expr:
            parts = expr.split(' or ')
            return any(resolve_path(p.strip(), config, page_brief) for p in parts)

        # Handle 'not' operator
        if expr.startswith('not '):
            val = resolve_path(expr[4:].strip(), config, page_brief)
            return not val

        # Simple truthy check
        val = resolve_path(expr, config, page_brief)
        return bool(val)

    def replace_conditional(match):
        expr = match.group(1)
        if_block = match.group(2)
        else_block = match.group(3) or ''
        if eval_condition(expr):
            return if_block
        return else_block

    # Multiple passes for nested conditionals
    for _ in range(5):
        new_html = pattern.sub(replace_conditional, html)
        if new_html == html:
            break
        html = new_html
    return html


def process_loops(html, config, page_brief):
    """Process {% for item in collection %} ... {% endfor %} blocks."""
    pattern = re.compile(
        r'\{%\s*for\s+(\w+)\s+in\s+(.+?)\s*%\}(.*?)\{%\s*endfor\s*%\}',
        re.DOTALL
    )

    def replace_loop(match):
        var_name = match.group(1)
        collection_path = match.group(2).strip()
        body = match.group(3)

        items = resolve_path(collection_path, config, page_brief)
        if not items or not isinstance(items, list):
            return ''

        parts = []
        for idx, item in enumerate(items):
            rendered = body
            # Replace loop variables
            rendered = rendered.replace('{{ loop.first }}', str(idx == 0))
            rendered = rendered.replace('{{ loop.index0 }}', str(idx))
            rendered = rendered.replace('{{ loop.index }}', str(idx + 1))

            # Replace {{ var_name.field }} references
            if isinstance(item, dict):
                for key, val in item.items():
                    rendered = rendered.replace(f'{{{{ {var_name}.{key} }}}}', str(val) if val else '')
            elif isinstance(item, str):
                rendered = rendered.replace(f'{{{{ {var_name} }}}}', item)

            # Handle loop.first for class toggling
            if idx == 0:
                rendered = re.sub(
                    r'\{%\s*if\s+loop\.first\s*%\}(.*?)\{%\s*endif\s*%\}',
                    r'\1', rendered, flags=re.DOTALL
                )
            else:
                rendered = re.sub(
                    r'\{%\s*if\s+loop\.first\s*%\}(.*?)\{%\s*endif\s*%\}',
                    '', rendered, flags=re.DOTALL
                )

            parts.append(rendered)

        return ''.join(parts)

    # Multiple passes for nested loops
    for _ in range(3):
        new_html = pattern.sub(replace_loop, html)
        if new_html == html:
            break
        html = new_html
    return html


def fill_config_slots(html, config):
    """Replace {{ config.path.to.value }} with actual values."""
    pattern = re.compile(r'\{\{\s*config\.([a-zA-Z0-9_.]+)\s*\}\}')

    def replace_slot(match):
        path = match.group(1)
        val = resolve_nested(config, path)
        if val is None:
            return ''
        if isinstance(val, (list, dict)):
            return json.dumps(val)
        return str(val)

    return pattern.sub(replace_slot, html)


def fill_page_slots(html, page_brief, page_path, config):
    """Fill page-specific template variables."""
    # {{ page.title }}, {{ page.path }}, etc.
    html = html.replace('{{ page.title }}', page_brief.get('title', ''))
    html = html.replace('{{ page.path }}', page_path)

    # {{ build_year }}
    from datetime import datetime
    html = html.replace('{{ build_year }}', str(datetime.now().year))

    # {{ seo.* }} placeholders — seo.py fills these later
    # Leave them for now unless already set in brief
    return html


def fill_asset_paths(html, manifest):
    """Replace asset references using manifest — character for character copy."""
    for asset_key, asset_info in manifest.items():
        if isinstance(asset_info, dict):
            local_path = asset_info.get('local_path', '')
            if local_path:
                # Replace any reference to this asset's original URL with local path
                original_url = asset_info.get('original_url', '')
                if original_url and original_url in html:
                    html = html.replace(original_url, local_path)
    return html


def mark_pending_content(html):
    """Mark empty content slots and placeholder images."""
    # Find remaining unfilled {{ }} slots
    html = re.sub(
        r'\{\{\s*(?:seo\.[a-zA-Z_]+)\s*\}\}',
        lambda m: m.group(0),  # Keep SEO slots for seo.py
        html
    )
    # Mark other empty slots
    html = re.sub(
        r'\{\{\s*(?!seo\.)([a-zA-Z0-9_.]+)\s*\}\}',
        r'<!-- CONTENT PENDING: \1 -->',
        html
    )
    return html


def check_contamination(html, page_path):
    """Flag any URL containing known client slugs."""
    warnings = []
    url_pattern = re.compile(r'https?://[^\s"\'<>]+')
    urls = url_pattern.findall(html)

    for url in urls:
        for slug in KNOWN_CLIENT_SLUGS:
            if slug in url.lower():
                warnings.append({
                    'page': page_path,
                    'url': url,
                    'slug': slug,
                })
    return warnings


def classify_section(section_data):
    """
    Classify a content section as simple or complex.
    Simple: max 3 CSS properties, no grid, no carousel, no multi-column.
    Complex: everything else — flagged for human review.

    Returns: 'simple' or 'complex'
    """
    css_props = section_data.get('css_properties', [])
    css_text = ' '.join(str(p).lower() for p in css_props)

    # Check for complex indicators
    for indicator in COMPLEX_CSS_INDICATORS:
        if indicator in css_text:
            return 'complex'

    # Check property count
    if len(css_props) > MAX_SIMPLE_CSS_PROPS:
        return 'complex'

    return 'simple'


def resolve_path(expr, config, page_brief):
    """Resolve a dotted path like config.features.gallery to a value."""
    if expr.startswith('config.'):
        return resolve_nested(config, expr[7:])
    if expr.startswith('page.'):
        return resolve_nested(page_brief, expr[5:])
    return resolve_nested(config, expr) or resolve_nested(page_brief, expr)


def resolve_nested(obj, dotted_path):
    """Resolve a.b.c path on a nested dict."""
    keys = dotted_path.split('.')
    current = obj
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chowdown Renderer — Module 5')
    parser.add_argument('--dir', required=True, help='Path to client output directory')
    args = parser.parse_args()
    render(args.dir)
