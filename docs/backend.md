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

- New website/manual orders: `pending` with a bounded payment hold. Successful server-side online payment confirms atomically; staff cannot manually confirm/reject. Expired/cancelled holds release inventory; checked-in stays and bookings with recorded onsite collection cannot be cancelled through the normal workflow. Provider deployment evidence is maintained separately in verification.md.
- Pending reserves the physical room until the server hold deadline; availability ignores elapsed holds and expiry jobs persist their transition. The date interval is `[start,end)`. A checkout and subsequent checkin may be on the same date.
- New guest bookings require an active GuestAccount; contact name/phone come from its profile/account. An opaque anonymous owner supports legacy browser history only. Registration adopts only this browser's own history, never another history matched by phone. Session cookies have a 14-day sliding lifetime.
- API checks role and resort on every mutation; manager scope comes from the database, not request payload. No production `/demo/accounts` endpoint.
- Accommodation price is integer KZT, calculated per night from seasonal room price plus chargeable guests' tariff supplement and optional tariff discount, then summed. The separately frozen booking fee is added on top and collected online; accommodation is collected at the property. Existing price, payment and cancellation-time snapshots do not change with catalogue edits.
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

`commerce` stores DemoPayment/DemoRefund separately from real provider attempts/events. When the simulator is explicitly enabled, website owners can simulate success/failure while the payment hold is valid and before the frozen check-in timestamp. It has no bank calls and confirms pending orders directly. UUID idempotency, a per-booking successful-payment constraint and the parent-resort lock prevent duplicate simulator payments.

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

Phone input accepts Kazakhstan mobile **format** `+77` followed by nine digits. Spaces, parentheses and hyphens are removed; an eleven-digit number starting `8` is normalized to `+7`. This is format checking, not carrier/ownership verification. Registration requires a name of 1–80 characters and a guest password of 8–128 characters with no composition requirement (registration and reset; staff policy unchanged). Unknown fields such as client-supplied roles/owners are rejected. Password and OTP are stored using Django password hashing; neither is written to audit. Guest auth errors return `code` plus Russian `message`/`fields`; frontend translations may map `phone_invalid`, `weak_password`, `name_invalid`, `invalid_request`, `invalid_credentials`, `invalid_code`, `code_expired`, `resend_cooldown`, `rate_limited`, `sms_unavailable`, `already_authenticated`, `phone_change_requires_verification`, `method_not_allowed`, and `not_found`.

Codes are random six-digit strings, valid for five minutes, single use, with at most five verification attempts. A challenge is bound to its initiating browser and purpose. Resending after 60 seconds invalidates previous unused codes for that phone/purpose. PostgreSQL row locks serialize concurrent sends/redemption; failed-code attempts are committed even though the API returns an error. Shared PostgreSQL limits count requests across workers: code requests at most 5 per phone / 30 per IP per hour, login 10 per phone / 30 per IP per 15 minutes, redemption 60 per IP per 15 minutes. Cooldown requests also count. The backend deliberately uses `REMOTE_ADDR`, not untrusted forwarded headers.

Initial registration adopts only the current anonymous profile and its associated website bookings in one transaction. It rotates the profile's opaque owner and rewrites those booking owners so an old anonymous session cookie cannot keep access. It never searches/merges history by phone. Existing-account login selects that account's owner without attaching the current browser's unrelated history. Logout/account switching clears the previous guest identity; staff authentication is unaffected by guest logout. Password reset increments `auth_version`; every subsequent guest ownership check validates the session version, including bookings, reviews, payments and receipt JSON/PDF access. In-flight operations already authorized before a reset may complete. Reset responses/challenge envelopes are generic for existing and unknown accounts; an unknown phone's valid reset challenge returns the same success response without creating an account.

**Demo delivery is not SMS.** `DemoCodeDelivery.send_code(phone, code)` returns `demoCode` only under the explicit two-setting guard. Challenge-based registration/reset requests, including previously issued code redemption, fail closed with HTTP 503 `sms_unavailable` when the guard is off. The separately enabled temporary direct registration below does not use or bypass challenge redemption. Existing accounts may still sign in with their password. `code_delivery()` is the integration seam for a future verified SMS provider; no provider SDK/network call/credentials are configured. Real production rollout must replace this adapter, hide codes entirely, add verified delivery/error handling and edge abuse protection, and configure expiry cleanup/retention of challenge and throttle records. The current development demonstration does not prove possession of the telephone number and must not contain real personal data.

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


## Seasonal prices, child policies and probes (27 October 2026)

Migrations 0006/0007 add RoomPricePeriod (date range + GiST exclusion, parent Room) and opt-in tariff child policy; additive changes only, no rewriting existing bookings. Apply with `migrate` after backup/rehearsal. The new period serializer is called through the existing transactional service and resort lock. See `booking/pricing.py`, `booking/test_pricing.py` and the API contract for nullable nightly prices. Local migration is not deployment to Supabase. To roll back in production, first disable new writes and deploy a compatible forward migration; do not drop booked price snapshots. Rehearse migrations with production-sized data before real deployment (not done here).

`/health/live` and `/health/ready` are separate process/DB checks; see [sre.md](sre.md). Readiness SQL timeout is one second, connect_timeout is ten seconds. Cloud monitoring and alerts are not configured by these endpoints.

## Payment-first checkout and commission

Booking migration 0008 adds nullable per-resort commission and indexed hold_expires_at, plus expired status; existing rows/snapshots are retained. Configure BOOKING_HOLD_MINUTES (default 15; 1–120). Schedule `backend/.venv/bin/python backend/manage.py expire_payment_holds` every minute and monitor lag. New booking/payment writes also handle stale holds. Durable provider jobs and reconciliation have a separate scheduler; monitor both expiry and delivery. Null expiry on historical records is intentionally retained until an explicit migration policy is agreed; do not silently release legacy inventory.

Manual confirmation/rejection is no longer supported. Demo payment creates payment + confirmed status + receipt + audit atomically. For staff-created simulator orders use the scoped /payments/demo/staff endpoint. Only platform admin sets commissionPercent; public catalogue exposes read-only bookingFeePercent while staff-only commissionTerms remain hidden from guests. Automatic bank splits/payouts are not implemented.


## Staff planner contract (2026-11-04)

Migration 0009 adds private `Booking.staff_notes` and permits null protected tariff references. New staff orders can omit `tariffId` to use seasonal/base room-only pricing; guest orders still require it. Explicit legacy tariff input remains supported. No historical data is rewritten. `pricingBasis=room|tariff` is frozen in new snapshots. Receipts and readonly Django Admin accept null tariff.

`POST /bookings/:id/notes` is a service-backed staff-only mutation with version/tenant checks, resort lock, CSRF for browser sessions and transactional redacted audit. Guest output omits `staffNotes`. Both `/api` and `/api/v1` route to the same handler. Apply the migration before deploying the new server. After room-only bookings exist, rollback to a non-null tariff would fail; preserve history and deploy forward fixes. Local tests do not constitute a Supabase migration or a production load test.


## Общее sandbox окружение, 05.11.2026

Django, Supabase PostgreSQL/private S3 и scheduler подключены. Актуальная конфигурация, ограничения и статус банковской приёмки: [halyk-sandbox.md](halyk-sandbox.md). Более ранние записи о неподключённом runtime ниже/выше относятся к предыдущему этапу. Не считать staging production-ready.

## XPayment / Kaspi: подготовка до регистрации, 06.11.2026

[Настройка XPayment](xpayment-integration.md) описывает серверный ключ устройства, account UUID, webhook secret и условия включения. Провайдер новых попыток выбирается через `PAYMENT_PROVIDER=xpayment`; `XPAYMENT_ENABLED` и `XPAYMENT_PROTOCOL_VERIFIED` по умолчанию false. Опубликованного денежного sandbox не найдено: это подготовка закрытого production-адаптера, а не новый симулятор. Halyk sandbox и исторический demo сохраняются как отдельные источники.

Сохранённая попытка определяет провайдер/окружение/merchant scope для очереди, а не текущий выбор нового checkout. Один банковский attempt на бронь, resort lock, frozen amount, owner/tenant checks и independent server verification остаются общими. XPayment webhook проверяет HMAC исходного тела, долговечно дедуплицирует delivery и лишь ставит сверку; тестовый подписанный callback не подтверждает бронь. Неизвестный исход создания/возврата не разрешает повтор POST без доказанной идемпотентности. Секреты и полные внешние payload не попадают в audit/logs.

Подключение рассчитано на один аккаунт получателя. Реальные multi-resort settlements, split, комиссия банка/платформы и провайдерский чек ещё требуют R01/R16–R19. HTTP 202 возврата фиксирует принятие запроса, а не перевод денег. Регистрация, банковская приёмка и облачный деплой этого расширения не доказываются наличием кода; результаты и ограничения записываются в [verification.md](verification.md).


## Accounting module
`commerce/accounting` owns scoped financial reads, sanitized XLSX templates, PDF rendering and versioned accounting documents. Role `accountant` is assigned by a platform admin and uses the separate `/staff/accounting` web page. Existing manager endpoints reject it; tenant access is enforced in services. PostgreSQL migrations booking/0010 and commerce/0005 add role metadata and three accounting tables. Domain mutations remain in service transactions; Django Admin shows document/company metadata read-only. See api-contract.md and production-readiness.md R20 for unsigned-document/ESF/cash limitations.

For private Supabase deployments, new tables must retain the existing schema boundary: enable RLS and revoke anon/authenticated grants using the Django owning role. The connector's migration role may not own Django-created tables. This rollout applied those restrictions to commerce_accountingcompany, commerce_accountingdocument, commerce_accountingsequence and commerce_webhookdelivery and checked them through pg_class/has_table_privilege. Django remains the authorization boundary, using its private schema owner; RLS owner bypass is not claimed as per-tenant protection.


## Current checkout / finance changes, 2026-11-08

New guest booking requires GuestAccount and server-owned profile contacts; default BOOKING_HOLD_MINUTES=15 (older deadlines unchanged). User-requested demo 12-digit child entry is local only, unverified first-six DOB assumption, no checkbox. API rejects full IIN; DOB discarded after server age validation. SMS remains disabled on the public staging environment until a real delivery provider is connected.

Accountant is now platform-wide. Explicit read access to workspace/analytics does not grant catalogue/booking/user mutations. `commerce/accounting/reporting.py` uses grouped database aggregates (not one query per resort). `expenses.py` provides idempotent manual expense creation/versioned void. Migration commerce/0006 adds its table and RLS. Technical admin exposes expense metadata read-only. See [accounting guide](accounting.md) for UI, calculation boundaries and export semantics.

### Partner ownership (2026-11-08)
Migration booking.0011 backfills Resort.account and makes it NOT NULL/PROTECT. Preflight requires existing managers or an active platform administrator for all existing resorts. Run migration immediately before API rollout; prior API cannot create a resort under the new non-null constraint. User.resort is deprecated for authorization. Role/ownership updates serialize with pg_advisory_xact_lock(74696879); operational scope checks in atomic services lock the target resort. Owners' User.version changes revoke native staff tokens. Django Admin remains read-only and shows the responsible account.

Guest directory is booking/directory.py, platform-admin-only. Guest status changes revoke all earlier guest credentials using auth_version. They do not cancel bookings or erase documents. Disabling a staff owner preserves the FK and requires admin reassignment for a replacement operator.


## Temporary phone/password registration — 08.11.2026

The owner requested usable signup while SMS is pending. `GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION` defaults to false; explicitly setting it true exposes direct phone/name/password signup at the existing `/guest-auth/register`. DEBUG and `GUEST_AUTH_DEMO_OTP` remain false in a public deployment. SMS challenge code is preserved, not commented out or removed. Turning this switch off restores the previous challenge-only registration and does not prevent password login for existing accounts.

`booking.0012_guest_phone_verification` adds nullable `phone_verified_at`; existing accounts and all demo/no-SMS registrations remain unverified. Web/native account responses expose only `phoneVerified`, not the timestamp. Registration UI discovers `registrationMode` and displays the direct form plus a temporary-mode explanation. Profile UI no longer claims every number is verified.

Direct signup requires CSRF and an exact phone/name/password body. Per-phone (5/hour) and IP (20/hour) signup limits commit independently of account transactions; phone and profile row locks plus database uniqueness prevent duplicate identities or overwriting another account. Only the current browser-owned profile may be adopted; matching a phone never imports unrelated history. Normal password hashing, 8–128 character policy, session/owner rotation and guest/staff isolation apply.

Password reset still requires a valid purpose-bound, single-use challenge from configured delivery. Without SMS, the public UI explains that recovery is unavailable; no phone-only or shared-code reset exists. Real SMS integration must implement delivery/capability reporting, mark genuine verification, handle number changes and resolve unverified-number claims without disclosing another person's history. Native signup/reset remain web-only; installed apps were not rebuilt.

## Booking fee, property collection and profiles — 2026-11-08

`commerce/settlement.py` freezes `paymentTerms` v1 when `booking/services.py` creates an order. The existing admin-only `Resort.commission_percent` is now a markup above accommodation: base 280000 KZT at 10% produces online fee 28000, onsite amount 280000 and customer total 308000. It is not a deposit deducted from base. The rate must be positive and configured, and the half-up rounded fee at least 1 KZT; otherwise creation returns a specific 409. A public read-only `bookingFeePercent` supports a price preview, but the server recomputes and freezes the amount under the resort lock. Top-level booking.total/nightlyBreakdown keep accommodation values for compatibility.

Snapshots without paymentTerms derive a v0 full-online agreement; neither their saved JSON nor existing attempts/receipts are rewritten. New bank/demo checkout takes the frozen online amount. Successful verified collection confirms the room reservation; the existing 100%/70%/0% cancellation schedule applies to that collected fee only. New commissionTerms use basis=accommodation_markup and resortAmount=base, still marked estimate rather than bank settlement. Admin changes affect future orders only.

`commerce/vouchers.py` supplies owned JSON/PDF booking tickets at `/bookings/:id/voucher[/pdf]`. Guests use existing guest_owner checks; managers use resort ownership; admin/accountant have platform read scope. Verified paid and refunded history remains downloadable, with invalid status for cancelled bookings. The generated document explicitly identifies itself as a booking ticket, not a provider/fiscal receipt. It separates original online payment, refund and onsite amount; no public unauthenticated share URL is created.

The same module records `/bookings/:id/onsite-payment` from exactly version/method/received. Only admin/owning manager can attest cash/card collection, for a confirmed paid reservation in its local stay dates before checkout. Amount comes exclusively from the frozen agreement. OneToOne uniqueness plus the parent-resort lock gives one record/audit; repeating the same method returns it, changing method conflicts. The first write checks/increments booking.version. Accountant has read access only to this operation. Recording blocks ordinary cancellation; check-in for new split-collection orders requires recorded onsite payment. This is a staff attestation, not an API transfer, cash ledger or independently verified receipt; no edit/delete workflow is exposed.

`PAYMENTS_INLINE_CHECKOUT` defaults to false. If explicitly enabled, a checkout request can execute one eligible leased create job after commit, and refresh can execute one verify/refund_verify job. External HTTP still runs outside the inventory transaction. The durable queue, mark-before-send uncertainty handling and scheduler recovery remain authoritative; enabling the flag neither permits duplicate POSTs nor guarantees provider latency. Keep scheduler, worker failure and reconciliation monitoring enabled.

Accounting invoice/act amounts and VAT remain based on accommodation. For v1 their paidAmount uses OnsiteSettlement; platform fee paid/refunded amounts and full customer total have separate snapshot fields. Release requires the exact frozen onsite collection plus the existing checkout/requisites/online-payment checks. Released copies remain immutable. Finance awaiting-payment totals use the online fee; onsiteDue/onsiteRecorded are separate booking-cohort measures, excluded from platform received/net. Legacy full-online records retain their original meaning; PKO/registered ESF and bank payouts are not enabled by this change.

Migration `booking.0013_catalog_profile_content` adds optional second descriptions to resort/room plus property WhatsApp/2GIS contacts. Existing description remains the first block, followed by the media gallery and descriptionAfter. Empty defaults preserve old pages. Contact validation normalizes an international digit phone and permits only HTTPS 2gis.kz/2gis.com exact hosts (including www); existing tenant/version/media checks apply. These fields and seasonal room pricePeriods are available from uncached public catalogue/profile responses.

Migration `commerce.0008_onsite_settlement` depends on booking.0013 and creates the protected per-booking collection record. Apply both before serving the new serializers/endpoints, and enforce the existing private PostgreSQL boundary for the new table: RLS enabled, anon/authenticated grants revoked, private Django role only. No booking or released document backfill is needed. Preserve new records when rolling forward from a failure; do not drop financial history. Source/migration preparation alone does not prove Supabase application or deployment; consult verification.md for observed rollout state.

## Private document guest data — 2026-11-08

`commerce/accounting/document_guests.py` owns a booking-bound staff form for each occupant's name/IIN and the selected payer's document requisites. GET/PUT `/bookings/:id/document-guests` grants active admin, owning manager and platform accountant explicit access, independently of ordinary booking/profile output. There is no guest self-service endpoint. Writes lock the resort, validate a separate roster version and audit only version/count/field names. Reads use the same ownership lock and metadata-only audit. Missing draft fields are permitted; issue/release requires all occupants' names/12-digit IINs plus a selected buyer/address. A 12-digit string is not verified identity. Existing PKO cash-accounting restriction remains.

Migration `commerce.0009_document_guest_roster` adds DocumentGuestRoster with protected OneToOne booking, ciphertext, version, updated_by and timestamp. It enables RLS and revokes PUBLIC plus existing anon/authenticated role grants. Django's private database role is still the authorization boundary; database-owner RLS bypass is not tenant security. New data never enters Booking.snapshot, GuestProfile, workspace/public serializers or audit payloads.

`accounting/private_data.py` uses pinned cryptography/Fernet authenticated encryption for the whole roster and the selected-buyer portion of document snapshots. Configure server-only `DOCUMENT_DATA_ENCRYPTION_KEYS` as a comma-separated list of URL-safe base64-encoded 32-byte Fernet keys. The first key encrypts new values; all listed keys can decrypt old values. No default, browser key, SECRET_KEY derivation or plaintext fallback exists. Keep key material only in protected server config, separately backed up from the database. Keep old keys until all retained roster and immutable document ciphertext can still be decrypted; removing a key makes its records unavailable. Key rotation here does not rewrite historical issued documents.

The selected buyer snapshot is context-bound to booking ID/document number; the roster is bound to its booking ID. Normal authorized PDF/XLSX rendering decrypts in memory, maps the buyer to the supplied invoice/act/PKO cells and never copies other occupants' identities to exports. Draft refresh/release takes a fresh encrypted buyer snapshot; published copies keep the old one. An authorized downloaded file necessarily contains buyer personal data; no public sharing URL or browser persistence is added. Missing key/unreadable data fails closed with generic503. Establish retention, lawful processing and operating access procedures before collecting real document data; encryption is not a claim of complete compliance.

The public booking form does not collect these document requisites. This stored, staff-entered IIN is isolated from child-age calculation and does not replace authentication or provider receipt evidence. Test fixtures and preview exports use entirely fictional identities. Apply the encryption configuration and migration before rolling out the endpoint; no legacy document backfill is performed.


## Child category and opt-in update — 2026-11-08

Apply `booking.0014_children_under_two_free` before deploying the new tariff serializers. It renames the model field while explicitly retaining the physical `children_under_three_free` database column and configured values; old/new runtime SQL remains compatible during deployment. it does not update Booking/receipt snapshot JSON. New quote snapshots use pricingVersion3 and childrenUnderTwoFree. The declared child category is 0–13 at check-in; only ages0–1 receive an enabled tariff-supplement exemption. Room price/capacity/adult requirements are unchanged. Versioned PATCH /tariffs/:id supports the small staff policy form and retains existing tenant/audit permissions.

Children count entry no longer clamps to the current room. It retains the requested party, selects a supplied larger active room with a visible notice when possible, or disables booking with an explicit capacity error and a link to find another room. Full checkout IIN stays transient component input; only the derived birth date is sent, discarded after server age validation. Historical under-three snapshots retain their original meaning. Installed native bundles are deferred; server validation remains authoritative until their next rebuild.


## Class-wide seasonal price operation — 2026-11-09

`booking/class_pricing.py` exposes the scoped preview/apply operation described in the API contract. It reuses RoomPricePeriod and the existing resort lock; no schema migration or data backfill is needed. Application compares the exact selected class membership and room/resort versions before any mutation, validates every room's overlap/period limit, then bulk-inserts periods and increments room versions in one transaction. A concurrent duplicate succeeds once; the other attempt sees stale versions. Per-room writes take the same resort lock and PostgreSQL exclusion remains the final overlap guard.

The operation deliberately includes existing maintenance rooms, excludes other classes/resorts, and never affects future rooms automatically. Newly saved prices feed current availability/quotes, while frozen booking totals remain unchanged. Staff can remove/change a copied period using the existing versioned room editor. Browser CSRF and native staff credentials remain enforced; accountants/guests cannot read or mutate the class preview. One audit records actor, category, exact room versions and the period, with no guest data. `booking.test_class_pricing` covers permissions, stale membership, validation, all-or-nothing conflicts, adjacent intervals, subsequent per-room edits, public calendar values and concurrent duplicate submission.

## Operational monitoring

`GET /internal/metrics` exports bounded Prometheus gauges from PostgreSQL, protected by a separate server-only `METRICS_BEARER_TOKEN` (32+ characters). Empty token disables it (404), incorrect/missing credentials return 401 without querying the database. No query-string authentication, cookies or browser login grant access. Database failures/timeouts return 503 instead of healthy zeros; SQL statement timeout is 2 seconds per statement, connection timeout remains 10 seconds. Multiple aggregate queries use READ COMMITTED, so the snapshot is operational, not a financial report.

`REQUEST_LOG_ENABLED` defaults on outside DEBUG. Request logs allowlist server-generated `request_id`, resolver route template, method, status and duration; no request bodies, query strings or client identifiers. `X-Request-ID` is returned to correlate support reports. Liveness/readiness/metrics probes are excluded from routine logs. Logs currently stay with the hosting provider; no automatic Grafana log drain or HTTP percentile claim.

Setup, dashboard and alerts: [monitoring](../ops/monitoring/README.md). Current limits/next scaling steps: [SRE](sre.md), [rate limits](rate-limits.md). OperationalHeartbeat records scheduler/CLI start and completion independently of whether any jobs were due. A successful iteration does not imply a successful bank payment. New concurrent indexes are additive; do not remove them or the heartbeat table during a code rollback.
