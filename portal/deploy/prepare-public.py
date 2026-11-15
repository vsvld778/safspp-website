#!/usr/bin/env python3
"""Publish only explicitly approved static files; never expose the checkout."""
from pathlib import Path
import re
import shutil
import subprocess

SOURCE = Path('/opt/safspp/source')
DEST = Path('/srv/safspp/public')

def main():
    index = SOURCE / 'index.html'
    if not index.is_file() or index.is_symlink():
        raise SystemExit('Missing regular source index.html')
    source_html = index.read_text(encoding='utf-8')
    if '</head>' not in source_html or '<body' not in source_html:
        raise SystemExit('Source is not the expected complete HTML document')
    DEST.mkdir(parents=True, exist_ok=True, mode=0o755)
    source_html = re.sub(r'<meta\s+[^>]*name=["\']robots["\'][^>]*>', '', source_html, flags=re.I)
    source_html = source_html.replace('</head>', '<meta name="robots" content="noindex,nofollow,noarchive">\n<style>.portal-entry-bar{display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:4px 28px;padding:10px 18px;background:#14495b}.portal-test-entry{display:block;text-align:center;padding:4px 0;color:#fff;font:600 15px/1.4 Arial,sans-serif;text-decoration:underline;text-underline-offset:3px}.portal-test-entry:focus-visible{outline:3px solid #c49a4a;outline-offset:3px}</style>\n</head>', 1)
    source_html = re.sub(r'(<body\b[^>]*>)', r'\1\n<div class="portal-entry-bar"><a class="portal-test-entry" href="/login/">Личный кабинет · тестовый режим</a><a class="portal-test-entry" href="/partners/preview/">Кабинет организации · демоверсия</a></div>', source_html, count=1, flags=re.I)
    staged = DEST / 'index.html.pending'
    staged.write_text(source_html, encoding='utf-8')
    staged.chmod(0o644)
    staged.replace(DEST / 'index.html')
    assets = SOURCE / 'assets'
    if not assets.is_dir() or assets.is_symlink():
        raise SystemExit('Missing regular assets directory')
    subprocess.run(['rsync', '-a', '--safe-links', '--chmod=D755,F644', '--chown=root:root', str(assets) + '/', str(DEST / 'assets') + '/'], check=True)
    for name in ('concept.pdf', '.nojekyll'):
        item = SOURCE / name
        if item.is_file() and not item.is_symlink():
            shutil.copyfile(item, DEST / name)
            (DEST / name).chmod(0o644)
    print('Published static allowlist with test portal link and noindex; source unchanged.')

if __name__ == '__main__':
    main()
