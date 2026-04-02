#!/usr/bin/env python3
"""
Chowdown Scaffold — Module 4
Reads config.json and page-tree.json, creates complete folder structure
with HTML shells, CSS variables, static assets, and infrastructure files.

Usage:
    python3 tools/scaffold.py --config output/CLIENT/config.json --pages output/CLIENT/page-tree.json

Output: complete folder structure in output/CLIENT/ ready for renderer.py
"""

import argparse
import json
import os
import shutil
import re
from datetime import datetime
from pathlib import Path

# Global constants — same for all clients
REVIEWS_WORKER_URL = 'https://reviews.chowdown.workers.dev/api/reviews'
TEMPLATE_DIR = Path(__file__).parent.parent / 'template'
BUILD_YEAR = str(datetime.now().year)


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  wrote: {path}')


def scaffold(config_path, pages_path):
    config = load_json(config_path)
    page_tree = load_json(pages_path)
    slug = config['client']['slug']
    output_dir = Path('output') / slug

    print(f'\n=== Scaffolding: {config["client"]["name"]} ===')
    print(f'Output: {output_dir}')

    # 1. Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # 2. Copy template assets
    copy_template_assets(output_dir)

    # 3. Inject CSS variables from config
    inject_css_variables(output_dir, config)

    # 4. Generate @font-face declarations
    font_face_css = generate_font_face_css(config)

    # 5. Read icons.css for inlining
    icons_css = read_template_file('assets/css/icons.css')

    # 6. Generate font preload tags
    font_preload_tags = generate_font_preloads(config)

    # 7. Build context shared across all pages
    context = {
        'config': config,
        'build_year': BUILD_YEAR,
        'font_face_css': font_face_css,
        'icons_css': icons_css,
        'font_preload_tags': font_preload_tags,
        'REVIEWS_WORKER_URL': REVIEWS_WORKER_URL,
    }

    # 8. Create page folders with shells
    approved_pages = get_approved_pages(page_tree)
    for page in approved_pages:
        create_page_shell(output_dir, page, config, context)

    # 9. Write infrastructure files
    write_redirects(output_dir, page_tree)
    write_headers(output_dir)
    write_robots_txt(output_dir, config)

    # 10. Copy config into output for renderer/schema/seo to read
    shutil.copy2(config_path, output_dir / 'config.json')

    print(f'\n=== Scaffold complete: {len(approved_pages)} pages ===\n')
    return output_dir


def copy_template_assets(output_dir):
    """Copy CSS, JS, icons from template into client output."""
    print('\nCopying template assets...')
    assets_src = TEMPLATE_DIR / 'assets'
    assets_dst = output_dir / 'assets'

    for subdir in ['css', 'js']:
        src = assets_src / subdir
        dst = assets_dst / subdir
        if src.exists():
            os.makedirs(dst, exist_ok=True)
            for f in src.iterdir():
                if f.is_file():
                    shutil.copy2(f, dst / f.name)
                    print(f'  copied: assets/{subdir}/{f.name}')

    # Ensure images/home directory exists for asset pipeline
    os.makedirs(output_dir / 'assets' / 'images' / 'home', exist_ok=True)
    # Ensure fonts directory exists
    os.makedirs(output_dir / 'assets' / 'fonts', exist_ok=True)


def inject_css_variables(output_dir, config):
    """Overwrite :root CSS variables in base.css with config.json brand values."""
    print('\nInjecting CSS variables...')
    base_css_path = output_dir / 'assets' / 'css' / 'base.css'
    if not base_css_path.exists():
        print('  WARNING: base.css not found, skipping variable injection')
        return

    with open(base_css_path, 'r', encoding='utf-8') as f:
        css = f.read()

    brand = config.get('brand', {})
    replacements = {
        '--color-primary': brand.get('primary_color', '#8B1A1A'),
        '--color-secondary': brand.get('secondary_color', '#C9A96E'),
        '--color-accent': brand.get('accent_color', '#D4AF37'),
        '--color-bg': brand.get('background_color', '#1a1a1a'),
        '--color-text': brand.get('text_color', '#f5f5f5'),
    }

    # Compute derived colors from brand
    bg = brand.get('background_color', '#1a1a1a')
    text = brand.get('text_color', '#f5f5f5')
    is_dark_bg = is_dark_color(bg)

    derived = {
        '--color-bg-alt': lighten_hex(bg, 0.05) if is_dark_bg else darken_hex(bg, 0.03),
        '--color-bg-light': '#f5f5f5' if is_dark_bg else '#ffffff',
        '--color-text-dark': '#333333',
        '--color-text-muted': '#999999',
        '--color-text-on-light': '#333333',
        '--color-border': '#333333' if is_dark_bg else '#e0e0e0',
        '--color-border-light': '#e0e0e0',
    }
    replacements.update(derived)

    # Font families
    heading = brand.get('heading_font', 'Libre Baskerville')
    body = brand.get('body_font', 'Lato')
    script = brand.get('script_font', '')
    heading_stack = f"'{heading}', Georgia, serif" if heading else "'Libre Baskerville', Georgia, serif"
    body_stack = f"'{body}', system-ui, sans-serif" if body else "'Lato', system-ui, sans-serif"
    script_stack = f"'{script}', cursive" if script else "'Alex Brush', cursive"
    replacements['--font-heading'] = heading_stack
    replacements['--font-body'] = body_stack
    replacements['--font-script'] = script_stack

    for var_name, value in replacements.items():
        # Replace the value after the variable name in :root
        pattern = re.compile(
            rf'({re.escape(var_name)}\s*:\s*)([^;]+)(;)',
            re.MULTILINE
        )
        if var_name.startswith('--font-'):
            css = pattern.sub(rf'\g<1>{value}\3', css, count=1)
        else:
            css = pattern.sub(rf'\g<1>{value}\3', css, count=1)

    with open(base_css_path, 'w', encoding='utf-8') as f:
        f.write(css)
    print(f'  injected {len(replacements)} CSS variables')


def generate_font_face_css(config):
    """Generate @font-face declarations from config fonts."""
    brand = config.get('brand', {})
    fonts = []

    heading = brand.get('heading_font', 'Libre Baskerville')
    body = brand.get('body_font', 'Lato')
    script = brand.get('script_font', '')

    # Heading font: 400 + 700
    slug = font_slug(heading)
    fonts.append(font_face(heading, 'normal', '400', f'/assets/fonts/{slug}-regular.woff2'))
    fonts.append(font_face(heading, 'normal', '700', f'/assets/fonts/{slug}-bold.woff2'))

    # Body font: 300 + 400 + 700
    slug = font_slug(body)
    fonts.append(font_face(body, 'normal', '300', f'/assets/fonts/{slug}-light.woff2'))
    fonts.append(font_face(body, 'normal', '400', f'/assets/fonts/{slug}-regular.woff2'))
    fonts.append(font_face(body, 'normal', '700', f'/assets/fonts/{slug}-bold.woff2'))

    # Script font: 400 only
    if script:
        slug = font_slug(script)
        fonts.append(font_face(script, 'normal', '400', f'/assets/fonts/{slug}-regular.woff2'))

    return '\n'.join(fonts)


def generate_font_preloads(config):
    """Generate <link rel=preload> tags for primary font files."""
    brand = config.get('brand', {})
    tags = []
    for font_name in [brand.get('heading_font', ''), brand.get('body_font', '')]:
        if font_name:
            slug = font_slug(font_name)
            tags.append(
                f'<link rel="preload" as="font" type="font/woff2" '
                f'href="/assets/fonts/{slug}-regular.woff2" crossorigin>'
            )
    script = brand.get('script_font', '')
    if script:
        slug = font_slug(script)
        tags.append(
            f'<link rel="preload" as="font" type="font/woff2" '
            f'href="/assets/fonts/{slug}-regular.woff2" crossorigin>'
        )
    return '\n  '.join(tags)


def font_face(family, style, weight, src):
    return (
        f"@font-face {{\n"
        f"  font-family: '{family}';\n"
        f"  font-style: {style};\n"
        f"  font-weight: {weight};\n"
        f"  font-display: swap;\n"
        f"  src: url('{src}') format('woff2');\n"
        f"}}"
    )


def font_slug(name):
    """Convert font name to file slug: 'Libre Baskerville' -> 'libre-baskerville'"""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def get_approved_pages(page_tree):
    """Extract approved pages from page-tree.json."""
    pages = page_tree.get('pages', [])
    return [p for p in pages if p.get('status') in ('approved', 'include')]


def create_page_shell(output_dir, page, config, context):
    """Create folder and copy correct shell for a page."""
    path = page.get('path', '/')
    page_type = page.get('type', 'subpage')

    # Determine which shell to use
    if path == '/' or path == '/index.html':
        shell_name = 'home.html'
        folder = output_dir
    elif page_type == 'vendor':
        shell_name = 'vendor.html'
        folder = output_dir / path.strip('/')
    else:
        shell_name = 'subpage.html'
        folder = output_dir / path.strip('/')

    shell_path = TEMPLATE_DIR / 'pages' / shell_name
    if not shell_path.exists():
        print(f'  WARNING: shell {shell_name} not found for {path}')
        return

    os.makedirs(folder, exist_ok=True)
    dest = folder / 'index.html'
    shutil.copy2(shell_path, dest)
    print(f'  shell: {path} -> {shell_name}')


def write_redirects(output_dir, page_tree):
    """Write _redirects file from excluded pages."""
    print('\nWriting _redirects...')
    excluded = page_tree.get('build_decisions', {}).get('excluded_pages', [])
    lines = []
    for exc in excluded:
        source = exc.get('path', '')
        target = exc.get('redirect_to', '/')
        if source:
            lines.append(f'{source}  {target}  301')

    content = '\n'.join(lines) + '\n' if lines else '# No redirects\n'
    write_file(output_dir / '_redirects', content)


def write_headers(output_dir):
    """Write _headers file with Cloudflare Pages cache rules."""
    print('Writing _headers...')
    content = (
        '/assets/*\n'
        '  Cache-Control: public, max-age=31536000, immutable\n'
        '\n'
        '/*\n'
        '  X-Content-Type-Options: nosniff\n'
        '  X-Frame-Options: DENY\n'
        '  Referrer-Policy: strict-origin-when-cross-origin\n'
    )
    write_file(output_dir / '_headers', content)


def write_robots_txt(output_dir, config):
    """Write robots.txt with sitemap reference."""
    print('Writing robots.txt...')
    domain = config['client']['domain']
    content = f'User-agent: *\nAllow: /\n\nSitemap: {domain}/sitemap.xml\n'
    write_file(output_dir / 'robots.txt', content)


def read_template_file(relative_path):
    """Read a file from the template directory."""
    path = TEMPLATE_DIR / relative_path
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ''


def is_dark_color(hex_color):
    """Check if a hex color is dark (luminance < 0.5)."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5


def lighten_hex(hex_color, amount):
    """Lighten a hex color by a fraction."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f'#{r:02x}{g:02x}{b:02x}'


def darken_hex(hex_color, amount):
    """Darken a hex color by a fraction."""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = max(0, int(r * (1 - amount)))
    g = max(0, int(g * (1 - amount)))
    b = max(0, int(b * (1 - amount)))
    return f'#{r:02x}{g:02x}{b:02x}'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chowdown Scaffold — Module 4')
    parser.add_argument('--config', required=True, help='Path to config.json')
    parser.add_argument('--pages', required=True, help='Path to page-tree.json')
    args = parser.parse_args()
    scaffold(args.config, args.pages)
