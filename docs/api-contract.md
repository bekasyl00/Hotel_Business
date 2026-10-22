# Frontend API contract

Implemented consumer contract, not a running backend. Default: `VITE_DATA_MODE=demo`. To use a future API set `VITE_DATA_MODE=api` and `VITE_API_BASE=/api` before building. `src/app/main.js` chooses the transport. Components/Pinia stores use `shared/api.request(method, path, body)`; they do not depend on browser storage.

## Responses and sessions

JSON responses (or 204). Errors: `{ "message": "Human-readable message", "fields": { "name": "Optional field message" } }`. HTTP status: 401 expired/absent session, 403 forbidden tenant/role, 404 absent record, 409 stale version or booking collision, 422 validation, 503 unavailable. Forms retain values on failure and disable duplicate submissions.

Real mode uses HttpOnly cookie sessions with `credentials: include`; passwords are held only in login component memory and cleared after success. Backend must set secure cookie attributes and enforce CSRF protections (SameSite + Origin validation, or extend transport with a server CSRF token), authorization, rate limits, availability constraints and input validation. No token is stored in localStorage. Demo `/auth/login` accepts `{accountId}`; real login accepts `{email,password}`. Never deploy a server that accepts the demo login contract.

| Method / path | Result / behavior |
|---|---|
| GET /auth/session | Account or null; account has id, name, login, role (`admin`/`manager`), resortId, status |
| POST /auth/login | Session account; real server sets session cookie |
| POST /auth/logout | Clear server session; 204 or null |
| GET /demo/accounts | Demo only: active selectable identities; never needed by real mode |
| GET /catalog | `{resorts, rooms, tariffs}` published public catalog, active rooms/tariffs |
| GET /availability?start=YYYY-MM-DD&end=YYYY-MM-DD&guests=2 | `{roomIds: string[]}` available physical rooms; no guest records exposed |
| GET /my-bookings | Current guest's bookings only (demo browser identity) |
| POST /my-bookings | Create guest booking; `{roomId,tariffId,start,end,guests}`; server calculates price |
| PATCH /my-bookings/:id | `{status:"cancelled",version}`; own booking only |
| GET /workspace | `{resorts,rooms,tariffs,bookings,accounts,audit}`; server-scoped to role/tenant; accounts empty for managers |
| POST /resorts | Admin only; create draft; returns saved resort |
| PATCH /resorts/:id | Admin or assigned manager; full editable fields + version |
| DELETE /resorts/:id | Admin only; `{version}`, archive; blocked by current/future active bookings |
| POST /rooms, PATCH /rooms/:id | Scoped create/update; unique physical number inside resort |
| DELETE /rooms/:id | Scoped `{version}`; reject when any booking references this room |
| POST /tariffs, PATCH /tariffs/:id | Scoped create/update; disabled tariffs excluded from guest catalog |
| DELETE /tariffs/:id | Scoped `{version}`; reject when referenced by booking history |
| POST /accounts, PATCH /accounts/:id | Admin only; create/edit manager, assign a single resort, disable access. Real provisioning/invitations belong to server |
| POST /bookings | Staff manual booking, plus `guestLabel`; same collision/price rules as website |
| PATCH /bookings/:id | Scoped `{status:"cancelled",version}`; history retained |

Every record has string `id` and integer `version`. PATCH/DELETE send the version read by the form; the server must compare and update atomically. POST returns version 1. Parent resortId on room/tariff is immutable; accounts may be reassigned by the admin. DELETE for room/tariff returns null; archive returns updated resort. Audit has no write/delete endpoint.

## Record fields

- Resort: name, city, address, subtitle, description, feature, lat, lng, rating (read-only demo), status (`draft`, `published`, `archived`). Publish requires at least one active room and tariff. New rooms/tariffs require non-archived resort.
- Room: resortId, number, category (`standard`, `comfort`, `suite`), title, area, capacity (1–4), beds, price (integer KZT per room/night), status (`active`, `maintenance`). Cannot lower capacity below a current/future booking's guest count or place a reserved room into maintenance.
- Tariff: resortId, name, description, supplement (integer KZT per guest/night), features (string[] in response; newline-separated string on write), status (`active`, `disabled`).
- Manager account: name, login, resortId, role (`manager`, server assigned), status (`active`, `disabled`). No password data in workspace responses. Login unique. Admin account cannot be modified via manager endpoints.
- Booking: resortId, roomId, tariffId, start, end, guests, guestLabel, status (`confirmed`, `cancelled`), source (`website`, `staff`), createdAt, snapshots resortName/roomName/unit/tariffName, nightly, nights, total. Price = (room.price + tariff.supplement × guests) × nights; checkout excluded. Existing booking prices remain unchanged after catalog edits. No payments.
- Audit: id, at (ISO UTC), actor (display name), resortId, entity, entityId, action (`create`, `update`, `delete`, `archive`, `cancel`), label, before, after. Server must record audit in the same transaction as the mutation and redact sensitive fields. UI renders local time in Asia/Almaty.

## Demo limitations and migration

One versioned localStorage envelope `tynys:workspace:v2` stores data and audit together. Session identity is per-tab sessionStorage. On first initialization, valid matching legacy `tynys:bookings:v1` records are imported; the original key is retained. Browser Web Locks serialize demo writes when supported; no cross-device guarantees. Audit and roles can be modified through browser tools, so demo access is not authentication or security.

The browser identity used for guest booking ownership must be replaced with server-authenticated ownership (or a secure guest-session mechanism). Real backend integration, session expiry, CSRF behavior and server-side concurrency have not been tested. `GET /workspace` is intentionally a small-MVP snapshot; server paging/filtering should be introduced before large catalogs.
