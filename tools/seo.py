#!/usr/bin/env python3
"""
Chowdown SEO — Module 7
Writes unique titles, meta descriptions, OG tags, and generates sitemap.xml.

Usage:
    python3 tools/seo.py --dir output/CLIENT/

Reads: config.json, content-brief.json from output dir.
Output: all index.html files with SEO metadata filled, sitemap.xml generated.
"""

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def seo(output_dir):
    output_dir = Path(output_dir)
    config = load_json(output_dir / 'config.json')
    brief = load_json(output_dir / 'content-brief.json')

    if not config:
        print('ERROR: config.json not found')
        return

    print(f'\n=== SEO: {config["client"]["name"]} ===')

    domain = config['client']['domain']
    name = config['client']['name']
    city = config['contact']['city']
    state = config['contact']['state']
    location = f'{city}, {state}'
    og_image = config['brand'].get('og_image', '/assets/images/home/og-share.jpg')

    # Find all pages
    html_files = sorted(output_dir.rglob('index.html'))
    print(f'Processing {len(html_files)} pages\n')

    sitemap_entries = []
    validation_errors = []

    for html_path in html_files:
        page_path = '/' + str(html_path.parent.relative_to(output_dir)) + '/'
        if page_path == '/./' or page_path == '//':
            page_path = '/'

        page_brief = brief.get('pages', {}).get(page_path, {})
        page_url = f'{domain}{page_path}'

        # Generate SEO metadata
        meta = generate_meta(page_path, page_brief, config)

        # Fill SEO slots in HTML
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        html = fill_seo_slot(html, 'seo.title', meta['title'])
        html = fill_seo_slot(html, 'seo.description', meta['description'])
        html = fill_seo_slot(html, 'seo.og_title', meta['og_title'])
        html = fill_seo_slot(html, 'seo.og_description', meta['og_description'])
        html = fill_seo_slot(html, 'seo.twitter_title', meta['twitter_title'])
        html = fill_seo_slot(html, 'seo.twitter_description', meta['twitter_description'])

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        # Validate
        errors = validate_page(html, page_path, meta)
        validation_errors.extend(errors)

        # Sitemap entry
        priority = get_priority(page_path, config)
        changefreq = get_changefreq(page_path)
        sitemap_entries.append({
            'url': page_url,
            'priority': priority,
            'changefreq': changefreq,
        })

        print(f'  {page_path}: "{meta["title"]}" ({len(meta["title"])} chars)')

    # Generate sitemap.xml
    write_sitemap(output_dir, sitemap_entries)

    # Report validation
    if validation_errors:
        print(f'\n!!! SEO VALIDATION ERRORS ({len(validation_errors)}) !!!')
        for err in validation_errors:
            print(f'  {err}')
    else:
        print('\nAll pages pass SEO validation.')

    print(f'\n=== SEO complete: {len(html_files)} pages ===\n')


def generate_meta(page_path, page_brief, config):
    """Generate unique SEO metadata for a page."""
    name = config['client']['name']
    city = config['contact']['city']
    state = config['contact']['state']
    location = f'{city}, {state}'

    # Get page title from brief or derive from path
    brief_title = page_brief.get('title', '')
    page_name = derive_page_name(page_path)

    if page_path == '/':
        title = f'{name} | {location}'
        desc = page_brief.get('description', f'{name} in {location}.')
    else:
        title = f'{page_name} | {name}'
        desc = page_brief.get('description', f'{page_name} at {name} in {location}.')

    # Enforce title length limit
    if len(title) > 60:
        # Try shorter format
        title = f'{page_name} | {name}'
        if len(title) > 60:
            title = title[:57] + '...'

    # Enforce description length limit
    if len(desc) > 160:
        desc = desc[:157] + '...'

    return {
        'title': title,
        'description': desc,
        'og_title': title,
        'og_description': desc,
        'twitter_title': title,
        'twitter_description': desc,
    }


def derive_page_name(page_path):
    """Derive a human-readable page name from URL path."""
    if page_path == '/':
        return 'Home'
    parts = page_path.strip('/').split('/')
    last = parts[-1]
    return last.replace('-', ' ').title()


def fill_seo_slot(html, slot_name, value):
    """Replace SEO values in HTML — handles both template tags and rendered-empty tags."""
    escaped = escape_html_attr(value)

    # Try template tag first
    html = html.replace(f'{{{{ {slot_name} }}}}', escaped)

    # Also replace already-rendered empty tags by matching the HTML element directly
    if slot_name == 'seo.title':
        html = re.sub(r'<title>[^<]*</title>', f'<title>{escaped}</title>', html)
    elif slot_name == 'seo.description':
        html = re.sub(r'(<meta\s+name="description"\s+content=")[^"]*(")', rf'\g<1>{escaped}\2', html)
    elif slot_name == 'seo.og_title':
        html = re.sub(r'(<meta\s+property="og:title"\s+content=")[^"]*(")', rf'\g<1>{escaped}\2', html)
    elif slot_name == 'seo.og_description':
        html = re.sub(r'(<meta\s+property="og:description"\s+content=")[^"]*(")', rf'\g<1>{escaped}\2', html)
    elif slot_name == 'seo.twitter_title':
        html = re.sub(r'(<meta\s+name="twitter:title"\s+content=")[^"]*(")', rf'\g<1>{escaped}\2', html)
    elif slot_name == 'seo.twitter_description':
        html = re.sub(r'(<meta\s+name="twitter:description"\s+content=")[^"]*(")', rf'\g<1>{escaped}\2', html)

    return html


def escape_html_attr(text):
    """Escape text for use in HTML attributes."""
    return (text
            .replace('&', '&amp;')
            .replace('"', '&quot;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def validate_page(html, page_path, meta):
    """Validate SEO completeness on a page."""
    errors = []

    if '<title>' not in html:
        errors.append(f'{page_path}: missing <title>')
    if 'meta name="description"' not in html:
        errors.append(f'{page_path}: missing meta description')
    if 'rel="canonical"' not in html:
        errors.append(f'{page_path}: missing canonical')
    if 'og:title' not in html:
        errors.append(f'{page_path}: missing og:title')
    if 'og:image' not in html:
        errors.append(f'{page_path}: missing og:image')
    if 'twitter:image' not in html:
        errors.append(f'{page_path}: missing twitter:image')

    if len(meta['title']) > 60:
        errors.append(f'{page_path}: title too long ({len(meta["title"])} chars)')
    if len(meta['description']) > 160:
        errors.append(f'{page_path}: description too long ({len(meta["description"])} chars)')

    return errors


def get_priority(page_path, config):
    """Determine sitemap priority for a page."""
    if page_path == '/':
        return '1.0'

    # Vendor pages and food-beverage
    vendors = config.get('vendors', [])
    vendor_slugs = [v['slug'] for v in vendors]
    path_clean = page_path.strip('/')

    if path_clean == 'food-beverage' or path_clean in vendor_slugs:
        return '0.8'
    if any(f'food-beverage/{s}' == path_clean for s in vendor_slugs):
        return '0.8'

    return '0.6'


def get_changefreq(page_path):
    """Determine sitemap changefreq for a page."""
    if page_path == '/':
        return 'weekly'
    path_lower = page_path.lower()
    if 'event' in path_lower or 'food-beverage' in path_lower:
        return 'weekly'
    return 'monthly'


def write_sitemap(output_dir, entries):
    """Generate sitemap.xml."""
    print('\nWriting sitemap.xml...')
    today = date.today().isoformat()

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')

    for entry in entries:
        lines.append('  <url>')
        lines.append(f'    <loc>{entry["url"]}</loc>')
        lines.append(f'    <lastmod>{today}</lastmod>')
        lines.append(f'    <changefreq>{entry["changefreq"]}</changefreq>')
        lines.append(f'    <priority>{entry["priority"]}</priority>')
        lines.append('  </url>')

    lines.append('</urlset>')

    sitemap_path = output_dir / 'sitemap.xml'
    with open(sitemap_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'  wrote: sitemap.xml ({len(entries)} URLs)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chowdown SEO — Module 7')
    parser.add_argument('--dir', required=True, help='Path to client output directory')
    args = parser.parse_args()
    seo(args.dir)
