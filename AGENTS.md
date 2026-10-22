# Project navigation

Read `architecture/system.c4`, `architecture/modules.c4`, and recent `docs/decisions.md` before structural changes. Product scope and proposed backlog: `docs/product.md`. Current checks and limitations: `docs/verification.md`. Verify documentation against source.

- Vue 3 + Pinia + Vue Router + Vite, FSD, vue-i18n (ru/kk/en). Translation JSON lives in src/shared/i18n/locales; preserve key/placeholder parity. Backend: Django 5.2 / DRF / PostgreSQL in backend/. Read docs/backend.md.
- FSD dependencies: app → pages → widgets → features → entities → shared. Import another slice through its root public API; no sideways imports. `npm test` checks local JS/Vue imports.
- `src/app/providers/demo.js` implements the demo transport. `src/shared/api` owns the HTTP boundary. Contract: `docs/api-contract.md`. Views never access localStorage directly.
- `src/entities/booking/model/rules.js` owns date rules. Production validation and transactions live in backend/booking/services.py. PostgreSQL tests must use real PostgreSQL, never SQLite.
- Roles in the frontend are not security. Production tenant scoping, authentication, concurrency protection and audit integrity belong on the server.
- Keep fictional prices, approximate locations and illustrative photos explicit. No real personal data, credentials or payments in demo storage.
- Structural changes update the architecture in the same commit. `npm run arch:sync` derives FSD dependencies from local imports; semantic responsibilities are maintained in `system.c4`.
- Run `npm test`, `npm run build`, `npm run build:surfaces`, `npm run arch:check`. Check affected UI at desktop and mobile widths. Publish only the selected website artifact: public `dist/site` or staff `dist/staff`, never LikeC4. Build-time #surface-routes alias chooses public/staff/combined routes; see docs/frontend.md.
- Retired vanilla `src/app.js`, `src/map.js`, root styles and vendored Leaflet are replaced by Vue/FSD and package imports; do not restore them.

- New bookings are pending and reserve inventory until manager confirmation/rejection or cancellation. Do not auto-confirm website bookings.
- Run backend tests with `backend/.venv/bin/python backend/manage.py test booking commerce`; include migration drift check. Never put credentials in source, audit, or logs.
- `backend/commerce` implements a Kaspi-themed simulator, never real bank payments. Freeze check-in terms when creating bookings; cancellation and demo refunds commit together. Refund schedule: >=48h 100%, >=24h 70%, otherwise 0%; same for staff/guest until a different policy is agreed.
- GuestAccount is separate from staff User. Registration/reset requires a challenge; demo OTP must require DEBUG plus GUEST_AUTH_DEMO_OTP. All guest ownership checks use guest_owner, including receipts and payments; reset invalidates earlier sessions. Never merge accounts/bookings by phone alone.
- Native guest sessions use booking/mobile_auth.py and identity models: short-lived opaque access tokens, rotating refresh tokens, replay revocation, account auth-version and per-device revocation. A Bearer token never grants staff access; invalid Authorization must not fall back to cookies. Browser writes still require CSRF. Versioned /api/v1 and legacy /api use the same handlers. Native registration/reset transport and real SMS remain outstanding; see docs/mobile-api.md.
- New uploads have MediaAsset metadata and stable authorized /api/media/files/:id URLs. Keep default storage private (local private-media or configured Supabase S3); never expose storage keys or persist expiring signed URLs. Catalog/review references must pass media_access ownership validation. Avatars require a signed-in guest. cleanup_media is dry-run by default; deletion must retain referenced files. Supabase configuration is not evidence of a live connection.
- Django Admin is /django-admin/ (/admin/ redirects), served by platform_admin_site and restricted to active staff superusers. Domain models are read-only there; mutations use service-backed staff workflows. Do not restore unrestricted UserAdmin or expose password/token/ownership hashes. See docs/admin.md.
