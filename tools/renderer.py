#!/usr/bin/env python3
"""
Chowdown Renderer — Module 5
Fills template slots from content-brief.json and asset-manifest.json.
Processes {% include %}, {% for %}, {% if %}, {% elif %}, {% else %}, {% endif %}.

Usage:
    python3 tools/renderer.py --dir output/CLIENT/

Reads: config.json, content-brief.json, asset-manifest.json from output dir.
Output: all index.html files filled with content.
"""

import argparse
import json
import os
import re
from datetime import datetime
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

REVIEWS_WORKER_URL = 'https://reviews.chowdown.workers.dev/api/reviews'
TEMPLATE_DIR = Path(__file__).parent.parent / 'template'


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

    # Build the global context available to all pages
    ctx = build_context(config, output_dir)

    html_files = sorted(output_dir.rglob('index.html'))
    print(f'Found {len(html_files)} pages to render\n')

    contamination_warnings = []

    for html_path in html_files:
        page_path = '/' + str(html_path.parent.relative_to(output_dir)).replace('.', '') + '/'
        page_path = re.sub(r'/+', '/', page_path)

        print(f'Rendering: {page_path}')

        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        page_brief = brief.get('pages', {}).get(page_path, {})

        # Build page-level context
        page_ctx = dict(ctx)
        page_ctx['page'] = {
            'path': page_path,
            'title': page_brief.get('title', derive_page_name(page_path)),
            'breadcrumbs': build_breadcrumbs(page_path),
            'hero_image': config.get('hero', {}).get('image_url', ''),
        }
        page_ctx['page_sections'] = []

        # Pass 1: Process includes (3 passes for nesting)
        for _ in range(3):
            prev = html
            html = process_includes(html)
            if html == prev:
                break

        # Pass 2-6: Process control structures and slots (multiple passes)
        for _ in range(8):
            prev = html
            html = process_conditionals(html, page_ctx)
            html = process_for_loops(html, page_ctx)
            html = fill_slots(html, page_ctx)
            if html == prev:
                break

        # Pass 7: Fill asset paths from manifest
        html = fill_asset_paths(html, manifest)

        # Pass 8: Clean up any remaining template tags
        html = cleanup_remaining_tags(html)

        # Check contamination
        warnings = check_contamination(html, page_path)
        contamination_warnings.extend(warnings)

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

    if contamination_warnings:
        print(f'\n!!! CONTAMINATION WARNINGS ({len(contamination_warnings)}) !!!')
        for w in contamination_warnings:
            print(f'  {w["page"]}: {w["url"]} (contains "{w["slug"]}")')
    else:
        print('\nNo contamination detected.')

    print(f'\n=== Render complete: {len(html_files)} pages ===\n')


def build_context(config, output_dir):
    """Build the global template context from config and generated assets."""
    brand = config.get('brand', {})

    # Generate font-face CSS
    font_face_css = generate_font_face_css(config)

    # Read icons.css for inlining
    icons_path = TEMPLATE_DIR / 'assets' / 'css' / 'icons.css'
    icons_css = ''
    if icons_path.exists():
        with open(icons_path, 'r') as f:
            icons_css = f.read()

    # Font preload tags
    font_preload_tags = generate_font_preloads(config)

    # Critical CSS (inline above-fold styles)
    critical_css = generate_critical_css(config)

    return {
        'config': config,
        'build_year': str(datetime.now().year),
        'font_face_css': font_face_css,
        'icons_css': icons_css,
        'font_preload_tags': font_preload_tags,
        'critical_css': critical_css,
        'REVIEWS_WORKER_URL': REVIEWS_WORKER_URL,
        'seo': {
            'title': '',
            'description': '',
            'og_title': '',
            'og_description': '',
            'twitter_title': '',
            'twitter_description': '',
        },
    }


def process_includes(html):
    """Replace {% include "path" %} with file contents."""
    def replace_include(m):
        path = m.group(1)
        fpath = TEMPLATE_DIR / path
        if fpath.exists():
            with open(fpath, 'r') as f:
                return f.read()
        return f'<!-- INCLUDE NOT FOUND: {path} -->'

    return re.sub(r'\{%\s*include\s+"([^"]+)"\s*%\}', replace_include, html)


def process_conditionals(html, ctx):
    """Process {% if %}...{% elif %}...{% else %}...{% endif %} blocks."""
    # Match the outermost if/endif pairs
    pattern = re.compile(
        r'\{%\s*if\s+(.+?)\s*%\}'
        r'(.*?)'
        r'\{%\s*endif\s*%\}',
        re.DOTALL
    )

    def replace_block(m):
        full_expr = m.group(1)
        body = m.group(2)

        # Split body into if/elif/else branches
        branches = []
        # First branch: the if condition
        parts = re.split(r'\{%\s*elif\s+(.+?)\s*%\}|\{%\s*else\s*%\}', body)

        # parts[0] is the if-body
        # Then alternating: elif-condition, elif-body, ..., else-body (if present)
        conditions = [full_expr]
        bodies = [parts[0]]

        i = 1
        while i < len(parts):
            if parts[i] is not None:
                # This is an elif condition
                conditions.append(parts[i])
                bodies.append(parts[i + 1] if i + 1 < len(parts) else '')
                i += 2
            else:
                # This is the else (condition is None)
                bodies.append(parts[i + 1] if i + 1 < len(parts) else '')
                conditions.append(None)  # else has no condition
                i += 2

        # Evaluate branches in order
        for j, cond in enumerate(conditions):
            if cond is None:
                # else branch — always true if reached
                return bodies[j] if j < len(bodies) else ''
            if eval_expr(cond, ctx):
                return bodies[j] if j < len(bodies) else ''

        return ''  # No branch matched, no else

    return pattern.sub(replace_block, html)


def process_for_loops(html, ctx):
    """Process {% for item in collection %} ... {% endfor %} blocks."""
    pattern = re.compile(
        r'\{%\s*for\s+(\w+)\s+in\s+(.+?)\s*%\}(.*?)\{%\s*endfor\s*%\}',
        re.DOTALL
    )

    def replace_loop(m):
        var_name = m.group(1)
        collection_path = m.group(2).strip()
        body = m.group(3)

        items = resolve(collection_path, ctx)
        if not items or not isinstance(items, list):
            return ''

        parts = []
        for idx, item in enumerate(items):
            rendered = body

            # Loop metadata
            is_first = (idx == 0)

            # Handle {% if loop.first %} ... {% endif %}
            rendered = re.sub(
                r'\{%\s*if\s+loop\.first\s*%\}(.*?)\{%\s*endif\s*%\}',
                lambda mm: mm.group(1) if is_first else '',
                rendered, flags=re.DOTALL
            )

            rendered = rendered.replace('{{ loop.index0 }}', str(idx))
            rendered = rendered.replace('{{ loop.index }}', str(idx + 1))

            # Replace item fields
            if isinstance(item, dict):
                for key, val in flatten_dict(item, var_name):
                    rendered = rendered.replace(f'{{{{ {key} }}}}', str(val) if val is not None else '')
            elif isinstance(item, str):
                rendered = rendered.replace(f'{{{{ {var_name} }}}}', item)

            # Handle range() in nested loops (for star ratings)
            rendered = re.sub(
                r'\{%\s*for\s+\w+\s+in\s+range\((\w+\.\w+)\)\s*%\}(.*?)\{%\s*endfor\s*%\}',
                lambda mm: handle_range_loop(mm, item, var_name),
                rendered, flags=re.DOTALL
            )

            parts.append(rendered)

        return ''.join(parts)

    return pattern.sub(replace_loop, html)


def handle_range_loop(m, item, parent_var):
    """Handle {% for i in range(review.rating) %} style loops."""
    field_path = m.group(1)
    body = m.group(2)
    field = field_path.split('.')[-1]
    count = 0
    if isinstance(item, dict):
        count = int(item.get(field, 0) or 0)
    return body * count


def fill_slots(html, ctx):
    """Replace {{ path.to.value }} with resolved values."""
    def replace_slot(m):
        path = m.group(1).strip()
        val = resolve(path, ctx)
        if val is None:
            return m.group(0)  # Keep unresolved for later passes
        if isinstance(val, (list, dict)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return re.sub(r'\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}', replace_slot, html)


def fill_asset_paths(html, manifest):
    """Replace asset references using manifest — character for character."""
    for key, info in manifest.items():
        if isinstance(info, dict):
            orig = info.get('original_url', '')
            local = info.get('local_path', '')
            if orig and local and orig in html:
                html = html.replace(orig, local)
    return html


def cleanup_remaining_tags(html):
    """Remove any remaining template tags that couldn't be resolved."""
    # Remove empty {% if %}{% endif %} blocks
    html = re.sub(r'\{%\s*if\s+[^%]*%\}\s*\{%\s*endif\s*%\}', '', html)

    # Remove remaining {% %} control tags
    html = re.sub(r'\{%[^%]*%\}', '', html)

    # Replace remaining {{ }} value tags with empty string
    # But preserve HTML comments and <!-- SLOT: --> markers
    html = re.sub(r'\{\{\s*[a-zA-Z0-9_.]+\s*\}\}', '', html)

    # Clean up excessive blank lines
    html = re.sub(r'\n{3,}', '\n\n', html)

    return html


def eval_expr(expr, ctx):
    """Evaluate a template expression to a boolean."""
    expr = expr.strip()

    # Handle == comparison
    if '==' in expr:
        left, right = expr.split('==', 1)
        left_val = str(resolve(left.strip(), ctx) or '')
        right_val = right.strip().strip('"').strip("'")
        return left_val == right_val

    # Handle 'or'
    if ' or ' in expr:
        return any(eval_expr(p.strip(), ctx) for p in expr.split(' or '))

    # Handle 'and'
    if ' and ' in expr:
        return all(eval_expr(p.strip(), ctx) for p in expr.split(' and '))

    # Handle 'not'
    if expr.startswith('not '):
        return not eval_expr(expr[4:], ctx)

    # Simple truthy check
    val = resolve(expr, ctx)
    if isinstance(val, list):
        return len(val) > 0
    if isinstance(val, dict):
        return len(val) > 0
    return bool(val)


def resolve(path, ctx):
    """Resolve a dotted path against the context. Tries multiple prefixes."""
    # Direct lookup
    val = resolve_nested(ctx, path)
    if val is not None:
        return val

    # Try with config. prefix stripped if present
    if path.startswith('config.'):
        return resolve_nested(ctx.get('config', {}), path[7:])

    # Try as config path
    val = resolve_nested(ctx.get('config', {}), path)
    if val is not None:
        return val

    return None


def resolve_nested(obj, dotted_path):
    """Resolve a.b.c on a nested dict."""
    if not obj or not dotted_path:
        return None
    keys = dotted_path.split('.')
    current = obj
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def flatten_dict(d, prefix):
    """Yield (dotted_key, value) pairs for template substitution."""
    for key, val in d.items():
        full_key = f'{prefix}.{key}'
        if isinstance(val, dict):
            yield from flatten_dict(val, full_key)
        elif isinstance(val, list):
            yield (full_key, json.dumps(val, ensure_ascii=False))
        else:
            yield (full_key, val)


def build_breadcrumbs(page_path):
    """Build breadcrumb array from path."""
    if page_path == '/':
        return []
    parts = [p for p in page_path.strip('/').split('/') if p]
    crumbs = []
    for i, part in enumerate(parts):
        is_last = (i == len(parts) - 1)
        crumbs.append({
            'label': part.replace('-', ' ').title(),
            'url': None if is_last else '/' + '/'.join(parts[:i + 1]) + '/',
        })
    return crumbs


def derive_page_name(page_path):
    if page_path == '/':
        return 'Home'
    parts = page_path.strip('/').split('/')
    return parts[-1].replace('-', ' ').title()


def check_contamination(html, page_path):
    """Flag any URL containing known client slugs."""
    warnings = []
    urls = re.findall(r'https?://[^\s"\'<>]+', html)
    for url in urls:
        for slug in KNOWN_CLIENT_SLUGS:
            if slug in url.lower():
                warnings.append({'page': page_path, 'url': url, 'slug': slug})
    return warnings


def generate_font_face_css(config):
    """Generate @font-face declarations."""
    brand = config.get('brand', {})
    fonts = []
    heading = brand.get('heading_font', 'Libre Baskerville')
    body = brand.get('body_font', 'Lato')
    script = brand.get('script_font', '')

    slug_h = font_slug(heading)
    fonts.append(ff(heading, '400', f'/assets/fonts/{slug_h}-regular.woff2'))
    fonts.append(ff(heading, '700', f'/assets/fonts/{slug_h}-bold.woff2'))

    slug_b = font_slug(body)
    fonts.append(ff(body, '300', f'/assets/fonts/{slug_b}-light.woff2'))
    fonts.append(ff(body, '400', f'/assets/fonts/{slug_b}-regular.woff2'))
    fonts.append(ff(body, '700', f'/assets/fonts/{slug_b}-bold.woff2'))

    if script:
        slug_s = font_slug(script)
        fonts.append(ff(script, '400', f'/assets/fonts/{slug_s}-regular.woff2'))

    return '\n'.join(fonts)


def ff(family, weight, src):
    return (f"@font-face {{ font-family: '{family}'; font-style: normal; "
            f"font-weight: {weight}; font-display: swap; "
            f"src: url('{src}') format('woff2'); }}")


def font_slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def generate_font_preloads(config):
    brand = config.get('brand', {})
    tags = []
    for font in [brand.get('heading_font', ''), brand.get('body_font', '')]:
        if font:
            slug = font_slug(font)
            tags.append(f'<link rel="preload" as="font" type="font/woff2" href="/assets/fonts/{slug}-regular.woff2" crossorigin>')
    script = brand.get('script_font', '')
    if script:
        slug = font_slug(script)
        tags.append(f'<link rel="preload" as="font" type="font/woff2" href="/assets/fonts/{slug}-regular.woff2" crossorigin>')
    return '\n  '.join(tags)


def generate_critical_css(config):
    """Generate minimal critical above-fold CSS."""
    brand = config.get('brand', {})
    primary = brand.get('primary_color', '#8B1A1A')
    bg = brand.get('background_color', '#1a1a1a')
    text = brand.get('text_color', '#f5f5f5')
    heading = brand.get('heading_font', 'Libre Baskerville')
    body_font = brand.get('body_font', 'Lato')

    return (
        f"*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}"
        f"body{{font-family:'{body_font}',system-ui,sans-serif;color:{text};background:{bg};overflow-x:hidden}}"
        f".site-header{{position:fixed;top:0;left:0;width:100%;z-index:1000;transition:background .3s}}"
        f".site-header.scrolled{{background:rgba(0,0,0,.95);box-shadow:0 2px 10px rgba(0,0,0,.3)}}"
        f".navbar{{width:100%;padding:10px 0}}"
        f".nav-container{{display:flex;align-items:center;justify-content:center;width:90%;max-width:1280px;margin:0 auto;position:relative}}"
        f".nav-logo img{{height:100px;width:auto}}"
        f".nav-left,.nav-right{{display:flex;list-style:none;gap:20px;align-items:center}}"
        f".nav-left a,.nav-right a{{font-family:'{heading}',serif;text-transform:uppercase;color:#fff;text-decoration:none;font-size:clamp(.875rem,.875rem + ((1vw - .2rem)*.542),1.2rem)}}"
        f".hero{{position:relative;width:100%;height:85vh;min-height:500px;overflow:hidden}}"
        f".hero-image,.hero-video{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}"
        f".hero-overlay{{position:absolute;inset:0;background:rgba(0,0,0,.5)}}"
        f".container{{width:90%;max-width:1280px;margin:0 auto}}"
        f".btn{{display:inline-block;font-family:'{heading}',serif;text-transform:uppercase;font-weight:700;"
        f"background:{primary};color:#fff;border:2px solid {primary};padding:10px 30px;border-radius:10px;text-decoration:none}}"
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chowdown Renderer — Module 5')
    parser.add_argument('--dir', required=True, help='Path to client output directory')
    args = parser.parse_args()
    render(args.dir)
