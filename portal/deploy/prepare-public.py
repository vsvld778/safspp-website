#!/usr/bin/env python3
"""Publish only explicitly approved static files; never expose the checkout."""
from pathlib import Path
from html import escape
import argparse
import json
import re
import shutil
import subprocess
from urllib.request import urlopen

SOURCE = Path('/opt/safspp/source')
DEST = Path('/srv/safspp/public')

PLATFORM_URL = 'https://app.migrantmost.ru'
PUBLICATION_URL = PLATFORM_URL + '/api/public/site-publication/'


def site_announcement(publication):
    if (not isinstance(publication, dict) or type(publication.get('revision')) is not int
            or type(publication.get('visible')) is not bool
            or any(not isinstance(publication.get(key), str) or len(publication[key]) > limit
                   for key, limit in (('title', 120), ('text', 1200)))):
        raise ValueError('Invalid site publication')
    if not publication['visible']:
        return ''
    title = escape(publication['title'])
    body = escape(publication['text']).replace('\n', '<br>')
    return f'<section class="shell portal-announcement"><h2>{title}</h2><p>{body}</p></section>'


def platform_entry():
    return (
        '<div class="portal-entry-bar">'
        f'<a class="portal-test-entry" href="{PLATFORM_URL}/cabinet/">Личный кабинет</a></div>'
    )


def load_publication():
    with urlopen(PUBLICATION_URL, timeout=8) as response:
        if response.url != PUBLICATION_URL:
            raise ValueError('The publication must be served by the canonical application URL')
        payload = response.read(16_385)
        if len(payload) > 16_384:
            raise ValueError('Site publication is too large')
    return json.loads(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', action='store_true', help='Publish links and the latest approved platform announcement')
    args = parser.parse_args()
    index = SOURCE / 'index.html'
    if not index.is_file() or index.is_symlink():
        raise SystemExit('Missing regular source index.html')
    source_html = index.read_text(encoding='utf-8')
    if '</head>' not in source_html or '<body' not in source_html:
        raise SystemExit('Source is not the expected complete HTML document')
    DEST.mkdir(parents=True, exist_ok=True, mode=0o755)
    source_html = re.sub(r'<meta\s+[^>]*name=["\']robots["\'][^>]*>', '', source_html, flags=re.I)
    source_html = source_html.replace('</head>', '<meta name="robots" content="noindex,nofollow,noarchive">\n<style>.portal-entry-bar{display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:4px 28px;padding:10px 18px;background:#14495b}.portal-test-entry{display:block;text-align:center;padding:4px 0;color:#fff;font:600 15px/1.4 Arial,sans-serif;text-decoration:underline;text-underline-offset:3px}.portal-test-entry:focus-visible{outline:3px solid #c49a4a;outline-offset:3px}</style>\n</head>', 1)
    entry = '<div class="portal-entry-bar"><a class="portal-test-entry" href="/login/">Личный кабинет · тестовый режим</a></div>'
    if args.platform:
        # Fetch and validate before touching the currently served index.
        announcement = site_announcement(load_publication())
        entry = platform_entry()
        source_html = source_html.replace('<main id="main"', announcement + '<main id="main"', 1)
        source_html = source_html.replace('</head>', '<style>.portal-announcement{padding-block:24px}</style>\n</head>', 1)
    source_html = re.sub(r'(<body\b[^>]*>)', lambda m: m.group(1) + '\n' + entry, source_html, count=1, flags=re.I)
    assets = SOURCE / 'assets'
    if not assets.is_dir() or assets.is_symlink():
        raise SystemExit('Missing regular assets directory')
    subprocess.run(['rsync', '-a', '--safe-links', '--chmod=D755,F644', '--chown=root:root', str(assets) + '/', str(DEST / 'assets') + '/'], check=True)
    for name in ('concept.pdf', '.nojekyll'):
        item = SOURCE / name
        if item.is_file() and not item.is_symlink():
            shutil.copyfile(item, DEST / name)
            (DEST / name).chmod(0o644)
    staged = DEST / 'index.html.pending'
    staged.write_text(source_html, encoding='utf-8')
    staged.chmod(0o644)
    staged.replace(DEST / 'index.html')
    print('Published the public homepage.')

if __name__ == '__main__':
    main()
