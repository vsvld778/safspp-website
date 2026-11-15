#!/usr/bin/env python3
"""Atomically set the portal domain while preserving secrets and unrelated keys."""
import argparse
import os
from pathlib import Path
import re
import shlex
import stat
import tempfile

def update_environment(path: Path, include_www=False):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Environment path must be a regular, non-symlink file')
    metadata = path.stat()
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines()
    parsed = {}
    for line in lines:
        match = re.match(r'^([A-Z][A-Z0-9_]*)=(.*)$', line)
        if match:
            words = shlex.split(match.group(2), comments=True)
            if len(words) > 1:
                raise ValueError('Environment values containing spaces must be quoted')
            parsed[match.group(1)] = words[0] if words else ''
    domains = ['migrantmost.ru'] + (['www.migrantmost.ru'] if include_www else [])

    def merged(key, required):
        values = [x.strip() for x in parsed.get(key, '').split(',') if x.strip()]
        return ','.join(dict.fromkeys(values + required))

    updates = {
        'DJANGO_ALLOWED_HOSTS': merged('DJANGO_ALLOWED_HOSTS', ['194.58.103.10', '127.0.0.1', 'localhost'] + domains),
        'DJANGO_CSRF_TRUSTED_ORIGINS': merged('DJANGO_CSRF_TRUSTED_ORIGINS', ['https://194.58.103.10'] + ['https://' + d for d in domains]),
        'PUBLIC_SITE_URL': 'https://migrantmost.ru/',
        'DJANGO_TRUST_PROXY': 'true',
        'DJANGO_SECURE_COOKIES': 'true',
        'DJANGO_SECURE_SSL_REDIRECT': 'true',
    }
    output = []
    seen = set()
    for line in lines:
        key = line.split('=', 1)[0]
        if key in updates:
            if key not in seen:
                output.append(key + '=' + updates[key])
                seen.add(key)
        else:
            output.append(line)
    output.extend(key + '=' + value for key, value in updates.items() if key not in seen)
    content = '\n'.join(output) + '\n'
    if content == original:
        return
    fd, temporary = tempfile.mkstemp(prefix='.portal-domain-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('environment', type=Path)
    parser.add_argument('--www', action='store_true')
    args = parser.parse_args()
    update_environment(args.environment, args.www)
    print('Domain settings updated; secret and intake/registration settings preserved.')
