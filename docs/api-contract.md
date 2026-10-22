# Frontend API contract

Implemented by Django/DRF in `backend/booking` and `backend/commerce`. Paths below are relative to `/api`. Default static builds use `VITE_DATA_MODE=demo`; API builds use `VITE_DATA_MODE=api`, `VITE_API_BASE=/api`. `src/shared/api` supports JSON/FormData, cookie sessions and CSRF. Scope: [product.md](product.md); deployment: [backend.md](backend.md); evidence: [verification.md](verification.md).

## Sessions, versions and errors

JSON responses or 204. Errors: `{message, fields, code?}`; guest authentication adds a stable machine-readable code. HTTP statuses: 401 absent/expired staff session or invalid guest credentials, 403 forbidden scope/CSRF, 404 missing/inaccessible record, 409 stale version/state/collision, 422 invalid input, 429 rate limit, 503 unavailable SMS delivery. The client maps network failure to 503 and invalid successful JSON to 502.

Get `/auth/csrf` before writes; send `X-CSRFToken`, including anonymous writes/login. `credentials: include` carries the HttpOnly session cookie. Refresh CSRF after register/login/logout; API auth tokens are never stored in localStorage. Staff login accepts `{email,password}`; guest login below accepts `{phone,password}`. Demo staff login accepts `{accountId}` only in the browser adapter; Django never accepts that contract.

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
| GET /my-bookings                                           | Website bookings owned by this server guest session                                                           |
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
| PATCH /bookings/:id                                        | Scoped `{status:"confirmed"                                                                                   | "rejected"           | "cancelled",version}` |
| GET /reviews?resortId=:id                                  | Approved public reviews, newest 100                                                                           |
| POST /reviews                                              | `{bookingId,rating,text,photos}`; own completed confirmed website stay, guest only                            |
| PATCH /reviews/:id                                         | Scoped `{version,status:"approved"                                                                            | "rejected",reply?}`  |
| POST /media                                                | Multipart `{file,resortId}` for scoped staff, `{file,bookingId}` for eligible guest review → `{url,kind,alt}` |
| POST /payments/demo                                        | `{bookingId,requestId,outcome:"success"                                                                       | "failed"}` → payment |
| GET /cancellation-preview/:id                              | Owner/scoped staff refund estimate; `?asStaff=true` explicitly selects staff authorization                    |

## Guest phone registration, login and password reset

Guest authentication is separate from staff `/auth/*`; a GuestAccount never grants staff permissions. Session response is `{authenticated,account:{id,phone}|null,profile:{id,name,phone,version,createdAt,updatedAt}|null,mode:"demo"|"disabled"}`. Responses are no-store and contain no opaque owner, password or OTP hashes.

| Method / path | Input or result |
| --- | --- |
| GET /guest-auth/session | Current guest session response (anonymous uses false/null/null) |
| POST /guest-auth/challenges | `{phone,purpose:"register"\|"reset"}` → `{challengeId,expiresAt,retryAfterSeconds:60,mode:"demo",demoCode,message}` |
| POST /guest-auth/register | `{challengeId,code,name,password}` → authenticated session, 201 |
| POST /guest-auth/login | `{phone,password}` → authenticated session, 200 |
| POST /guest-auth/reset | `{challengeId,code,password}` → `{ok:true,mode:"demo"}`; revokes old guest sessions, does not sign in |
| POST /guest-auth/logout | `{}` → anonymous session response; rotates session/CSRF, preserves independent staff identity |

Phone is normalized to Kazakhstan mobile format `+77` followed by nine digits; spaces, parentheses, hyphens and an eleven-digit leading `8` are accepted. Name is 1–80 characters. Password is 12–128 characters and must pass Django common/numeric-password validation. Codes are six-digit strings (keep leading zeros), expire in five minutes, allow at most five attempts, and are single-use/browser-bound/purpose-bound. Repeating `/challenges` after 60 seconds invalidates the previous code. The browser must retain its session cookie between requesting and redeeming a code.

Machine error codes: `phone_invalid`, `weak_password`, `name_invalid`, `invalid_request`, `invalid_credentials`, `invalid_code`, `code_expired`, `resend_cooldown`, `rate_limited`, `sms_unavailable`, `already_authenticated`, `phone_change_requires_verification`, `method_not_allowed`, `not_found`. Reset/challenge responses use generic messages for existing and unknown phones; reset of an unknown phone does not create an account. See [backend.md](backend.md#guest-phone-authentication-api) for exact rate limits and delivery integration seam.

**OTP is explicitly DEMO**: code exposure requires both DEBUG=True and GUEST_AUTH_DEMO_OTP=True. Otherwise registration/reset, including code redemption, return503 `sms_unavailable`; password login for existing accounts remains available. No SMS is sent, and this flow is not proof of phone possession. Real SMS integration remains required before enabling public registration in production.

Registration adopts only this browser's anonymous profile/website history, rotating opaque ownership so the old anonymous cookie loses access. Login to an existing account never merges this browser's unrelated history by phone. Password reset invalidates all guest session versions across devices, including receipt/payment/review/booking ownership checks. Guest logout/account switching drops the previous guest identity. Anonymous booking remains supported; anonymous history cannot be recovered by phone alone.

## Profile, stay and receipt routes

| Method / path                                        | Input or result                                                                                        |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| GET /profile                                         | `{profile,bookings}` for current guest session; creates an empty session profile if absent             |
| PATCH /profile                                       | `{name,phone}` only; rejects identity/role/owner overrides; returns own profile/history                |
| GET /guests/:id                                      | Staff `{profile,bookings}` with history filtered to their resort; no matching scoped history gives 404 |
| POST /bookings/:id/check-in                          | Scoped `{version}`; confirmed+paid, inside stay dates, not already arrived                             |
| POST /bookings/:id/check-out                         | Scoped `{version}`; confirmed+paid, currently checked in                                               |
| GET /receipts/:paymentId                             | Owner or scoped staff `{receipt,payment,refund}`; failed/foreign receipt gives 404                     |
| GET /receipts/:paymentId/pdf                         | Same access; PDF attachment, Cache-Control no-store                                                    |
| GET /analytics?start=&end=&resortId=&granularity=day | Scoped event analytics, described below                                                                |

Profile fields: id/name/phone/version/createdAt/updatedAt. The server resolves its owner from the guest account or anonymous session. Authenticated PATCH /profile can change name, but phone must normalize to the account phone; changing it returns422 `phone_change_requires_verification` until a separate verification flow exists. Website bookings link guestProfileId and retain their own contact snapshots; a booking contact phone never changes the account/profile's verified phone. Booking additionally returns stayStatus (`not_arrived/in_house/checked_out`), checkedInAt and checkedOutAt. Cancellation after check-in is refused. Checkout does not change the original booked date range or automatically issue a refund.

Successful payments additionally return `receiptUrl: "/receipts/:id"`; failed attempts return null. Receipt JSON is `{receipt,payment,refund}`. Receipt contains number, issuedAt, paymentId, bookingId, resortName, resortAddress, roomName, unit, start/end, guests, guestLabel, tariffName, regularNightly, nightly, nights, discountPercent, total, currency, checkinAt/timeZone, paymentMode, source, notice and legacySnapshot. Phone is omitted. The original snapshot is saved in the payment transaction and never changed by refunds; current refund is a separate `{amount,percent,createdAt}` or null. Legacy successful payments without a receipt are frozen on first authorized read and marked legacySnapshot:true, using immutable booking details and current address/missing catalogue fallback values.

`source:"demo"` is mandatory today. This is not a receipt delivered by Kaspi. A future real integration must retain the provider-delivered receipt file/URL after verified payment; no such provider API/schema has been implemented. PDF uses embedded OFL Noto Sans and is explicitly non-fiscal/demo. No public receipt access token or automatic external sharing exists; frontend may download/share a file at the user's action.

## Catalogue and accounts

- Resort: name, city, address, subtitle, description (≤3000), feature, lat/lng, rating/reviewRating and reviewCount (read-only approved-review aggregates), status (`draft/published/archived`), category (`wellness/family/premium/nature`), resortClass (`standard/comfort/premium`), checkInTime (`HH:mm`), timeZone (IANA, default Asia/Almaty), amenities, media. Classes are product labels, not certified star ratings.
- Room: resortId, number, category (`standard/comfort/suite`), title, description (≤5000), amenities, media, area (1–1000), capacity (1–4), beds, price (integer KZT/night), status (`active/maintenance`). Active bookings restrict maintenance and capacity reduction.
- Tariff: resortId, name, description, supplement (KZT/guest/night), features, status (`active/disabled`), priceKind (`regular/discount`), discountPercent (regular: 0; discount: 1–90).
- Amenities/features: string arrays, up to 30 entries of 200 characters; newline-separated text accepted on write. Media: `{kind:"image"|"video",url,alt}` array; API max 20, alt max 200. URLs must be HTTPS or `/assets/`/`/media/` paths, without credentials/traversal.
- Account: name, login, resortId, role (`admin/manager`, server controlled), status (`active/disabled`), version. Password is write-only, at least 12 characters, required on manager creation. Unique email; invitation/reset email delivery absent. Superuser/admin cannot be edited via manager endpoints.

## Booking and price snapshots

Booking contains id/version, resortId, roomId, tariffId, start/end, guests, guestLabel/guestPhone, status, source (`website/staff`), createdAt; frozen resortName/roomName/unit/tariffName, regularNightly, priceKind, discountPercent, nightly, nights, total, cancellationPolicy. It also returns payment (object/null), reviewId and reviewStatus (null or pending/approved/rejected). Legacy bookings without recorded cancellation terms use a stable 14:00 Asia/Almaty default.

```text
regularNightly = room.price + tariff.supplement × guests
nightly = floor((regularNightly × (100 − discountPercent) + 50) / 100)
total = nightly × nights
```

The server ignores client total/discount overrides. Dates are `[start,end)`, 1–30 nights. Pending and confirmed block inventory. Pending transitions to confirmed/rejected/cancelled; confirmed only to cancelled. Guests cancel only their website bookings. Completed stays cannot change status.

POST requires UUID requestId. Identical validated payload/owner/key returns the original booking and its original price/time terms. Changed payload/owner with a used key returns 409. Confirmation does not mark a booking paid. Pending requests and unpaid confirmations have no automatic expiry.

## Demo payments and cancellation

This is an internal Kaspi-themed simulator, **not an official Kaspi API/sandbox integration**. No bank calls, card details, bank QR codes or real money movements. It remains a simulator in both data modes.

Payment: `{id,bookingId,status,paymentMode:"demo",provider:"kaspi-demo",currency:"KZT",amount,refundedAmount,createdAt}`. Status: paid/failed/partially_refunded/refunded. Only the website owner can pay a confirmed booking before its frozen check-in timestamp. Amount is the server total. Same requestId/outcome returns the original result; conflicting reuse returns 409. Failed attempts may retry with new keys. A booking cannot be paid successfully twice, including concurrent requests.

Cancellation policy freezes `{mode:"demo",checkinAt,checkInTime,timeZone,partialRefundPercent:70,policyText}` when booking is created. Preview adds `{paidAmount,refundAmount,refundPercent,hoursBeforeCheckin,actorKind}`. At least 48h gives 100%; at least 24h but less than 48h gives 70%; under 24h gives 0%. Refund = floor(paidAmount × percent / 100). No successful payment means zero paid/refund amounts. Staff and guest use the same schedule; actorKind records initiation, not a policy override.

Preview is an estimate. Cancellation recomputes under the same resort lock as booking/payment mutations. Booking status, refund and audit commit atomically. Finalized refunds are immutable; later preview returns saved values with finalized:true. Booking.cancellation contains the saved calculation. Zero refund still permits cancellation and releases inventory; payment remains paid with refundedAmount 0.

## Reviews and files

Public review: `{id,resortId,rating,text,photos,reply,createdAt,verifiedStay:true}`. Staff output adds version/status/bookingId. Guests submit one review per owned completed confirmed website booking. Text 10–3000 characters, rating 1–5, max 6 photos. Initial pending; scoped manager/admin approves/rejects or replies. Only approved reviews affect aggregate rating/public list. No general comment thread or guest edit/delete endpoint.

POST /media requires CSRF. Staff need a non-archived assigned resort; guests need an owned completed booking without a review. Images: JPEG/PNG/WebP ≤8MiB/20MP, re-encoded to JPEG max 2400px with EXIF removed. Staff videos: MP4/WebM ≤40MiB, basic header checks. Generated filenames are stored under local backend/mediafiles; upload response is attached by a later catalogue/review save. Unattached-file cleanup, per-user quotas, media ownership references, video decoding/transcoding and object storage are not implemented.

## Limits

Workspace is a full catalogue/booking snapshot with newest 500 scoped audit/review entries; public reviews max 100. Pagination/search/export remain future work. Audit stores before/after with password/guestPhone excluded, including demo_payment/demo_refund events; DB administrators can still modify data.

API guest ownership resolves a stable registered account owner or an opaque anonymous session owner. Demo uses tynys:workspace:v2 in localStorage and per-tab employee selection; browser tools can modify it, and it is not a secure shared account database. Demo time policy is fixed to Asia/Almaty; roles are not security. Demo file uploads do not persist in a shared service. Deployment and verification are documented separately above.

## Analytics contract

GET /analytics is staff-only. Parameters: start/end date-only, inclusive, 1–366 days; default end today in Asia/Almaty and preceding 27 days; optional resortId (must be authorized); granularity day/week/month. Boundary years 0001/9999 are rejected to protect interval arithmetic. Previous period immediately precedes start with equal duration.

Response: `{period:{start,end,granularity,timeZone},previousPeriod:{start,end},paymentMode:"demo",totals,previousTotals,series,byResort,byRoom,resorts,truncated}`. Metric fields: bookingCount, bookedAmount, grossReceived, refunds, netReceived, reviewCount, averageRating. Totals/breakdowns also carry statuses:{pending,confirmed,rejected,cancelled}. Series rows add date and omit statuses. Weeks start Monday and months on day 1; bucket labels can precede start, but events are still limited to the requested interval. Missing buckets are zero-filled; averageRating is null when no approved reviews exist.

Booking count/value uses booking.createdAt, including cancelled/rejected requests. Gross uses successful payment.createdAt and original amount, even after refund; failed attempts are excluded. Refunds use refund.createdAt, not booking/payment dates. Net = grossReceived − refunds, may be negative and is not profit. Reviews count all creation events, while averageRating only includes currently approved reviews created within the period (rounded half-up to 2 decimals).

byResort rows add resortId/name; byRoom adds roomId/resortId/name/number. They include all authorized catalogue records, even archived/maintenance/zero-activity, rank netReceived descending then id ascending and cap 500 each with truncated flags. Totals/series remain full-scope. resorts contains all authorized filter options even when resortId selects one. Backend uses scoped database aggregates. Demo additionally returns refundDataIncomplete when legacy positive refunds lack event timestamps; those unknown-date events are omitted, never assigned an invented date.
