#!/usr/bin/env python3
"""Fail closed unless both REG authorities and Cloudflare agree on deployment DNS."""
from concurrent.futures import ThreadPoolExecutor
import re
import shutil
import subprocess
import sys

EXPECTED_ADDRESS = '194.58.103.10'
ALLOWED_NAMES = {'migrantmost.ru', 'www.migrantmost.ru'}
SERVERS = (('ns1.reg.ru', True), ('ns2.reg.ru', True), ('1.1.1.1', False))


def validate_response(output, domain, rrtype, authoritative):
    header = re.search(r'^;; ->>HEADER<<-.*\bstatus: ([A-Z]+),', output, re.MULTILINE)
    flags = re.search(r'^;; flags: ([^;]*);', output, re.MULTILINE)
    if not header or header.group(1) != 'NOERROR' or not flags:
        raise ValueError('DNS response is missing or not NOERROR')
    flags = set(flags.group(1).split())
    if 'qr' not in flags or 'tc' in flags or (authoritative and 'aa' not in flags):
        raise ValueError('DNS response lacks required complete/authoritative flags')
    values = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith(';'):
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError('Unexpected DNS answer format')
        owner, ttl, record_class, answer_type, value = fields
        if owner.lower() != domain.lower() + '.' or not ttl.isdigit() or record_class != 'IN' or answer_type != rrtype:
            raise ValueError('Unexpected owner/type or CNAME in DNS answer')
        values.append(value)
    if rrtype == 'A' and set(values) != {EXPECTED_ADDRESS}:
        raise ValueError('A records do not resolve exclusively to the intended VPS')
    if rrtype == 'AAAA' and values:
        raise ValueError('An IPv6 record is present but this deployment has no configured IPv6 endpoint')


def query(dig, server, authoritative, domain, rrtype):
    command = [dig, '+tcp', '+time=3', '+tries=1', '+noall', '+comments', '+answer', '@' + server, domain, rrtype]
    label = server + ' / ' + domain + ' / ' + rrtype
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        if result.returncode:
            raise ValueError('DNS query failed')
        validate_response(result.stdout, domain, rrtype, authoritative)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ValueError(label + ': ' + str(exc)) from exc
    return label + ': verified'


def verify(domains):
    if not domains or len(domains) != len(set(domains)) or not set(domains) <= ALLOWED_NAMES:
        raise ValueError('Only the unique intended deployment names may be verified')
    dig = shutil.which('dig')
    if not dig:
        raise ValueError('dig is required for independent DNS verification (Ubuntu package: dnsutils)')
    probes = [(server, authoritative, domain, rrtype) for server, authoritative in SERVERS for domain in domains for rrtype in ('A', 'AAAA')]
    # Twelve bounded probes for apex+www; no response is silently skipped.
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(query, dig, *probe) for probe in probes]
        results = []
        failures = []
        for future in futures:
            try:
                results.append(future.result())
            except ValueError as exc:
                failures.append(str(exc))
    if failures:
        raise ValueError('Independent DNS verification failed:\n' + '\n'.join(failures))
    return results


if __name__ == '__main__':
    try:
        results = verify(sys.argv[1:])
    except ValueError as exc:
        raise SystemExit(str(exc))
    print('\n'.join(results))
    print('Both REG authoritative servers and Cloudflare agree: intended IPv4 only, no AAAA records.')
