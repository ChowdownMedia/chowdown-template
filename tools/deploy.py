#!/usr/bin/env python3
"""
Chowdown Deploy — Module 8
Commits built site to GitHub and runs post-deploy verification.

Usage:
    python3 tools/deploy.py --dir output/CLIENT/ --pages output/CLIENT/page-tree.json

Steps:
  1. Read config.json for client name, slug, GitHub repo
  2. git init (if needed), git add -A, git commit
  3. gh repo create under ChowdownMedia org and push
  4. Post-deploy verification:
     - Zero source platform references (sh-websites.com, spotapps.co)
     - Zero cross-client contamination (liberty-collective, westfield-collective)
     - Zero old URL patterns (food_and_beverage, /vendor/)
     - Page count matches approved count from page-tree.json
  5. Print staging URL
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run(cmd, cwd=None, check=True):
    """Run a shell command and return output."""
    result = subprocess.run(
        cmd, shell=True, cwd=cwd,
        capture_output=True, text=True
    )
    if check and result.returncode != 0:
        print(f'  CMD: {cmd}')
        print(f'  STDERR: {result.stderr.strip()}')
        if result.returncode != 0 and check:
            print(f'  WARNING: command returned {result.returncode}')
    return result


def deploy(output_dir, pages_path):
    output_dir = Path(output_dir).resolve()
    config = load_json(output_dir / 'config.json')
    page_tree = load_json(pages_path)

    name = config['client']['name']
    slug = config['client']['slug']
    repo = config['client'].get('github_repo', f'ChowdownMedia/{slug}')

    print(f'\n=== Deploy: {name} ===')
    print(f'Output: {output_dir}')
    print(f'Repo: {repo}')

    # Count approved pages
    approved = [p for p in page_tree.get('pages', []) if p.get('status') in ('approved', 'include')]
    expected_count = len(approved)

    # 1. Pre-deploy verification
    print('\n--- Pre-deploy verification ---')
    errors = verify(output_dir, expected_count, slug)
    if errors:
        print(f'\n!!! {len(errors)} VERIFICATION ERRORS — FIX BEFORE DEPLOYING !!!')
        for e in errors:
            print(f'  {e}')
        print('\nDeploy aborted.')
        sys.exit(1)
    print('All checks passed.\n')

    # 2. Git init + commit
    print('--- Git ---')
    if not (output_dir / '.git').exists():
        run('git init', cwd=output_dir)

    page_count = count_html_files(output_dir)
    commit_msg = f'Initial build: {name} — {page_count} pages, optimized assets, full SEO'

    run('git add -A', cwd=output_dir)
    run(f'git commit -m "{commit_msg}"', cwd=output_dir)
    print(f'  Committed: {commit_msg}')

    # 3. Create GitHub repo and push
    print('\n--- GitHub ---')
    result = run(
        f'gh repo create {repo} --public --source=. --push',
        cwd=output_dir, check=False
    )
    if result.returncode == 0:
        print(f'  Created: https://github.com/{repo}')
    else:
        # Repo may already exist — try pushing
        print(f'  Repo may already exist, pushing...')
        run(f'git remote add origin https://github.com/{repo}.git', cwd=output_dir, check=False)
        run('git push -u origin main', cwd=output_dir, check=False)

    # 4. Print staging URL
    staging_url = f'https://{slug}.pages.dev'
    print(f'\n--- Deploy complete ---')
    print(f'  GitHub: https://github.com/{repo}')
    print(f'  Staging: {staging_url}')
    print(f'  Pages: {page_count}')
    print(f'\n  Next: Connect GitHub to Cloudflare Pages in dashboard,')
    print(f'  or run: wrangler pages deploy . --project-name {slug} --branch main')
    print()


def verify(output_dir, expected_count, client_slug):
    """Run all post-build verification checks."""
    errors = []

    # Check 1: Zero source platform references
    result = run(
        'grep -rl "sh-websites.com\\|spotapps.co" --include="*.html" .',
        cwd=output_dir, check=False
    )
    if result.stdout.strip():
        count = len(result.stdout.strip().split('\n'))
        errors.append(f'Source platform references found in {count} file(s): sh-websites.com or spotapps.co')

    # Check 2: Zero cross-client contamination
    # Skip the client's own slug
    other_slugs = ['liberty-collective', 'westfield-collective']
    other_slugs = [s for s in other_slugs if s != client_slug]
    if other_slugs:
        pattern = '\\|'.join(other_slugs)
        result = run(
            f'grep -rl "{pattern}" --include="*.html" .',
            cwd=output_dir, check=False
        )
        if result.stdout.strip():
            count = len(result.stdout.strip().split('\n'))
            errors.append(f'Cross-client contamination found in {count} file(s): {", ".join(other_slugs)}')

    # Check 3: Zero old URL patterns
    result = run(
        'grep -rl "food_and_beverage\\|/vendor/" --include="*.html" .',
        cwd=output_dir, check=False
    )
    if result.stdout.strip():
        count = len(result.stdout.strip().split('\n'))
        errors.append(f'Old URL patterns found in {count} file(s): food_and_beverage or /vendor/')

    # Check 4: Page count matches
    actual_count = count_html_files(output_dir)
    if expected_count > 0 and actual_count != expected_count:
        errors.append(f'Page count mismatch: expected {expected_count}, found {actual_count}')
    print(f'  Pages: {actual_count} (expected: {expected_count})')

    # Check 5: All iframes have title attributes
    result = run(
        'grep -rl "<iframe" --include="*.html" . | xargs grep -L "title=" 2>/dev/null',
        cwd=output_dir, check=False
    )
    if result.stdout.strip():
        count = len(result.stdout.strip().split('\n'))
        errors.append(f'Iframes missing title attribute in {count} file(s)')

    # Check 6: Sitemap exists and URL count matches
    sitemap_path = output_dir / 'sitemap.xml'
    if not sitemap_path.exists():
        errors.append('sitemap.xml not found')
    else:
        with open(sitemap_path, 'r') as f:
            sitemap_urls = f.read().count('<loc>')
        if sitemap_urls != actual_count:
            errors.append(f'Sitemap URL count ({sitemap_urls}) != HTML file count ({actual_count})')
        print(f'  Sitemap: {sitemap_urls} URLs')

    # Check 7: robots.txt exists
    if not (output_dir / 'robots.txt').exists():
        errors.append('robots.txt not found')

    for check_name, passed in [
        ('Source platform refs', not any('Source platform' in e for e in errors)),
        ('Cross-client contamination', not any('Cross-client' in e for e in errors)),
        ('Old URL patterns', not any('Old URL' in e for e in errors)),
        ('Page count', not any('Page count' in e for e in errors)),
        ('Iframe titles', not any('Iframes' in e for e in errors)),
        ('Sitemap', not any('sitemap' in e.lower() for e in errors)),
        ('robots.txt', not any('robots' in e for e in errors)),
    ]:
        status = 'PASS' if passed else 'FAIL'
        print(f'  {check_name}: {status}')

    return errors


def count_html_files(directory):
    """Count index.html files in directory."""
    return len(list(Path(directory).rglob('index.html')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chowdown Deploy — Module 8')
    parser.add_argument('--dir', required=True, help='Path to client output directory')
    parser.add_argument('--pages', required=True, help='Path to page-tree.json')
    args = parser.parse_args()
    deploy(args.dir, args.pages)
