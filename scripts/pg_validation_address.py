#!/usr/bin/env python3
"""Shared address contract for the owned PostgreSQL validation phases."""
from __future__ import annotations
import argparse
import os
import re
import sys
from typing import NoReturn
from urllib.parse import parse_qsl, urlsplit


def fail(message: str) -> NoReturn:
    raise RuntimeError(message)


# Explicit address contract for the already provisioned workflow service, not
# proof of physical ownership. The workflow retains its service-ID diagnostics.
REDIRECT_OPTIONS = {'host', 'hostaddr', 'port', 'dbname', 'database', 'user',
                    'password', 'passfile', 'service', 'servicefile', 'options',
                    'target_session_attrs', 'search_path', 'role', 'session_authorization'}
REDIRECT_ENV = ('PGHOST', 'PGHOSTADDR', 'PGPORT', 'PGDATABASE', 'PGUSER',
                'PGPASSWORD', 'PGPASSFILE', 'PGSERVICE', 'PGSERVICEFILE',
                'PGSYSCONFDIR', 'PGOPTIONS', 'PGTARGETSESSIONATTRS')


def check_address_environment(adapter: str) -> None:
    if adapter not in ('loopback', 'github-service'):
        fail('unsupported database adapter')
    for key in REDIRECT_ENV:
        if os.environ.get(key):
            fail(f'{key} may redirect the disposable connection; unset it before execution')


def check_address(key: str, value: str, adapter: str, database: str) -> None:
    if not value:
        fail(f'{key} is required; refusing a silently skipped integration suite')
    if adapter == 'github-service':
        if value not in {f'{scheme}://postgres:ci@postgres:5432/{database}' for scheme in ('postgres', 'postgresql')}:
            fail(f'{key} must be a canonical github-service disposable {database} URI')
    else:
        # urlsplit strips some control characters; reject before parsing.
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            fail(f'{key} contains control characters')
        parsed = urlsplit(value)
        if parsed.scheme not in ('postgres', 'postgresql') or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.path != '/' + database:
            fail(f'{key} must point at the loopback disposable {database} service')
        # pgx splits the URL host into comma-separated failover hosts;
        # urlsplit.hostname alone can hide everything after the first port.
        # Check only the final hostspec, preserving encoded userinfo.
        hostspec = parsed.netloc.rsplit('@', 1)[-1]
        if re.fullmatch(r'(?:127\.0\.0\.1|localhost)(?::[0-9]+)?', hostspec) is None:
            fail(f'{key} must contain one literal loopback host and optional numeric port')
        try:
            port = parsed.port
        except ValueError:
            fail(f'{key} contains an invalid loopback port')
        if port is not None and not 1 <= port <= 65535:
            fail(f'{key} contains an invalid loopback port')
        if parsed.fragment:
            fail(f'{key} must not contain a URI fragment')
        # Decode parameter names before checking: %68ostaddr is hostaddr.
        if any(name.lower() in REDIRECT_OPTIONS for name, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            fail(f'{key} contains a connection/session redirect option')


def check_clean_environment(adapter: str) -> None:
    check_address_environment(adapter)
    identities = []
    for key, database in (('YUEBOARD_ADMIN_DATABASE_URL', 'postgres'),
                          ('CLEAN_PG_DSN', 'yueboard_clean_gate')):
        value = os.environ.get(key, '')
        check_address(key, value, adapter, database)
        parsed = urlsplit(value)
        # Only database names may differ. Equivalent scheme spellings are
        # normalized, but authority and allowed query options stay exact.
        identities.append(('postgres', parsed.netloc, parsed.query))
    if identities[0] != identities[1]:
        fail('clean database connection identity mismatch')


def check_e2e_environment(adapter: str) -> None:
    check_address_environment(adapter)
    identities = []
    for key, database in (('YUEBOARD_ADMIN_DATABASE_URL', 'postgres'),
                          ('YUEBOARD_E2E_DATABASE_URL', 'yueboard_e2e')):
        value = os.environ.get(key, '')
        # The hosted admin URI has no SSL option; the browser server explicitly
        # disables SSL for its disposable service. Do not normalize other options.
        base = value.removesuffix('?sslmode=disable')
        check_address(key, base, adapter, database)
        parsed = urlsplit(base)
        if parsed.query or (key == 'YUEBOARD_E2E_DATABASE_URL' and base == value):
            fail('e2e database requires only the explicit sslmode=disable option')
        identities.append(parsed.netloc)
    if identities[0] != identities[1]:
        fail('e2e database connection identity mismatch')
    if os.environ.get('YUEBOARD_E2E_ALLOW_RESET') != 'YES_I_UNDERSTAND_THIS_DATABASE_IS_DISPOSABLE':
        fail('e2e database reset requires explicit disposable acknowledgement')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-adapter', choices=['loopback', 'github-service'], required=True)
    parser.add_argument('--phase', choices=['clean', 'e2e'], default='clean')
    args = parser.parse_args()
    try:
        if args.phase == 'e2e':
            check_e2e_environment(args.database_adapter)
        else:
            check_clean_environment(args.database_adapter)
    except (RuntimeError, ValueError) as error:
        print(f'::error::{error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
