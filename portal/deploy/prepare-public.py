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


CABINET_HEADER_CSS = """
.header .header-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: 10px 22px;
    align-items: center;
    padding-block: 14px;
}
.header .header-identity { grid-column: 1; grid-row: 1; }
.header .language-picker { grid-column: 2; grid-row: 1; margin-left: 0; }
.header .portal-cabinet {
    grid-column: 3;
    grid-row: 1;
    justify-self: end;
    display: inline-flex;
    min-height: 44px;
    align-items: center;
    justify-content: center;
    padding: 9px 15px;
    border: 1px solid #14495b;
    border-radius: 8px;
    background: #14495b;
    color: #fff;
    font: 600 14px/1.3 "Segoe UI", Arial, sans-serif;
    text-decoration: none;
    white-space: nowrap;
}
.header .portal-cabinet:hover { background: #0e3542; }
.header .portal-cabinet:focus-visible { outline: 3px solid #c49a4a; outline-offset: 3px; }
html[data-theme="dark"] .header .portal-cabinet { border-color: #7caaa3; }
.header #navigation {
    grid-column: 1 / -1;
    grid-row: 2;
    width: 100%;
    justify-content: flex-end;
    margin: 0;
    padding: 5px 0 0;
    gap: 4px 22px;
    border-top: 1px solid var(--stone);
}
@media (min-width: 721px) and (max-width: 900px) {
    .header .header-row { grid-template-columns: minmax(0, 1fr) auto; }
    .header .portal-cabinet { grid-column: 2; }
    .header .language-picker { grid-column: 1 / -1; grid-row: 2; justify-self: start; }
    .header #navigation { grid-row: 3; }
}
@media (max-width: 720px) {
    .header .header-row { grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
    .header .portal-cabinet { grid-column: 2; padding-inline: 11px; font-size: 13px; }
    .header .language-picker {
        grid-column: 1 / -1;
        grid-row: 2;
        padding-right: 54px;
        width: 100%;
    }
    .header .menu-toggle { grid-column: 2; grid-row: 2; }
    .header #navigation { grid-row: 3; padding: 4px 14px; gap: 0; border-color: var(--line); }
}
@media (max-width: 440px) {
    .header .header-identity .brand img { width: 34px; height: 34px; flex-basis: 34px; }
    .header .header-identity .brand { gap: 7px; }
    .header .brand-name { font-size: 11px; }
    .header .brand-line { white-space: normal; }
    .header .portal-cabinet { padding-inline: 9px; font-size: 12px; }
    .header .language-flags { gap: 3px; }
    .header .language-flag span { font-size: clamp(15px, 4.7vw, 20px); }
}
"""


def add_cabinet_button(source_html, url):
    marker = '<div class="language-picker">'
    if source_html.count(marker) != 1:
        raise SystemExit('Expected one language picker in the site header')
    button = f'<a class="portal-cabinet" href="{escape(url, quote=True)}">Личный кабинет</a>'
    source_html = source_html.replace(marker, button + '\n' + marker, 1)
    return source_html.replace('</head>', f'<style>{CABINET_HEADER_CSS}</style>\n</head>', 1)


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
    source_html = source_html.replace('</head>', '<meta name="robots" content="noindex,nofollow,noarchive">\n</head>', 1)
    cabinet_url = '/login/'
    if args.platform:
        # Fetch and validate before touching the currently served index.
        announcement = site_announcement(load_publication())
        cabinet_url = PLATFORM_URL + '/cabinet/'
        source_html = source_html.replace('<main id="main"', announcement + '<main id="main"', 1)
        source_html = source_html.replace('</head>', '<style>.portal-announcement{padding-block:24px}</style>\n</head>', 1)
    source_html = add_cabinet_button(source_html, cabinet_url)
    if args.platform:
        editorial = '<script defer src="assets/editorial.js?v=1" data-surface="site"></script>'
        source_html = source_html.replace("</head>", editorial + "\n</head>", 1)
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
