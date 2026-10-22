# Project navigation

Read `architecture/system.c4`, `architecture/modules.c4`, and recent `docs/decisions.md` before structural changes. Current checks and limitations: `docs/verification.md`. Verify documentation against source.

- Vue 3 + Pinia + Vue Router + Vite. User selected FSD. Russian interface; i18n deferred. Backend is not implemented.
- FSD dependencies: app → pages → widgets → features → entities → shared. Import another slice through its root public API; no sideways imports. `npm test` checks local JS/Vue imports.
- `src/app/providers/demo.js` implements the demo transport. `src/shared/api` owns the HTTP boundary. Contract: `docs/api-contract.md`. Views never access localStorage directly.
- `src/entities/booking/model/rules.js` owns date rules. Record/version/reference validation lives in the demo adapter until a backend exists.
- Roles in the frontend are not security. Production tenant scoping, authentication, concurrency protection and audit integrity belong on the server.
- Keep fictional prices, approximate locations and illustrative photos explicit. No real personal data, credentials or payments in demo storage.
- Structural changes update the architecture in the same commit. `npm run arch:sync` derives FSD dependencies from local imports; semantic responsibilities are maintained in `system.c4`.
- Run `npm test`, `npm run build`, `npm run arch:check`. Check affected UI at desktop and mobile widths. Publish only `dist/site`, never LikeC4.
- Retired vanilla `src/app.js`, `src/map.js`, root styles and vendored Leaflet are replaced by Vue/FSD and package imports; do not restore them.
