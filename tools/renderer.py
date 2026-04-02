#!/usr/bin/env python3
"""
Chowdown Renderer — Module 5
Renders all pages using Jinja2 template engine.

Usage:
    python3 tools/renderer.py --dir output/CLIENT/

Reads: config.json, content-brief.json, asset-manifest.json, page-tree.json from output dir.
Output: all index.html files rendered with Jinja2.
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / 'template'
REVIEWS_WORKER_URL = 'https://reviews.chowdown.workers.dev/api/reviews'

KNOWN_CLIENT_SLUGS = [
    'liberty-collective',
    'westfield-collective',
]


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def render(output_dir):
    output_dir = Path(output_dir).resolve()
    config = load_json(output_dir / 'config.json')
    brief = load_json(output_dir / 'content-brief.json')
    manifest = load_json(output_dir / 'asset-manifest.json')
    page_tree = load_json(output_dir / 'page-tree.json')

    if not config:
        print('ERROR: config.json not found')
        return

    print(f'\n=== Rendering: {config["client"]["name"]} ===')

    # Set up Jinja2
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )

    # Build shared context
    ctx = build_context(config, brief)

    # Get approved pages
    pages = page_tree.get('pages', [])
    approved = [p for p in pages if p.get('status') in ('approved', 'include')]
    contamination_warnings = []

    for page in approved:
        page_path = page.get('path', '/')
        page_type = page.get('type', 'subpage')
        page_title = page.get('title', derive_page_name(page_path))

        # Choose template
        if page_path == '/':
            template_name = 'pages/home.html'
        elif page_type == 'vendor':
            template_name = 'pages/vendor.html'
        else:
            template_name = 'pages/subpage.html'

        print(f'  {page_path} -> {template_name}')

        # Page-level context
        page_brief = brief.get('pages', {}).get(page_path, {})
        page_ctx = dict(ctx)
        page_ctx['page'] = {
            'path': page_path,
            'title': page_title,
            'breadcrumbs': build_breadcrumbs(page_path),
            'hero_image': config.get('hero', {}).get('image_url', ''),
        }
        page_ctx['page_sections'] = []
        page_ctx['seo'] = {
            'title': '',
            'description': '',
            'og_title': '',
            'og_description': '',
            'twitter_title': '',
            'twitter_description': '',
        }

        # Render with Jinja2
        template = env.get_template(template_name)
        html = template.render(**page_ctx)

        # Write to output
        if page_path == '/':
            dest = output_dir / 'index.html'
        else:
            dest = output_dir / page_path.strip('/') / 'index.html'

        os.makedirs(dest.parent, exist_ok=True)
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(html)

        # Check contamination
        warnings = check_contamination(html, page_path)
        contamination_warnings.extend(warnings)

    if contamination_warnings:
        print(f'\n!!! CONTAMINATION ({len(contamination_warnings)}) !!!')
        for w in contamination_warnings:
            print(f'  {w["page"]}: {w["url"]} (contains "{w["slug"]}")')
    else:
        print('\nNo contamination detected.')

    print(f'\n=== Render complete: {len(approved)} pages ===\n')


def build_context(config, brief):
    """Build the global Jinja2 context."""
    icons_path = TEMPLATE_DIR / 'assets' / 'css' / 'icons.css'
    icons_css = icons_path.read_text() if icons_path.exists() else ''

    return {
        'config': config,
        'build_year': str(datetime.now().year),
        'font_face_css': generate_font_face_css(config),
        'icons_css': icons_css,
        'font_preload_tags': generate_font_preloads(config),
        'critical_css': generate_critical_css(config),
        'schema_blocks': '',
        'REVIEWS_WORKER_URL': REVIEWS_WORKER_URL,
    }


def build_breadcrumbs(page_path):
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
    return page_path.strip('/').split('/')[-1].replace('-', ' ').title()


def check_contamination(html, page_path):
    warnings = []
    urls = re.findall(r'https?://[^\s"\'<>]+', html)
    for url in urls:
        for slug in KNOWN_CLIENT_SLUGS:
            if slug in url.lower():
                warnings.append({'page': page_path, 'url': url, 'slug': slug})
    return warnings


def generate_font_face_css(config):
    brand = config.get('brand', {})
    fonts = []
    for name, weights in [
        (brand.get('heading_font', 'Libre Baskerville'), ['400', '700']),
        (brand.get('body_font', 'Lato'), ['300', '400', '700']),
    ]:
        slug = font_slug(name)
        for w in weights:
            label = {'300': 'light', '400': 'regular', '700': 'bold'}[w]
            fonts.append(
                f"@font-face {{ font-family: '{name}'; font-style: normal; "
                f"font-weight: {w}; font-display: swap; "
                f"src: url('/assets/fonts/{slug}-{label}.woff2') format('woff2'); }}"
            )
    script = brand.get('script_font', '')
    if script:
        slug = font_slug(script)
        fonts.append(
            f"@font-face {{ font-family: '{script}'; font-style: normal; "
            f"font-weight: 400; font-display: swap; "
            f"src: url('/assets/fonts/{slug}-regular.woff2') format('woff2'); }}"
        )
    return '\n'.join(fonts)


def generate_font_preloads(config):
    brand = config.get('brand', {})
    tags = []
    for name in [brand.get('heading_font', ''), brand.get('body_font', ''), brand.get('script_font', '')]:
        if name:
            slug = font_slug(name)
            tags.append(f'<link rel="preload" as="font" type="font/woff2" href="/assets/fonts/{slug}-regular.woff2" crossorigin>')
    return '\n  '.join(tags)


def generate_critical_css(config):
    brand = config.get('brand', {})
    p = brand.get('primary_color', '#8B1A1A')
    bg = brand.get('background_color', '#1a1a1a')
    tx = brand.get('text_color', '#f5f5f5')
    hf = brand.get('heading_font', 'Libre Baskerville')
    bf = brand.get('body_font', 'Lato')
    return (
        f"*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}"
        f"body{{font-family:'{bf}',system-ui,sans-serif;color:{tx};background:{bg};overflow-x:hidden}}"
        f".site-header{{position:fixed;top:0;left:0;width:100%;z-index:1000;transition:background .3s}}"
        f".site-header.scrolled{{background:rgba(0,0,0,.95);box-shadow:0 2px 10px rgba(0,0,0,.3)}}"
        f".navbar{{width:100%;padding:10px 0}}"
        f".nav-container{{display:flex;align-items:center;justify-content:center;width:90%;max-width:1280px;margin:0 auto;position:relative}}"
        f".nav-logo img{{height:100px;width:auto}}"
        f".nav-left,.nav-right{{display:flex;list-style:none;gap:20px;align-items:center}}"
        f".nav-left a,.nav-right a{{font-family:'{hf}',serif;text-transform:uppercase;color:#fff;text-decoration:none}}"
        f".hero{{position:relative;width:100%;height:85vh;min-height:500px;overflow:hidden}}"
        f".hero-image,.hero-video{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}"
        f".hero-overlay{{position:absolute;inset:0;background:rgba(0,0,0,.5)}}"
        f".container{{width:90%;max-width:1280px;margin:0 auto}}"
        f".btn{{display:inline-block;font-family:'{hf}',serif;text-transform:uppercase;font-weight:700;"
        f"background:{p};color:#fff;border:2px solid {p};padding:10px 30px;border-radius:10px;text-decoration:none}}"
    )


def font_slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chowdown Renderer — Module 5 (Jinja2)')
    parser.add_argument('--dir', required=True, help='Path to client output directory')
    args = parser.parse_args()
    render(args.dir)
