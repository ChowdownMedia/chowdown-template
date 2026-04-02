#!/usr/bin/env python3
"""
Chowdown Schema Generator — Module 6
Generates JSON-LD structured data from config.json and injects into pages.

Usage:
    python3 tools/schema.py --dir output/CLIENT/

Schema by page type:
  homepage:       LocalBusiness + FoodEstablishment/EntertainmentBusiness
  vendor:         Restaurant/BarOrPub + parentOrganization + BreadcrumbList
  events:         Event + BreadcrumbList
  sports/activity: SportsActivityLocation + BreadcrumbList
  private-parties: EventVenue + BreadcrumbList
  all others:     BreadcrumbList
"""

import argparse
import json
import os
import re
from pathlib import Path

# Known source-site coordinates to validate against
CONTAMINATION_COORDS = [
    (39.3617, -84.3733),   # Liberty Collective (Liberty Township, OH)
]


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def schema(output_dir):
    output_dir = Path(output_dir)
    config = load_json(output_dir / 'config.json')

    print(f'\n=== Schema: {config["client"]["name"]} ===')

    # Validate geo coordinates aren't contaminated
    validate_coordinates(config)

    # Find all index.html files
    html_files = list(output_dir.rglob('index.html'))
    print(f'Processing {len(html_files)} pages\n')

    for html_path in html_files:
        page_path = '/' + str(html_path.parent.relative_to(output_dir)) + '/'
        if page_path == '/./' or page_path == '//':
            page_path = '/'

        page_type = classify_page(page_path, config)
        schema_blocks = generate_schema(page_type, page_path, config)

        inject_schema(html_path, schema_blocks)
        print(f'  {page_path} -> {page_type} ({len(schema_blocks)} blocks)')

    print(f'\n=== Schema complete ===\n')


def classify_page(page_path, config):
    """Determine page type from path and config."""
    if page_path == '/':
        return 'homepage'

    # Check if it's a vendor page
    vendors = config.get('vendors', [])
    for v in vendors:
        if f'/{v["slug"]}/' in page_path:
            return 'vendor'

    # Match by path keywords
    path_lower = page_path.lower()
    if 'event' in path_lower:
        return 'events'
    if 'sand-sport' in path_lower or 'beach' in path_lower or 'volleyball' in path_lower:
        return 'sports'
    if 'private-part' in path_lower or 'party' in path_lower:
        return 'venue'
    if 'golf-simulator' in path_lower:
        return 'sports'

    return 'subpage'


def generate_schema(page_type, page_path, config):
    """Generate JSON-LD blocks for a page type."""
    blocks = []
    domain = config['client']['domain']

    if page_type == 'homepage':
        blocks.append(generate_homepage_schema(config))
    elif page_type == 'vendor':
        blocks.append(generate_vendor_schema(page_path, config))
    elif page_type == 'events':
        blocks.append(generate_event_schema(config))
    elif page_type == 'sports':
        blocks.append(generate_sports_schema(page_path, config))
    elif page_type == 'venue':
        blocks.append(generate_venue_schema(page_path, config))

    # BreadcrumbList for all non-homepage pages
    if page_path != '/':
        blocks.append(generate_breadcrumb(page_path, config))

    return blocks


def generate_homepage_schema(config):
    """LocalBusiness + FoodEstablishment or EntertainmentBusiness."""
    schema_type = config.get('schema', {}).get('type', 'Restaurant')
    contact = config['contact']
    brand = config.get('brand', {})
    domain = config['client']['domain']

    # Determine @type array
    if config['client'].get('template_type') == 'venue':
        types = ['LocalBusiness', 'EntertainmentBusiness', 'FoodEstablishment']
    else:
        types = ['LocalBusiness', 'FoodEstablishment']

    schema = {
        '@context': 'https://schema.org',
        '@type': types,
        'name': config['client']['name'],
        'url': domain,
        'telephone': contact.get('phone', ''),
        'email': contact.get('email', ''),
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': contact['address'],
            'addressLocality': contact['city'],
            'addressRegion': contact['state'],
            'postalCode': contact['zip'],
            'addressCountry': contact.get('country', 'US'),
        },
        'geo': {
            '@type': 'GeoCoordinates',
            'latitude': contact['geo']['lat'],
            'longitude': contact['geo']['lng'],
        },
        'openingHoursSpecification': generate_opening_hours(config),
        'priceRange': config.get('schema', {}).get('price_range', '$$'),
    }

    cuisine = config.get('schema', {}).get('cuisine', [])
    if cuisine:
        schema['servesCuisine'] = cuisine

    social = config.get('social', {})
    same_as = [v for v in social.values() if v]
    if same_as:
        schema['sameAs'] = same_as

    # Remove empty values
    schema = {k: v for k, v in schema.items() if v}

    return json_ld(schema)


def generate_vendor_schema(page_path, config):
    """Restaurant/BarOrPub + parentOrganization."""
    vendors = config.get('vendors', [])
    vendor = None
    for v in vendors:
        if f'/{v["slug"]}/' in page_path:
            vendor = v
            break

    if not vendor:
        return ''

    contact = config['contact']
    domain = config['client']['domain']

    schema = {
        '@context': 'https://schema.org',
        '@type': vendor.get('type', 'Restaurant'),
        'name': vendor['name'],
        'url': f'{domain}{page_path}',
        'telephone': contact.get('phone', ''),
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': contact['address'],
            'addressLocality': contact['city'],
            'addressRegion': contact['state'],
            'postalCode': contact['zip'],
            'addressCountry': contact.get('country', 'US'),
        },
        'priceRange': config.get('schema', {}).get('price_range', '$$'),
        'parentOrganization': {
            '@type': 'Organization',
            'name': config['client']['name'],
            'url': domain,
        },
    }

    cuisine = vendor.get('cuisine', [])
    if cuisine:
        schema['servesCuisine'] = cuisine

    schema = {k: v for k, v in schema.items() if v}
    return json_ld(schema)


def generate_event_schema(config):
    """Event schema — placeholder structure."""
    domain = config['client']['domain']
    contact = config['contact']

    schema = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        'name': f'Events at {config["client"]["name"]}',
        'eventAttendanceMode': 'https://schema.org/OfflineEventAttendanceMode',
        'eventStatus': 'https://schema.org/EventScheduled',
        'location': {
            '@type': 'Place',
            'name': config['client']['name'],
            'address': {
                '@type': 'PostalAddress',
                'streetAddress': contact['address'],
                'addressLocality': contact['city'],
                'addressRegion': contact['state'],
                'postalCode': contact['zip'],
                'addressCountry': contact.get('country', 'US'),
            },
        },
        'organizer': {
            '@type': 'Organization',
            'name': config['client']['name'],
            'url': domain,
        },
    }
    return json_ld(schema)


def generate_sports_schema(page_path, config):
    """SportsActivityLocation schema."""
    contact = config['contact']
    domain = config['client']['domain']

    # Derive name from path
    path_name = page_path.strip('/').replace('-', ' ').title()

    schema = {
        '@context': 'https://schema.org',
        '@type': 'SportsActivityLocation',
        'name': f'{path_name} at {config["client"]["name"]}',
        'url': f'{domain}{page_path}',
        'telephone': contact.get('phone', ''),
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': contact['address'],
            'addressLocality': contact['city'],
            'addressRegion': contact['state'],
            'postalCode': contact['zip'],
            'addressCountry': contact.get('country', 'US'),
        },
    }
    return json_ld(schema)


def generate_venue_schema(page_path, config):
    """EventVenue schema for private parties."""
    contact = config['contact']
    domain = config['client']['domain']

    schema = {
        '@context': 'https://schema.org',
        '@type': 'EventVenue',
        'name': config['client']['name'],
        'url': f'{domain}{page_path}',
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': contact['address'],
            'addressLocality': contact['city'],
            'addressRegion': contact['state'],
            'postalCode': contact['zip'],
            'addressCountry': contact.get('country', 'US'),
        },
        'telephone': contact.get('phone', ''),
    }
    return json_ld(schema)


def generate_breadcrumb(page_path, config):
    """BreadcrumbList for any non-homepage page."""
    domain = config['client']['domain']
    parts = [p for p in page_path.strip('/').split('/') if p]

    items = [{
        '@type': 'ListItem',
        'position': 1,
        'name': 'Home',
        'item': f'{domain}/',
    }]

    for i, part in enumerate(parts):
        name = part.replace('-', ' ').title()
        is_last = (i == len(parts) - 1)
        entry = {
            '@type': 'ListItem',
            'position': i + 2,
            'name': name,
        }
        if not is_last:
            path = '/' + '/'.join(parts[:i + 1]) + '/'
            entry['item'] = f'{domain}{path}'
        items.append(entry)

    schema = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': items,
    }
    return json_ld(schema)


def generate_opening_hours(config):
    """Generate openingHoursSpecification from config.hours."""
    specs = []
    day_map = {
        'monday': 'Monday', 'tuesday': 'Tuesday', 'wednesday': 'Wednesday',
        'thursday': 'Thursday', 'friday': 'Friday', 'saturday': 'Saturday',
        'sunday': 'Sunday',
    }

    groups = config.get('hours', {}).get('groups', [])
    # Use the first group (typically the broadest hours) for schema
    if not groups:
        return specs

    primary = groups[0]
    for slot in primary.get('schedule', []):
        days_str = slot.get('days', '')
        opens = slot.get('open', '')
        closes = slot.get('close', '')

        schema_days = parse_days(days_str)
        if schema_days and opens and closes:
            specs.append({
                '@type': 'OpeningHoursSpecification',
                'dayOfWeek': schema_days if len(schema_days) > 1 else schema_days[0],
                'opens': opens,
                'closes': closes,
            })

    return specs


def parse_days(days_str):
    """Parse 'Monday - Thursday' or 'Friday' into schema.org day names."""
    days_str = days_str.strip()
    all_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    # Single day
    for day in all_days:
        if days_str.lower() == day.lower():
            return [day]

    # Range: "Monday - Thursday", "Mon - Thurs", "Mon-Thurs"
    range_match = re.match(r'(mon\w*)\s*[-–]\s*(thu\w*|fri\w*|sat\w*|sun\w*)', days_str, re.IGNORECASE)
    if range_match:
        start = match_day(range_match.group(1))
        end = match_day(range_match.group(2))
        if start is not None and end is not None:
            start_idx = all_days.index(start)
            end_idx = all_days.index(end)
            return all_days[start_idx:end_idx + 1]

    # Try matching abbreviated
    day = match_day(days_str)
    if day:
        return [day]

    return []


def match_day(text):
    """Match abbreviated or full day name."""
    text = text.strip().lower()
    mapping = {
        'mon': 'Monday', 'tue': 'Tuesday', 'wed': 'Wednesday',
        'thu': 'Thursday', 'fri': 'Friday', 'sat': 'Saturday', 'sun': 'Sunday',
        'monday': 'Monday', 'tuesday': 'Tuesday', 'wednesday': 'Wednesday',
        'thursday': 'Thursday', 'friday': 'Friday', 'saturday': 'Saturday', 'sunday': 'Sunday',
    }
    for prefix, day in mapping.items():
        if text.startswith(prefix):
            return day
    return None


def validate_coordinates(config):
    """Verify geo coordinates aren't from another client's config."""
    geo = config.get('contact', {}).get('geo', {})
    lat = geo.get('lat', 0)
    lng = geo.get('lng', 0)

    for clat, clng in CONTAMINATION_COORDS:
        if abs(lat - clat) < 0.01 and abs(lng - clng) < 0.01:
            print(f'  !!! COORDINATE CONTAMINATION: ({lat}, {lng}) matches known source site !!!')
            print(f'  !!! This looks like Liberty Collective coordinates, not this client !!!')
            raise ValueError(f'Geo coordinate contamination detected: ({lat}, {lng})')

    print(f'  Coordinates verified: ({lat}, {lng})')


def json_ld(schema):
    """Format a schema dict as a <script type=application/ld+json> block."""
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(schema, indent=2, ensure_ascii=False)
        + '\n</script>'
    )


def inject_schema(html_path, schema_blocks):
    """Replace schema slot in HTML with generated JSON-LD blocks."""
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    schema_html = '\n  '.join(schema_blocks)

    # Replace the slot marker
    html = re.sub(
        r'<!-- SLOT: schema_json_ld -->\s*\{\{\s*schema_blocks\s*\}\}',
        f'<!-- Schema generated by schema.py -->\n  {schema_html}',
        html
    )

    # Also replace standalone {{ schema_blocks }}
    html = html.replace('{{ schema_blocks }}', schema_html)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chowdown Schema — Module 6')
    parser.add_argument('--dir', required=True, help='Path to client output directory')
    args = parser.parse_args()
    schema(args.dir)
