#!/usr/bin/env python3
"""Offline configuration gate. Does not deploy, contact providers, or certify readiness."""
import argparse
import os
import sys
from urllib.parse import urlsplit


def failures(config):
    errors = []
    for name in ('DEBUG', 'GUEST_AUTH_DEMO_OTP',
                 'GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION', 'PAYMENTS_ALLOW_SIMULATOR'):
        if str(config.get(name, '')).lower() not in ('false', '0'):
            errors.append(f'{name}: explicitly set false')
    required = ('DJANGO_SECRET_KEY', 'DATABASE_URL', 'ALLOWED_HOSTS',
                'CSRF_TRUSTED_ORIGINS', 'DOCUMENT_DATA_ENCRYPTION_KEYS',
                'METRICS_BEARER_TOKEN', 'PAYMENTS_SCHEDULER_SECRET',
                'XPAYMENT_API_KEY', 'XPAYMENT_WEBHOOK_SECRET',
                'XPAYMENT_DEVICE_NAME', 'XPAYMENT_PRODUCTION_RESORT_IDS',
                'SUPABASE_S3_ENDPOINT', 'SUPABASE_S3_REGION',
                'SUPABASE_S3_ACCESS_KEY_ID', 'SUPABASE_S3_SECRET_ACCESS_KEY',
                'SUPABASE_STORAGE_BUCKET', 'SMSC_API_KEY', 'SMSC_SENDER')
    for name in required:
        value = str(config.get(name, '')).strip()
        if not value or any(word in value.lower() for word in ('replace_me', 'changeme', 'your_secret')):
            errors.append(f'{name}: missing or placeholder')
    if config.get('GUEST_OTP_PROVIDER') != 'smsc':
        errors.append('GUEST_OTP_PROVIDER: configure smsc before enabling public registration')
    try:
        daily = int(config.get('GUEST_OTP_DAILY_LIMIT', '0'))
    except (ValueError, TypeError):
        daily = 0
    if daily <= 0:
        errors.append('GUEST_OTP_DAILY_LIMIT: positive daily send limit required')
    if config.get('MEDIA_STORAGE') != 'supabase':
        errors.append('MEDIA_STORAGE: configure private S3 (current backend name: supabase)')
    for name, expected in (('PAYMENT_PROVIDER', 'xpayment'), ('XPAYMENT_ENV', 'production'),
                           ('XPAYMENT_API_VERSION', 'v2')):
        if config.get(name) != expected:
            errors.append(f'{name}: expected {expected}')
    for name in ('XPAYMENT_ENABLED', 'XPAYMENT_PROTOCOL_VERIFIED'):
        if str(config.get(name, '')).lower() not in ('true', '1'):
            errors.append(f'{name}: not enabled/verified')
    for name in ('PAYMENTS_PUBLIC_API_ORIGIN', 'PAYMENTS_PUBLIC_SITE_ORIGIN',
                 'PAYMENTS_PUBLIC_STAFF_ORIGIN', 'SUPABASE_S3_ENDPOINT'):
        try:
            value = urlsplit(config.get(name, ''))
            valid = value.scheme == 'https' and value.hostname and not value.username and not value.password
        except ValueError:
            valid = False
        if not valid:
            errors.append(f'{name}: HTTPS URL without credentials required')
    try:
        db = urlsplit(config.get('DATABASE_URL', ''))
        valid_db = db.scheme in ('postgres', 'postgresql') and bool(db.hostname)
    except ValueError:
        valid_db = False
    if not valid_db:
        errors.append('DATABASE_URL: PostgreSQL required')
    if config.get('DB_SSLMODE') not in ('require', 'verify-ca', 'verify-full'):
        errors.append('DB_SSLMODE: encrypted connection required; prefer verify-full + CA')
    if '*' in config.get('ALLOWED_HOSTS', ''):
        errors.append('ALLOWED_HOSTS: wildcard forbidden')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', help='Use backend/.venv Python; never pass secret values as arguments')
    args = parser.parse_args()
    if args.env_file:
        try:
            import environ
            if not os.path.isfile(args.env_file):
                raise ValueError('missing')
            environ.Env.read_env(args.env_file, overwrite=True)
        except Exception:
            print('Cannot load configuration. Use backend/.venv/bin/python and a readable env file.', file=sys.stderr)
            return 2
    errors = failures(os.environ)
    print('OFFLINE CONFIGURATION CHECK — not production readiness or provider verification')
    for error in errors:
        print('BLOCK:', error)
    print('Manual gates: OTP delivery/native flow, data residency/contracts, restore, payment/refund acceptance, clean release SHA.')
    if not errors:
        print('Configuration checks passed. Manual launch gates remain mandatory.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
