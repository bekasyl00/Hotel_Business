# Django API

Current code contains catalogue/reviews/media, guest profiles/stays and analytics in `backend/booking`; demo payments/refunds/receipts in `backend/commerce`; separate native guest/staff device and refresh-token records in `backend/identity`. The same transactional API serves browser and Capacitor iOS clients: `/api/v1` is versioned, `/api` remains a compatibility alias to the same handlers. Product capabilities and proposed backlog: [product.md](product.md). API shape: [api-contract.md](api-contract.md); native authentication: [mobile-api.md](mobile-api.md); operator console: [admin.md](admin.md). This runbook does not certify a cloud deployment; see [verification.md](verification.md) for evidence.

## Local start

Python 3.13+, PostgreSQL 14+ (17 in Compose). Backend uses Django 5.2 LTS and DRF. No SQLite fallback: overlap protection depends on PostgreSQL. Run from repository root:

```sh
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
# Set a random DJANGO_SECRET_KEY in backend/.env; never commit it.
docker compose up -d db
backend/.venv/bin/python backend/manage.py migrate
backend/.venv/bin/python backend/manage.py createsuperuser
backend/.venv/bin/python backend/manage.py seed_demo
backend/.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

`seed_demo` is optional, DEBUG-only and adds illustrative inventory without changing existing records or creating passwords. An empty database supports creating a sanatorium from scratch via the administrator's Vue workspace. A Django superuser is recognised as platform admin. Managers are provisioned through `/staff/accounts` with a unique email and an initial password of at least 12 characters. Password changes invalidate existing authenticated sessions. Disabling an account revokes subsequent access. The actual Django console is [http://127.0.0.1:8000/django-admin/](http://127.0.0.1:8000/django-admin/); `/admin/` redirects there. It requires an active staff superuser, displays current database records and stays read-only to preserve service invariants. `STAFF_WORKSPACE_URL` points its operation links to the API-connected staff application.

In another terminal:

```sh
VITE_DATA_MODE=api npm run dev
```

Open http://127.0.0.1:4173/staff/login. Vite proxies `/api` and `/media` to localhost:8000 in development/preview. Public routes are `/`, `/resorts/:id`, `/rooms/:id`, `/bookings`, `/profile`, `/receipts/:id`; staff analytics is `/staff/analytics`. Demo remains the default for static builds. Do not set API mode on the live Vercel project until its `/api` reaches a deployed server and uploaded files have durable hosting.

Compose API alternative: `docker compose build api`, `docker compose run --rm api python manage.py migrate`, `docker compose up -d api`. Migrations are an explicit deployment step, not something every Gunicorn worker executes. `.env` is excluded from image/git.

## Workflows and ownership

- New website/manual requests: `pending`. Manager/admin can confirm or reject; guest can cancel only their own request/confirmed reservation. Rejected/cancelled are terminal. Past completed stays cannot change status.
- Pending reserves the physical room until processed; no automatic timeout yet. The date interval is `[start,end)`. A checkout and subsequent checkin may be on the same date.
- Anonymous guests can still book with name/phone and an opaque server-session owner. They can register a separate phone/password guest account and keep this browser's existing profile/history. Authenticated guests can recover that history by signing in on another device. Anonymous history is not claimed by matching phone numbers. Session cookies have a 14-day sliding lifetime.
- API checks role and resort on every mutation; manager scope comes from the database, not request payload. No production `/demo/accounts` endpoint.
- Price is integer KZT; room/night + tariff supplement × guests/night, optionally reduced by a tariff discount of 1–90%. The discounted nightly amount is rounded half-up, then multiplied by nights. Existing price and cancellation-time snapshots do not change with catalogue edits.
- UUID `requestId` is mandatory on create. Retry identical payload/key returns the original booking. The frontend preserves that key across failed submission retries, regenerating it only when form data changes.
- Transactions lock the parent resort for consistent inventory/catalog operations. A database GiST exclusion constraint protects the invariant independently. This coarse lock is suitable for the MVP; finer room locks may be introduced after load measurement.
- History is written atomically with application mutations. Passwords/phone are excluded from audit snapshots. Audit has no public mutation endpoints; database administrators can still modify database data. This is not tamper-proof legal logging.
- Workspace returns the full current catalog/bookings and latest 500 scoped audit events/reviews; public reviews are limited to newest 100 approved entries. Payment relations are prefetched and the booking review is joined. Pagination/export is not implemented.

## Reviews, media and simulated payments

Catalogue categories and classes are fixed choices. Staff can edit property/physical-room profiles, descriptions, amenities and media. Reviews require a completed confirmed website stay owned by the guest session; one review per booking, 1–5 rating, text and up to six photos. Scoped staff moderate/reply; only approved reviews are public and contribute to rating. This is not a general comments/chat system.

Uploads use ordinary multipart file selection. Every new file has a `MediaAsset` record containing its purpose, owner/scope, MIME type, stored size and internal storage key. `POST /media` accepts staff catalogue images/video with `resortId`, or eligible guest review photos with `bookingId`. `POST /profile/avatar` accepts an authenticated guest's image; `DELETE /profile/avatar` removes its profile reference. Both avatar actions return `{profile}` and are audited. Anonymous sessions cannot change an avatar. Profile responses include `avatarUrl`.

JPEG/PNG/WebP images are limited to 8 MiB/20 MP, decoded, resized to at most 2400 px, re-encoded to JPEG and stripped of EXIF. Staff catalogue video supports MP4/WebM up to 40 MiB with basic container-header checks; duration, codecs, transcoding and malware analysis remain outstanding. A streaming upload handler stops files over 40 MiB and multipart file content over 50 MiB before filling temporary storage. Rolling 24-hour quotas count stored bytes and at most 100 assets per scope: by default 500 MiB per resort catalogue and 50 MiB per guest avatar profile or review booking. Configure `MEDIA_RESORT_DAILY_BYTES` and `MEDIA_GUEST_DAILY_BYTES` for operational limits. These are bounded upload limits, not a total lifetime storage quota.

Default `MEDIA_STORAGE=local` writes new files to private `backend/private-media`, outside the legacy public `/media` directory. API responses store stable `/api/media/files/:id` references. Every read rechecks visibility: published and attached active catalogue media may be public; review photos become public only with an approved review at a published property; the owner and permitted staff can view their own restricted uploads. Avatars are visible to their guest owner and authorized staff linked to that guest's booking, plus platform administrators. Old replaced avatars and detached public catalogue media are no longer publicly served. Local delivery supports byte ranges for video and sends `private, no-store`/`nosniff`; the legacy DEBUG `/media` route serves only old illustrative uploads.

`MEDIA_STORAGE=supabase` configures Django storage through the Supabase S3 interface and a **private** bucket. The same API access checks run before issuing a redirect to a signed URL valid for 60 seconds. Whoever possesses that short-lived URL can fetch the object until expiry; account revocation cannot invalidate an already issued URL sooner. Storage keys and credentials are server-only, and expiring URLs are never persisted as catalog/profile references. Cloud configuration is prepared but no live Supabase connection or upload has been established; [supabase.md](supabase.md) records configuration and verification steps.

Catalogue/review saves validate `MediaAsset` scope, kind and booking ownership before accepting its reference. Existing illustrative HTTPS/asset URLs remain supported for compatibility; the editor's normal path uses file upload. `cleanup_media` lists metadata-backed, unreferenced uploads older than 24 hours; `cleanup_media --delete` removes those files and records under the same owner locks used by mutations. Referenced media is retained. Schedule this command only after verifying the dry-run in the intended environment. Reconciliation of storage objects without metadata, full retention policy, total-storage quotas and recovery tests remain production work; database and object storage do not share an atomic transaction.

`commerce` stores DemoPayment/DemoRefund. The interface calls this Kaspi demo, but it is an internal simulator without official Kaspi API credentials or network calls. Website owners can simulate success/failure after manager confirmation and before the frozen check-in timestamp. UUID idempotency, a per-booking successful-payment constraint and the parent-resort lock prevent duplicate charges in the simulator.

Cancellation policy is fixed at booking creation using the property's time and IANA timezone. At least 48 hours before check-in returns 100%; 24 to less than 48 returns 70%; less than 24 returns 0%. The same rule applies to guest/staff cancellation. Amount is rounded down to integer KZT. Cancellation releases inventory independently of refund eligibility. `transition_booking` saves status, cancellation snapshot, simulated refund and audit in one transaction. Legacy bookings without terms use 14:00 Asia/Almaty. Refund preview is informational; the server recomputes at cancellation time, then preserves the finalized result.

## Analytics, guest profiles and receipts

`booking/analytics.py` computes scoped event aggregates in PostgreSQL, including previous equal-length periods and zero-filled daily/weekly/monthly series. Booked amount includes all created requests and is not revenue. Successful payment and refund events use their own timestamps; net receipts can be negative and are not profit. Reviews count all created records while average uses approved ones. Top500 breakdowns do not truncate totals. No expense accounting exists. Browser demo has an equivalent array adapter, with an explicit incomplete-history flag for legacy refunds lacking dates.

GuestProfile remains the contact/history record; GuestAccount optionally links it to phone/password authentication. GET/PATCH /profile expose only the resolved anonymous/authenticated guest owner; staff /guests/:id require a booking in their scope and filter the booking history accordingly. An authenticated profile's phone must equal the normalized account phone; changing it requires a future separate OTP flow. Booking contact snapshots do not overwrite this verified profile phone. Confirmed paid bookings can be checked in during their dates and checked out after arrival. Check-in/out timestamps are audited; checked-in bookings cannot be cancelled. Checkout does not shorten inventory dates or trigger a refund.

Successful DemoPayment stores a receipt JSON snapshot at creation. Authorized guest/scoped staff can read JSON or download an attachment PDF; both responses are no-store. Receipt omits phone and embeds explicit demo/non-fiscal notice. Refund appears separately without rewriting original paid amount. Existing paid rows are frozen on first authorized read with legacySnapshot:true; current address/missing metadata fallback is disclosed. ReportLab is pinned in requirements; Noto Sans Regular/Bold/OFL licence are in commerce/fonts. Static demo PDF uses a copy of the OFL font in public/assets/fonts.

The user requires a real receipt **from Kaspi** in the eventual integration. Generated PDFs here have source:demo and are not provider receipts. Real delivery must store the official provider's receipt file/URL after verified payment; that integration is not connected. A downloaded/shared file may contain guest name and booking details; there is no unauthenticated share URL or automatic delivery to others.

## Guest phone authentication API

`booking/guest_auth.py` implements guest accounts separately from staff `User`; signing in as a guest never grants a staff role. Staff email/password `/auth/*` remains separate. Migration `0004_guest_phone_auth` adds GuestAccount and short-lived GuestChallenge records. Guest account IDs, profile IDs and opaque ownership secrets are distinct; owners/password hashes/OTP hashes are never returned by the API.

All paths below have `/api` prefix and use the existing CSRF handshake. Every response is `no-store`. After successful register/login/logout, obtain a fresh CSRF token because session identifiers and CSRF tokens rotate. The `mode` field is `demo` only when **both** `DEBUG=True` and `GUEST_AUTH_DEMO_OTP=True`; otherwise it is `disabled`. `.env.example` opts into this local demonstration. Neither flag is a substitute for real SMS verification.

| Method/path | Request | Response |
| --- | --- | --- |
| GET `/guest-auth/session` | — | `{authenticated,account:{id,phone}\|null,profile:{id,name,phone,avatarUrl,version,createdAt,updatedAt}\|null,mode}` |
| POST `/guest-auth/challenges` | `{phone,purpose:"register"\|"reset"}` | `{challengeId,expiresAt,retryAfterSeconds:60,mode:"demo",demoCode,message}` |
| POST `/guest-auth/register` | `{challengeId,code,name,password}` | Same authenticated session object, HTTP 201 |
| POST `/guest-auth/login` | `{phone,password}` | Same authenticated session object, HTTP 200 |
| POST `/guest-auth/reset` | `{challengeId,code,password}` | `{ok:true,mode:"demo"}`; no automatic sign-in |
| POST `/guest-auth/logout` | `{}` | Anonymous session object, HTTP 200 |

Phone input accepts Kazakhstan mobile **format** `+77` followed by nine digits. Spaces, parentheses and hyphens are removed; an eleven-digit number starting `8` is normalized to `+7`. This is format checking, not carrier/ownership verification. Registration requires a name of 1–80 characters and a password of 12–128 characters passing Django's common/numeric-password validation. Unknown fields such as client-supplied roles/owners are rejected. Password and OTP are stored using Django password hashing; neither is written to audit. Guest auth errors return `code` plus Russian `message`/`fields`; frontend translations may map `phone_invalid`, `weak_password`, `name_invalid`, `invalid_request`, `invalid_credentials`, `invalid_code`, `code_expired`, `resend_cooldown`, `rate_limited`, `sms_unavailable`, `already_authenticated`, `phone_change_requires_verification`, `method_not_allowed`, and `not_found`.

Codes are random six-digit strings, valid for five minutes, single use, with at most five verification attempts. A challenge is bound to its initiating browser and purpose. Resending after 60 seconds invalidates previous unused codes for that phone/purpose. PostgreSQL row locks serialize concurrent sends/redemption; failed-code attempts are committed even though the API returns an error. Shared PostgreSQL limits count requests across workers: code requests at most 5 per phone / 30 per IP per hour, login 10 per phone / 30 per IP per 15 minutes, redemption 60 per IP per 15 minutes. Cooldown requests also count. The backend deliberately uses `REMOTE_ADDR`, not untrusted forwarded headers.

Initial registration adopts only the current anonymous profile and its associated website bookings in one transaction. It rotates the profile's opaque owner and rewrites those booking owners so an old anonymous session cookie cannot keep access. It never searches/merges history by phone. Existing-account login selects that account's owner without attaching the current browser's unrelated history. Logout/account switching clears the previous guest identity; staff authentication is unaffected by guest logout. Password reset increments `auth_version`; every subsequent guest ownership check validates the session version, including bookings, reviews, payments and receipt JSON/PDF access. In-flight operations already authorized before a reset may complete. Reset responses/challenge envelopes are generic for existing and unknown accounts; an unknown phone's valid reset challenge returns the same success response without creating an account.

**Demo delivery is not SMS.** `DemoCodeDelivery.send_code(phone, code)` returns `demoCode` only under the explicit two-setting guard. Registration/reset requests, including previously issued code redemption, fail closed with HTTP 503 `sms_unavailable` when the guard is off. Existing accounts may still sign in with their password. `code_delivery()` is the integration seam for a future verified SMS provider; no provider SDK/network call/credentials are configured. Real production rollout must replace this adapter, hide codes entirely, add verified delivery/error handling and edge abuse protection, and configure expiry cleanup/retention of challenge and throttle records. The current development demonstration does not prove possession of the telephone number and must not contain real personal data.

### Mobile application foundation

`booking/mobile_auth.py` exposes JSON login/refresh/logout plus device-session listing and revocation; `identity` persists devices and consumed refresh-token hashes. Access tokens are opaque, expire after 15 minutes and are stored only as HMAC-SHA256 hashes on the server. Each login creates a token family with an absolute 30-day lifetime. Refresh rotates both credentials, invalidates the previous access token and retains the consumed refresh hash. Reusing a consumed refresh token revokes its entire family. Password reset and account deactivation invalidate native access as well as browser sessions. See [mobile-api.md](mobile-api.md) for the precise request/response contract and retry behavior.

Native clients use `Authorization: Bearer ...` with the same `/api/v1` guest profiles, bookings, media, reviews, payments and receipt handlers. Guest identity never becomes a staff `User`; even a simultaneous staff cookie cannot elevate a guest Bearer request. Invalid Authorization fails closed instead of selecting a cookie or anonymous owner. Web writes retain CSRF; the exemption for ordinary API mutations is conditional on a valid explicit Bearer credential. Native credential endpoints do not authenticate through cookies. Login limits are shared across web/native; refresh is rate-limited in PostgreSQL. Run `cleanup_mobile_sessions` on a schedule to remove expired families; consumed hashes must survive until family expiry for replay detection.

Separate Capacitor iOS apps and Keychain storage are implemented; see [ios.md](ios.md). Guest login currently requires an existing account; registration/recovery still use the browser-bound OTP flow. Real SMS, native challenge transport, account deletion, push, device attestation and physical-device/store release testing remain outstanding. Staff-native credentials use separate models/endpoints and expire after a 12-hour absolute family lifetime; see [mobile-api.md](mobile-api.md). `deviceName` is a display label rather than cryptographic binding. `Accept-Language` is accepted as a request header, but stable error codes drive frontend localization; backend messages currently remain Russian. No OAuth/OpenID provider is configured.

### PostgreSQL and Supabase configuration

`config/infrastructure.py` enforces PostgreSQL, connection health checks and a 10-second connection timeout. `DB_SCHEMA` optionally selects a dedicated non-public application schema; `DB_SSLMODE` and `DB_SSLROOTCERT` configure certificate verification. `DB_TRANSACTION_POOLER=True` disables server-side cursors/prepared statements and persistent Django connections for transaction-pool compatibility; direct or session-pooled connections retain the usual behavior. Database extensions and schema permissions must be provisioned before migrations; connection options do not create them. The app continues to use Django auth/ownership and SQL transactions, not Supabase Auth or direct browser writes.

The supplied Supabase project `https://uchqzxxqioixhzbnwcak.supabase.co` now has a verified private tynys schema (25 tables, 26 Django migration records), RLS/client access restrictions and the private tynys-private bucket in ap-northeast-2. Application credentials, a least-privileged runtime role and live Django SQL/S3 connectivity are **not verified**. Local development and tests still use local PostgreSQL. Follow [supabase.md](supabase.md) to configure the actual database and private file storage without putting secrets in Git or frontend variables.

## Security and deployment

CSRF: first obtain `GET /api/auth/csrf`, send `X-CSRFToken` on writes including login, refresh token after login/logout. HttpOnly session cookie; Secure cookies and HTTPS redirect when DEBUG=False. Serve frontend and API under one origin, e.g. `/` static assets and `/api` reverse proxied to Gunicorn. No wildcard CORS. Set `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `TRUST_PROXY=True` only behind a trusted proxy that replaces forwarded headers. Never expose the database port publicly.

Staff login attempts are limited in PostgreSQL across workers (30 per account/IP per 15 minutes); guest limits are documented above. At a trusted reverse proxy configure client IP forwarding/edge rate limits explicitly; the app intentionally does not trust arbitrary X-Forwarded-For. Add edge abuse protection, verify the configured rolling upload limits and define total-storage quotas before public guest traffic. No real payments, SMS or email delivery are included. Guest registration/recovery currently uses explicit demo codes only. Staff password reset is performed by platform administrator through the account editor (superuser recovery via `changepassword`).

For production: use unique strong secrets/passwords, DEBUG=False, a least-privilege application DB user, a separate migration role able to install `btree_gist`, HTTPS, automatic backups with a tested restore, monitoring and a real catalogue. Compose defaults are local development only. `collectstatic --noinput` prepares the technical Django admin assets. The custom console includes searchable catalog, bookings, guests, reviews, media metadata, staff, audit, demo payments/refunds and current count cards. It is superuser-only and read-only, including staff accounts; passwords, token hashes, OTP records, ownership secrets and private storage keys are excluded. Its login has a separate shared-database limit of 30 attempts per account/IP in 15 minutes. See [admin.md](admin.md) for operator setup and remaining MFA/read-access auditing gaps.

## Verification

```sh
backend/.venv/bin/python backend/manage.py check
backend/.venv/bin/python backend/manage.py makemigrations --check --dry-run
backend/.venv/bin/python backend/manage.py collectstatic --noinput
backend/.venv/bin/python backend/manage.py test booking commerce
npm test
npm run build
npm run arch:check
```

The test DB is isolated by Django (`test_` prefix). Test role needs CREATEDB; never point tests at production credentials. Concurrent requests are tested with independent database connections.
