# Django Admin

Django has a separate administrative website at `/django-admin/` on the **backend** host. Locally: [http://127.0.0.1:8000/django-admin/](http://127.0.0.1:8000/django-admin/). It is rendered by Django and uses its database; it is not part of either Vercel static build. This address requires a running backend. A public cloud address exists only after backend deployment.

The console is for platform superusers. A manager or ordinary account with `role=admin` cannot enter, even with `is_staff=True`. Resort managers use the separate Vue staff site, whose API scopes access to their resort. The Django console retains normal session authentication and CSRF protection; it does not accept guest mobile tokens. Its login is limited by shared PostgreSQL counters to 30 attempts per account and IP in 15 minutes. Forwarded IP headers are not trusted; configure edge abuse protection at the reverse proxy as well.

Create the first operator interactively on the backend host:

```sh
backend/.venv/bin/python backend/manage.py createsuperuser
```

The command asks for email, username and password. Passwords are never saved in documentation. To recover a superuser password, run `manage.py changepassword <email>` interactively. Use `collectstatic --noinput` as part of backend deployment so admin styles are available.

## What is available

The dashboard reads current database counts: published properties, pending booking requests, guests currently checked in, reviews pending moderation and active guest accounts. Each count opens a filtered list. Search, filters, date navigation and pagination are available for catalog records, bookings, guest profiles/accounts, staff, reviews, uploaded-file metadata, audit events, demo payments and refunds. Related records link to their details; booking terms and payment/refund snapshots are shown without altering them. Avatar links open file metadata; private storage keys are not exposed.

The console is intentionally **read-only**, including staff accounts. Creation, changes, booking decisions, check-in/out, review moderation and account provisioning go through the Vue workspace and transactional backend services. This avoids a second write path bypassing inventory locks, cancellation/refund rules, record versions or audit. Bulk deletion is unavailable. Superuser administration is performed with the management commands above. A future editable Django Admin must call those same services and have equivalent invariant tests.

`STAFF_WORKSPACE_URL` points to the service-backed staff application, including `/staff` (for example `http://127.0.0.1:4173/staff`). Configure this to an API-connected staff deployment in production. Linking a static demo does **not** synchronize it with the database. If no valid URL is configured, navigation links are omitted.

Password hashes, ownership secrets, OTP challenges and throttle keys are not exposed in the console. Payment sections are explicitly simulation records, not real bank transactions. The superuser can view guest contact details across properties, so access must be restricted to authorized platform operators. MFA/SSO and operator-specific audit of read access are not implemented.

## Verification

`backend/.venv/bin/python backend/manage.py test booking.test_admin` uses real PostgreSQL and verifies superuser access, manager rejection, CSRF, dashboard counts/filter links, model pages/search, forbidden writes/deletes, escaping and absence of authentication secrets. This test does not establish a cloud deployment or real payment connectivity.
