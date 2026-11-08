# Frontend API contract

Implemented by Django/DRF in `backend/booking`, `backend/commerce` and `backend/identity`. Paths below are relative to `/api/v1`; legacy `/api` routes use the same handlers. Default static builds use `VITE_DATA_MODE=demo`; existing API builds use `VITE_DATA_MODE=api`, `VITE_API_BASE=/api`. `src/shared/api` supports JSON/FormData, cookie sessions and CSRF. Native guest Bearer authentication is described in [mobile-api.md](mobile-api.md). Scope: [product.md](product.md); deployment: [backend.md](backend.md); evidence: [verification.md](verification.md).

## Sessions, versions and errors

JSON responses or 204. Errors: `{message, fields, code?}`; guest authentication adds a stable machine-readable code. HTTP statuses: 401 absent/expired staff session or invalid guest credentials, 403 forbidden scope/CSRF, 404 missing/inaccessible record, 409 stale version/state/collision, 422 invalid input, 429 rate limit, 503 unavailable SMS delivery. The client maps network failure to 503 and invalid successful JSON to 502.

Browser clients get `/auth/csrf` before writes and send `X-CSRFToken`, including anonymous writes/login. `credentials: include` carries the HttpOnly session cookie. Refresh CSRF after register/login/logout; the web client never stores API auth tokens in localStorage. Staff login accepts `{email,password}`; guest login below accepts `{phone,password}`. Demo staff login accepts `{accountId}` only in the browser adapter; Django never accepts that contract.

Native guest login/refresh use JSON credentials at `/mobile-auth/*`; protected guest requests send `Authorization: Bearer <accessToken>`. Only a validated Bearer token exempts guest domain mutations from cookie CSRF. Invalid Authorization fails with 401 and never falls back to an anonymous guest or a staff/guest cookie. A guest Bearer token cannot authorize staff operations, even with a staff cookie present. Guest ownership, booking transactions and receipt/media access checks remain shared with the web API; see [native session contract](mobile-api.md) for device listing/revocation, 15-minute access, rotating refresh/replay revocation and registration/recovery limitations.

Domain records have string id and integer version. Catalogue/account/booking/review PATCH/DELETE send the version read by the editor. The session profile is a separate self-service name/phone update without a caller-selected identity or version. Parent resort on a room/tariff cannot change; admin can reassign accounts. Audit has no mutation endpoint. Server mutations validate scope and write audit in the same transaction.

| Method / path                                              | Input or result                                                                                               |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| GET /auth/csrf                                             | `{token}`; initializes guest session                                                                          |
| GET /auth/session                                          | Account or 204                                                                                                |
| POST /auth/login                                           | `{email,password}` → account + cookie                                                                         |
| POST /auth/logout                                          | Clears session, 204                                                                                           |
| GET /demo/accounts                                         | Browser demo only; absent on Django                                                                           |
| GET /categories                                            | `[{id,name}]`: wellness/family/premium/nature                                                                 |
| GET /catalog                                               | `{resorts,rooms,tariffs}`; published resorts, active inventory                                                |
| GET /resorts/:id                                           | `{resort,rooms,tariffs,reviews}`; published profile, approved reviews                                         |
| GET /rooms/:id                                             | `{resort,room,tariffs}`; active physical room under a published resort                                        |
| GET /availability?start=YYYY-MM-DD&end=YYYY-MM-DD&guests=2 | `{roomIds}`; no guest details                                                                                 |
| GET /my-bookings                                           | Website bookings owned by the resolved anonymous session or registered web/native guest                      |
| POST /my-bookings                                          | `{roomId,tariffId,start,end,guests,guestLabel,guestPhone,requestId}` → pending booking                        |
| PATCH /my-bookings/:id                                     | `{status:"cancelled",version}` → booking with cancellation/payment snapshots                                  |
| GET /workspace                                             | Scoped `{resorts,rooms,tariffs,bookings,accounts,audit,reviews}`; manager accounts list empty                 |
| POST /resorts                                              | Admin creates draft; publication requires active room and tariff                                              |
| PATCH /resorts/:id                                         | Admin/assigned manager edits fields + version                                                                 |
| DELETE /resorts/:id                                        | Admin `{version}` archives; current/future active bookings block archival                                     |
| POST /rooms, PATCH /rooms/:id                              | Scoped create/update; physical room number unique within resort                                               |
| DELETE /rooms/:id                                          | Scoped `{version}`; any historical booking reference prevents deletion                                        |
| POST /tariffs, PATCH /tariffs/:id                          | Scoped create/update                                                                                          |
| DELETE /tariffs/:id                                        | Scoped `{version}`; historical booking references prevent deletion                                            |
| POST /accounts, PATCH /accounts/:id                        | Admin manages manager; creation requires password, edit optionally replaces it                                |
| POST /bookings                                             | Staff request; same price/collision rules, starts pending                                                     |
| PATCH /bookings/:id                                        | Scoped `{status:"cancelled",version}`; manual approval/rejection returns 409                                              |
| GET /reviews?resortId=:id                                  | Approved public reviews, newest 100                                                                           |
| POST /reviews                                              | `{bookingId,rating,text,photos}`; own completed confirmed website stay, guest only                            |
| PATCH /reviews/:id                                         | Scoped `{version,status:"approved"\|"rejected",reply?}`                                                      |
| POST /media                                                | Multipart `{file,resortId}` for scoped staff, `{file,bookingId}` for eligible guest review → `{id,url,kind,alt}` |
| GET /media/files/:id                                       | Authorized managed file; private delivery or short-lived S3 redirect; inaccessible file gives 404            |
| POST /payments/demo                                        | `{bookingId,requestId,outcome:"success"\|"failed"}` → payment                                                |
| GET /cancellation-preview/:id                              | Owner/scoped staff refund estimate; `?asStaff=true` explicitly selects staff authorization                    |

## Guest phone registration, login and password reset

Guest authentication is separate from staff `/auth/*`; a GuestAccount never grants staff permissions. Session response is `{authenticated,account:{id,phone,phoneVerified}|null,profile:{id,name,phone,avatarUrl,version,createdAt,updatedAt}|null,mode:"demo"|"disabled",registrationMode:"password"|"challenge"|"disabled",passwordResetAvailable:boolean}`. `phoneVerified` is true only for a recorded genuine verification; demo OTP and temporary registration leave it false. `avatarUrl` is a stable authorized file URL or null. Responses are no-store and contain no opaque owner, password or OTP hashes.

| Method / path | Input or result |
| --- | --- |
| GET /guest-auth/session | Current guest session response (anonymous uses false/null/null) |
| POST /guest-auth/challenges | `{phone,purpose:"register"\|"reset"}` → `{challengeId,expiresAt,retryAfterSeconds:60,mode:"demo",demoCode,message}` |
| POST /guest-auth/register | `{challengeId,code,name,password}`; when temporary mode is explicitly enabled, `{phone,name,password}` → authenticated session, 201 |
| POST /guest-auth/login | `{phone,password}` → authenticated session, 200 |
| POST /guest-auth/reset | `{challengeId,code,password}` → `{ok:true,mode:"demo"}`; revokes old guest sessions, does not sign in |
| POST /guest-auth/logout | `{}` → anonymous session response; rotates session/CSRF, preserves independent staff identity |

Phone is normalized to Kazakhstan mobile format `+77` followed by nine digits; spaces, parentheses, hyphens and an eleven-digit leading `8` are accepted. Name is 1–80 characters. Guest password is 8–128 Unicode characters; digits, uppercase letters and symbols are not required. This policy applies to registration and reset, not staff passwords. Codes are six-digit strings (keep leading zeros), expire in five minutes, allow at most five attempts, and are single-use/browser-bound/purpose-bound. Repeating `/challenges` after 60 seconds invalidates the previous code. The browser must retain its session cookie between requesting and redeeming a code.

Machine error codes: `phone_invalid`, `weak_password`, `name_invalid`, `invalid_request`, `invalid_credentials`, `invalid_code`, `code_expired`, `resend_cooldown`, `rate_limited`, `sms_unavailable`, `already_authenticated`, `phone_change_requires_verification`, `method_not_allowed`, `not_found`. Reset/challenge responses use generic messages for existing and unknown phones; reset of an unknown phone does not create an account. See [backend.md](backend.md#guest-phone-authentication-api) for exact rate limits and delivery integration seam.

**OTP is explicitly DEMO**: code exposure requires both DEBUG=True and GUEST_AUTH_DEMO_OTP=True. Otherwise challenge creation/redemption and reset return503 `sms_unavailable`; password login remains available. No SMS is sent, and demo codes do not prove phone possession.

**Temporary registration without SMS (owner decision 08.11.2026):** server-only `GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION=True` enables the strict `{phone,name,password}` registration body independently of DEBUG. Default is false. The session advertises `registrationMode=password`; passwords retain 8–128 characters and normal hashing, CSRF and per-phone/IP rate limits. The phone is an unverified login identifier, never recovery proof. Existing phone/profile identities cannot be replaced or merged; phone/profile locks and unique constraints enforce one identity under concurrent signup. Session/owner rotation and adoption of only the current browser profile remain the same as challenge registration. Turning the flag off leaves existing password logins working and restores challenge-only registration. Reset is never bypassed: `passwordResetAvailable=false` hides its form until a real provider is connected (local DEBUG demo still supports its separate test reset flow). No fixed code, public OTP or SMS simulation is enabled in production. `booking.0012` adds nullable `GuestAccount.phone_verified_at`, preserving all old accounts as unverified; no past demo proof is promoted to actual verification.

Registration adopts only this browser's anonymous profile/website history, rotating opaque ownership so the old anonymous cookie loses access. Login to an existing account never merges this browser's unrelated history by phone. Password reset invalidates all guest session versions across devices, including receipt/payment/review/booking ownership checks. Guest logout/account switching drops the previous guest identity. New anonymous booking is forbidden (401 guest_login_required). Legacy anonymous history remains readable/adoptable and cannot be recovered by phone alone.

## Profile, stay and receipt routes

| Method / path                                        | Input or result                                                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| GET /profile                                         | `{profile,bookings}` for current guest session; creates an empty session profile if absent             |
| PATCH /profile                                       | `{name,phone}` only; rejects identity/role/owner overrides; returns own profile/history                |
| POST /profile/avatar                                 | Multipart `{file}`; signed-in guest only; returns `{profile}` with stable `avatarUrl`                  |
| DELETE /profile/avatar                               | Signed-in guest removes current avatar; returns `{profile}` with `avatarUrl:null`                     |
| GET /guests/:id                                      | Staff `{profile,bookings}` with history filtered to their resort; no matching scoped history gives 404 |
| POST /bookings/:id/check-in                          | Scoped `{version}`; confirmed+paid, inside stay dates, not already arrived                             |
| POST /bookings/:id/check-out                         | Scoped `{version}`; confirmed+paid, currently checked in                                               |
| GET /receipts/:paymentId                             | Owner or scoped staff `{receipt,payment,refund}`; failed/foreign receipt gives 404                     |
| GET /receipts/:paymentId/pdf                         | Same access; PDF attachment, Cache-Control no-store                                                    |
| GET /analytics?start=&end=&resortId=&granularity=day | Scoped event analytics, described below                                                                |

Profile fields: id/name/phone/avatarUrl/version/createdAt/updatedAt. The server resolves its owner from the registered web/native guest account or anonymous session. Authenticated PATCH /profile can change name, but phone must normalize to the account phone; changing it returns422 `phone_change_requires_verification` until a separate verification flow exists. Avatar changes use separate upload/delete endpoints, require a registered guest and cannot target an arbitrary profile. Replacing/removing an avatar makes the previous file inaccessible through its stable API URL; an already issued S3 signed URL may remain valid until its 60-second expiry. Website bookings link guestProfileId and retain their own contact snapshots; a booking contact phone never changes the account/profile's verified phone. Booking additionally returns stayStatus (`not_arrived/in_house/checked_out`), checkedInAt and checkedOutAt. Cancellation after check-in is refused. Checkout does not change the original booked date range or automatically issue a refund.

Successful payments additionally return `receiptUrl: "/receipts/:id"`; failed attempts return null. Receipt JSON is `{receipt,payment,refund}`. Receipt contains number, issuedAt, paymentId, bookingId, resortName, resortAddress, roomName, unit, start/end, guests, guestLabel, tariffName, regularNightly, nightly, nights, discountPercent, total, currency, checkinAt/timeZone, paymentMode, source, notice and legacySnapshot. Phone is omitted. The original snapshot is saved in the payment transaction and never changed by refunds; current refund is a separate `{amount,percent,createdAt}` or null. Legacy successful payments without a receipt are frozen on first authorized read and marked legacySnapshot:true, using immutable booking details and current address/missing catalogue fallback values.

`source:"demo"` is mandatory today. This is not a receipt delivered by Kaspi. A future real integration must retain the provider-delivered receipt file/URL after verified payment; no such provider API/schema has been implemented. PDF uses embedded OFL Noto Sans and is explicitly non-fiscal/demo. No public receipt access token or automatic external sharing exists; frontend may download/share a file at the user's action.

## Catalogue and accounts

- Resort: name, city, address, subtitle, description (≤3000), feature, lat/lng, rating/reviewRating and reviewCount (read-only approved-review aggregates), status (`draft/published/archived`), category (`wellness/family/premium/nature`), resortClass (`standard/comfort/premium`), checkInTime (`HH:mm`), timeZone (IANA, default Asia/Almaty), amenities, media. Classes are product labels, not certified star ratings.
- Room: resortId, number, category (`standard/comfort/suite`), title, description (≤5000), amenities, media, area (1–1000), capacity (1–4), beds, price (integer KZT/night), status (`active/maintenance`). Active bookings restrict maintenance and capacity reduction.
- Tariff: resortId, name, description, supplement (KZT/guest/night), features, status (`active/disabled`), priceKind (`regular/discount`), discountPercent (regular: 0; discount: 1–90).
- Amenities/features: string arrays, up to 30 entries of 200 characters; newline-separated text accepted on write. Media: `{kind:"image"|"video",url,alt}` array; API max 20, alt max 200. New uploads return canonical `/api/media/files/:id` URLs, including through `/api/v1`. Save validates asset purpose, kind and resort/booking ownership. Existing illustrative HTTPS and `/assets/`/`/media/` paths remain readable, without credentials/traversal; the UI uses file selection rather than URL entry.
- Account: name, login, resortId, role (`admin/manager`, server controlled), status (`active/disabled`), version. Password is write-only, at least 12 characters, required on manager creation. Unique email; invitation/reset email delivery absent. Superuser/admin cannot be edited via manager endpoints.

## Booking and price snapshots

Booking contains id/version, resortId, roomId, tariffId, start/end, guests, guestLabel/guestPhone, status, source (`website/staff`), createdAt; frozen resortName/roomName/unit/tariffName, regularNightly, priceKind, discountPercent, nightly, nights, total, cancellationPolicy. It also returns payment (object/null), reviewId and reviewStatus (null or pending/approved/rejected). Legacy bookings without recorded cancellation terms use a stable 14:00 Asia/Almaty default.

```text
for each night:
  roomPrice = matching seasonal period price, otherwise room.price
  regularNightly = roomPrice + tariff.supplement × chargeableGuests
  nightly = floor((regularNightly × (100 − discountPercent) + 50) / 100)
total = sum(nightlyBreakdown[].nightly)
```

The server ignores client total/discount overrides. Dates are `[start,end)`, 1–30 nights, before advertised check-in. Unexpired pending and confirmed reserve inventory. Successful payment atomically transitions pending → confirmed; manual confirmed/rejected requests return 409. Guest/scoped staff may cancel an eligible pending/confirmed booking. Expired pending → expired is a system action. Existing legacy confirmed/unpaid records can still pay; old pending records with null holdExpiresAt remain held until paid/cancelled (migration policy must be decided before production).

POST requires UUID requestId. Identical validated payload/owner/key returns the original booking with its current state and frozen price; changed payload/owner returns 409. A failed payment leaves the hold pending. Retrying the same payment key never repeats confirmation or receipt creation. New requests after payment, cancellation or expiry fail. Hold duration is BOOKING_HOLD_MINUTES (default 30, 1–120), capped at advertised check-in. holdExpiresAt is server time; client timers are informational.

## Demo payments and cancellation

This is an internal Kaspi-themed simulator, **not an official Kaspi API/sandbox integration**. No bank calls, card details, bank QR codes or real money movements. It remains a simulator in both data modes.

Payment: `{id,bookingId,status,paymentMode:"demo",provider:"kaspi-demo",currency:"KZT",amount,refundedAmount,createdAt}`. Status: paid/failed/partially_refunded/refunded. Website owner uses POST /payments/demo; scoped staff uses POST /payments/demo/staff only for source=staff orders (guest orders cannot be marked paid by this staff endpoint). Both accept `{bookingId,requestId,outcome:"success"|"failed"}`; the simulated outcome is NOT a trusted production-bank interface. One successful payment per booking, original amount frozen, payment/confirmation/receipt/audit atomic. Browser writes require CSRF; guest Bearer never grants staff payment permission.

Cancellation policy freezes `{mode:"demo",checkinAt,checkInTime,timeZone,partialRefundPercent:70,policyText}` when booking is created. Preview adds `{paidAmount,refundAmount,refundPercent,hoursBeforeCheckin,actorKind}`. At least 48h gives 100%; at least 24h but less than 48h gives 70%; under 24h gives 0%. Refund = floor(paidAmount × percent / 100). No successful payment means zero paid/refund amounts. Staff and guest use the same schedule; actorKind records initiation, not a policy override.

Preview is an estimate. Cancellation recomputes under the same resort lock as booking/payment mutations. Booking status, refund and audit commit atomically. Finalized refunds are immutable; later preview returns saved values with finalized:true. Booking.cancellation contains the saved calculation. Zero refund still permits cancellation and releases inventory; payment remains paid with refundedAmount 0.

## Reviews and files

Public review: `{id,resortId,rating,text,photos,reply,createdAt,verifiedStay:true}`. Staff output adds version/status/bookingId. Guests submit one review per owned completed confirmed website booking. Text 10–3000 characters, rating 1–5, max 6 photos. Initial pending; scoped manager/admin approves/rejects or replies. Only approved reviews affect aggregate rating/public list. No general comment thread or guest edit/delete endpoint.

POST /media requires browser CSRF or an authenticated native guest Bearer token. Staff need a non-archived assigned resort; guests need an owned completed booking without a review. Images: JPEG/PNG/WebP ≤8MiB/20MP, re-encoded to JPEG max 2400px with EXIF removed. Staff videos: MP4/WebM ≤40MiB, basic header checks. Avatar uploads use POST /profile/avatar with the same image rules and require a signed-in guest. Upload responses expose `{id,url,kind,alt}`; no object-storage key or permanent public bucket URL is returned.

Each upload creates `MediaAsset` metadata owned by a resort, review booking or guest profile. Catalogue/review uploads are attached by a later save, which checks the asset's scope and kind. Storage is private: local `backend/private-media` or configured Supabase S3. The stable canonical `/api/media/files/:id` endpoint evaluates permissions for every request; local delivery supports Range, configured S3 delivery redirects to a signed URL valid for 60 seconds. Responses use `private, no-store`; signed URLs must not be persisted in catalogue data. Public access requires a linked published resort/active room or approved review. Avatars require the owner or staff with access to that guest's booking; they are not public review photos.

Rolling 24-hour upload limits are 500MiB per resort's catalogue and 50MiB per avatar profile/review booking by default, at most 100 assets in each scope; settings can lower these limits. Over-limit uploads return429. Image/video files and aggregate incoming multipart requests have size limits. `cleanup_media` defaults to a dry run; `--delete` removes only metadata-backed unreferenced files older than 24 hours. Current references are retained. Object-store writes and database commits are not atomic, so reconciliation after failures remains required. Video decoding/transcoding, codec/duration validation and malware analysis are not implemented.

The Supabase private schema and bucket have been provisioned, but Django-to-Supabase SQL/S3 credentials and live application uploads remain unverified. The bucket accepts normalized JPEG plus MP4/WebM and has a 40MiB object limit; this does not replace the endpoint's stricter image limits. See [Supabase setup state](supabase.md).

## Limits

Workspace is a full catalogue/booking snapshot with newest 500 scoped audit/review entries; public reviews max 100. Pagination/search/export remain future work. Audit stores before/after with password/guestPhone excluded, including demo_payment/demo_refund events; DB administrators can still modify data.

API guest ownership resolves a stable registered web/native account owner or an opaque anonymous session owner. Demo uses tynys:workspace:v2 in localStorage and per-tab employee selection; browser tools can modify it, and it is not a secure shared account database. Demo uploads persist blobs in IndexedDB with stable local references and temporary display object URLs; this is per-browser/origin storage, not a shared media service. Demo time policy is fixed to Asia/Almaty; roles are not security. Deployment and verification are documented separately above.

## Analytics contract

GET /analytics is staff-only. Parameters: start/end date-only, inclusive, 1–366 days; default end today in Asia/Almaty and preceding 27 days; optional resortId (must be authorized); granularity day/week/month. Boundary years 0001/9999 are rejected to protect interval arithmetic. Previous period immediately precedes start with equal duration.

Response: `{period:{start,end,granularity,timeZone},previousPeriod:{start,end},paymentMode:"demo",totals,previousTotals,series,byResort,byRoom,resorts,truncated}`. Metric fields: bookingCount, bookedAmount, grossReceived, refunds, netReceived, reviewCount, averageRating. Totals/breakdowns also carry statuses:{pending,confirmed,rejected,cancelled}. Series rows add date and omit statuses. Weeks start Monday and months on day 1; bucket labels can precede start, but events are still limited to the requested interval. Missing buckets are zero-filled; averageRating is null when no approved reviews exist.

Booking count/value uses booking.createdAt, including cancelled/rejected requests. Gross uses successful payment.createdAt and original amount, even after refund; failed attempts are excluded. Refunds use refund.createdAt, not booking/payment dates. Net = grossReceived − refunds, may be negative and is not profit. Reviews count all creation events, while averageRating only includes currently approved reviews created within the period (rounded half-up to 2 decimals).

byResort rows add resortId/name; byRoom adds roomId/resortId/name/number. They include all authorized catalogue records, even archived/maintenance/zero-activity, rank netReceived descending then id ascending and cap 500 each with truncated flags. Totals/series remain full-scope. resorts contains all authorized filter options even when resortId selects one. Backend uses scoped database aggregates. Demo additionally returns refundDataIncomplete when legacy positive refunds lack event timestamps; those unknown-date events are omitted, never assigned an invented date.


## Seasonal pricing and child tariffs — 2026-10-27

`Room.pricePeriods`: up to 60 `{label, start, end, price}` periods. Start inclusive/end exclusive; price = room-only integer KZT/night (0..10,000,000), no overlaps. Missing field on PATCH preserves periods; `[]` clears them. Room version/tenant/audit checks still apply; PostgreSQL exclusion constraint is the final overlap guard.

`Tariff.childrenUnderThreeFree`: boolean, default false. When enabled, only tariff supplement is waived for children aged 0–2. Room charge remains, all guests count towards capacity. POST booking accepts optional `childrenAges` (integer ages 0..17 **at check-in**, max 3, length < guests). `guests` includes children and at least one adult. Missing ages retains all-paid legacy behavior; idempotency fingerprint omits empty ages for existing clients. Document validation/identity proof is not supplied by a declared age.

New snapshots (`pricingVersion:2`) include `childrenAges`, `freeChildren`, `chargeableGuests`, `childrenUnderThreeFree`, and `nightlyBreakdown` with date/roomPrice/periodLabel/supplementTotal/regularNightly/nightly. `nightly` and `regularNightly` are **null** when nonuniform; consumers must use `total` and daily lines, not assume nightly × nights. Update API consumers before enabling seasonal rates for them. Existing receipt/booking snapshots stay as written; new demo receipts copy daily lines. This is not fiscal or bank documentation.

## Infrastructure probes

`GET /health/live`: process 200 without DB. `GET /health/ready`: PostgreSQL SELECT 1; 200 or 503, JSON status only, no-store. Outside /api auth; restrict/rate-limit probes at ingress. No S3/SMS/payment/migration check.

## Platform commission and hold expiry

Staff workspace resorts include `commissionPercent` (decimal string or null). Only admin may submit this field through resort create/update; a manager submitting it gets 403. Public catalogue/profile serializers omit it. New booking snapshots store `commissionTerms:{percent,amount,resortAmount,currency,basis:"booking_total",mode:"estimate",refundHandling:"requires_reconciliation"}` with per-order half-up integer-KZT calculation. Only scoped staff booking output contains the terms. Null rate/amount is explicitly unconfigured, 0 is explicitly zero. Bank fees, actual split settlement and refund commission treatment are not implemented.

Run `manage.py expire_payment_holds` every minute in deployment. The command is idempotent, orders resort locks and audits expiry. New bookings also expire stale holds under the resort lock before the exclusion check; availability ignores elapsed holds. A payment attempt commits overdue expiry before refusing payment. Paid bookings never expire. Late real bank events after expiry require a separate reconciliation/refund workflow, never blindly recreate inventory. This simulator does not implement provider callbacks.


## Staff placement planner (2026-11-04)

- Staff `POST /bookings`: `tariffId` is optional. Omitted means room-only seasonal/base price with zero tariff supplement/discount; snapshot includes `pricingBasis: "room"` and `tariffName: ""`, response `tariffId: null`. Existing callers with an explicit valid tariff retain tariff pricing. Guest `POST /my-bookings` still requires tariff.
- `GET /workspace` booking includes `staffNotes: string`; guest/profile/receipt APIs do not expose notes. Existing stay and payment fields drive the calendar. Calendar colors do not constitute booking/payment transitions.
- `POST /bookings/:id/notes`: `{ "version": 2, "staffNotes": "…" }` -> updated staff booking; 401/403 unauthorized, 409 stale version, 422 invalid/non-string/>2000 characters. Empty string clears a note. Staff tenant scope and CSRF apply. Audit includes version/length only, not content. `/api/v1` and legacy `/api` share these contracts.
- Calendar interval is `[start,end)`; actual `checkedInAt`/`checkedOutAt` drive blue/purple, confirmed/not-arrived is green, unexpired pending is amber. Cancelled/rejected/expired are kept in the list. Early checkout does not alter reserved interval or refunds. Workspace remains unpaginated; window-scoped API is a future scaling task.


## Guest availability calendar

`GET /api/v1/availability-calendar` (also `/api`) takes `resortId`, `category` (`standard/comfort/suite`), `month` (`YYYY-MM`), optional `roomId`, `guests` (1–4, default 1), and optional `arrival` (`YYYY-MM-DD`). Published resorts and active rooms only; without `roomId` the calendar aggregates the selected class; with it, only the matching physical room. A missing/hidden resort or mismatched room returns 404; unsupported parameters return 422. Invalid input returns 400/422. Months are bounded from the property's current month through the month containing today + 365 days. Arrival must be within that year.

Response: `{month,today,timeZone,totalRooms,days:[{date,availableRooms,departureRooms,bookable}]}`. `totalRooms` counts matching physical rooms with enough capacity. `availableRooms` is the free room count for that night. `bookable` excludes past days, today after advertised local check-in, and days beyond the one-year arrival horizon. Confirmed bookings and unexpired pending holds occupy `[start,end)`; cancelled/expired holds do not. No guest, booking ID, phone or room ID list is returned. Responses are no-store. The server uses one bounded overlapping-range read, not one request per date.

With `arrival`, `departureRooms` counts rooms available continuously for `[arrival,date)`, from 1 to 30 nights. A night marked occupied may still be a valid check-out date, since that night is not part of the stay. Two separately free nights in different rooms never imply a single available stay. Calendar selection then runs the existing `/availability` range check; creation revalidates transactionally under the resort lock. These counts are a point-in-time view, not an inventory reservation. Demo implements the same contract against its own browser storage.


## Банковский sandbox checkout

Канонический новый контракт: [payments.openapi.yaml](contracts/payments.openapi.yaml); проверяемые обезличенные формы ответов: [halyk-sandbox.json](contracts/fixtures/halyk-sandbox.json). Оба префикса `/api/v1` и `/api` используют одинаковые handlers. `POST /payments/checkouts` принимает только bookingId, requestKey, locale; contacts для общего sandbox генерируются сервером и вымышлены. Staff routes отдельные, только для staff-source брони своего объекта. GET читает локальный статус, POST refresh ставит durable сверку. `/payments/config` сообщает доступность. При закрытом protocol gate возвращается 503, без подмены симулятором.

## XPayment: расширение банковского контракта, 06.11.2026

`xpayment` — отдельный provider, `production` — тип его внешнего API; опубликованного денежного sandbox не найдено. До настройки и приёмки провайдер недоступен. Сумма, валюта, merchant binding и provider определяются сервером. Исторические `halyk_epay/sandbox` и `kaspi-demo/demo` не меняют тип при переключении нового checkout. Клиент должен читать provider/environment сохранённой попытки и не выводить sandbox-ярлык для XPayment. Нельзя подтверждать бронь из перехода по QR/deep link или страницы возврата.

`POST /payments/providers/xpayment/callback` доступен под `/api/v1` и совместимым `/api`. Это endpoint провайдера без пользовательской сессии; он принимает ограниченное тело с `event_version="1"`, `source="xpayment"`, UUID `delivery_id`/`payment_id` и допустимым событием. `X-xPayment-Signature` проверяется как hex HMAC-SHA256 исходных байтов тела с серверным секретом. Повторная доставка дедуплицируется в БД. Callback ставит независимую GET-сверку; данные тела не являются финансовым доказательством, включая подписанный тест из кабинета провайдера.

Завершённый возврат требуется подтвердить отдельно от принятого POST. Неизвестные статусы, чужой аккаунт/заказ, сумма или валюта, поздняя оплата и неясный исход операции не разрешают оформление брони. XPayment не предоставляет документированный receipt API: `receiptUrl` остаётся null, пока настоящий документ не получен поддержанным способом. Подготовка и уточнения контракта — [xpayment-integration.md](xpayment-integration.md).


## Accounting and documents (2026-11-08)

All paths use `/api/v1` or legacy `/api`. Staff cookie + CSRF for writes; active admin or scoped accountant. Manager gets 403. Accountant has no workspace/catalog/stay/account mutation privilege. Existing admin-only accounts API accepts `role: manager|accountant`; password hashing and credential-version invalidation remain.

- `GET /accounting?resortId=&start=YYYY-MM-DD&end=YYYY-MM-DD&paymentMode=production|sandbox|demo&search=&page=1`: authorized resorts, period, totals (received/refunded/net), count, page, bookings (50), documents (latest 200), documentCount. Max period 366 days; dates are financial events in Asia/Almaty, booking list uses creation dates. No environment mixing. Net is not profit. Search only filters bookings.
- `GET /accounting/export`: same booking filters, CSV up to 5000 records, spreadsheet-formula prefixes escaped.
- `GET/PATCH /accounting/company/:resort`: optimistic `version` (0 creates), supplier, bin, address, iban, bank, bik, director, accountant, vatMode=no_vat|included, vatRate=0..100. VAT treatment is explicitly supplied by accountant, not inferred from booking.
- `POST /accounting/documents {bookingId,kind:act|invoice|cash_order}`: idempotently returns current nonvoided draft/released document; no duplicate number per scope.
- `POST /accounting/documents/:id/refresh|release|void {version}`: draft refresh, checked-out/paid/requisites validation before release, immutable released snapshot. PKO release blocked until cash-accounting domain exists.
- `GET /accounting/documents/:id/pdf|xlsx/download`: authorized attachment, no-store.
- `GET /my-documents[?bookingId=...]` and `/my-documents/:id/pdf|xlsx/download`: own released website booking only via guest_owner; no phone matching. Voided/draft/foreign documents hidden. Guest list bounded to latest 200.

Accountant reads do not include guest phone/IIN. Audit records document ID/state/version, not company requisites or document contents. Exports are unsigned preparation copies, not bank receipts/registered ESF. Actual checkout prepares invoice+act drafts atomically. Per-resort sequences are year/kind scoped. Current company/requisites affect drafts only. Additional line items, ledger, document pagination beyond 200, delivery notifications and signed archive remain follow-up.

### Child dates
Booking input accepts optional `childrenBirthDates: [YYYY-MM-DD]`; no confirmation checkbox is required. Legacy `childrenDatesConfirmed` is ignored. Server validates actual calendar dates, birth <= today, completed age 0..17 at check-in, adult/capacity rules and any supplied childrenAges consistency. Dates/confirmation are removed before idempotency fingerprint and persistence; snapshot stores ages only. The requested 12-digit demo input stays in component memory; only its first-six date assumption is submitted as a transient DOB, never the full IIN. Full `iin`/unknown fields are rejected. Legacy display total/nightly/regularNightly/discountPercent are ignored; server pricing remains authoritative. No identity verification is implied.


## 2026-11-08 — Registered checkout and platform finance (supersedes earlier scoped-accountant policy)

`POST /my-bookings` requires an active GuestAccount. Guest label/phone are overwritten from profile.name/account.phone before validation, never used to update the profile. Missing profile name returns 422 guest_profile_incomplete. Idempotent retries ignore contact changes and retain original contact/deadline snapshots. New hold default is 15 minutes, capped at advertised check-in; existing holds remain frozen. Countdown displays holdExpiresAt, does not extend or confirm bookings. Staff manual booking retains contact input.

Accountant may GET `/workspace` (all resorts, no employee accounts/audit/reviews) and `/analytics`, but may not mutate bookings, stay/notes, catalogue or staff accounts. Accountant's resortId is nullable/ignored; new edits save null. Admin/accountant accounting scope spans the platform. Manager remains tenant-scoped.

- GET `/bookings/:bookingId/documents` and `/bookings/:bookingId/documents/:id/:pdf|xlsx/download`: admin/accountant all resorts, manager assigned resort only. Read-only; no financial workspace access granted to manager. Guest `/my-documents` remains released/owned records only.
- GET `/accounting` adds `finance`: totals, byResort (max 500), platformExpenses, expenses (latest 200, includes voided history), expenseCount. Cash dates use recorded transaction time; booking values use creation period; expenses use occurred_on. Source modes remain separate. Search narrows booking registry/commitments, not payment/expense totals. Commission is frozen order estimate before refund reconciliation, never settled revenue.
- POST `/accounting/expenses`: `{resortId: string|null,date: YYYY-MM-DD,amount: integer 1..10^12,category: bank_fee|operations|marketing|payroll|taxes|other,description: <=240,paymentMode: production|sandbox|demo,requestId: UUID}`. Requires admin/accountant + CSRF. Date cannot be future. Same payload/key retries idempotently; changed payload/key conflicts. No money transfer occurs.
- POST `/accounting/expenses/:id/void`: `{version,reason: 3..240}`. Row lock, version check, audit and retained history. No destructive delete/update.
- GET `/accounting/report.xlsx`: same period/resort/mode/search filters; sheets Summary/Resorts/Expenses (Russian titles). Rejects truncated exports (>500 properties or >200 expenses), forces text cells to prevent spreadsheet formula execution. Not a bank statement or 1C import contract.

Prepared files have per-row loading/errors, PDF preview and persistent Download/Open fallback links for mobile browsers. Blob URLs are revoked on component disposal. No anonymous share URLs are created.

### Partner ownership and admin client directory (2026-11-08)
- Staff `Resort.accountId`: required on POST /resorts, optional on versioned PATCH; changing ownership is admin-only (older managers may round-trip their unchanged accountId). Must reference an active admin/manager; never exposed by public catalog endpoints. Existing disabled ownership remains linked until reassigned.
- Staff account response adds `resortIds` (all owned properties), `createdAt`, `lastLogin`. `resortId` is the first owned property for legacy readers, never an authorization source. POST /accounts allows a manager with no resorts. Assign/transfer in PATCH /resorts, not POST/PATCH /accounts. Manager workspace/analytics include all owned resorts; accountant retains global explicit financial/read permissions.
- Admin `GET /clients?q=&page=1`: `{items:[{profile,account,bookingCount}],count,page,pageSize:25}`. `account=null` is legacy history, not a registered guest. Registered summary contains only id, status, version, createdAt. Search max100, page max100000. No auth/ownership hashes.
- `GET /guests/:profileId`: admin can view guests without bookings, with account summary. Managers only view guests with website bookings in their owned resorts; history remains scoped. Accountant denied.
- Admin `PATCH /clients/:profileId` accepts exactly `{version,status:'active'|'disabled'}`. CSRF/Bearer rules apply; stale version409. Increments account.version and auth_version, invalidates previous sessions even on re-enable; audit contains status/version, not contacts.
