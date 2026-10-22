# Decisions — 2026-10-22

1. The first product is a working vanilla HTML/CSS/JavaScript prototype. A static development server is only a file server.
2. The geographic map is the primary discovery surface, following the user's screenshot. Desktop: list + map + property panel; mobile: map first, list below, property sheet over it.
3. Leaflet 1.9.4 is vendored locally. OSM tiles require internet and visible attribution. Production tile hosting/provider is undecided; the public tile service has no SLA. No prefetching or bulk tile downloads.
4. Six demonstration properties near Kokterek, three room categories, three tariffs. Coordinates are approximate. The supplied screenshot is a UX reference, not a verified inventory source. Photos are generic illustrations.
5. Prices are per room per night. Meal/wellness supplements are per guest per night. The date interval excludes checkout day. Category capacity limits all bookings. Dates are date-only; nights use UTC arithmetic.
6. Demo holds in app.js illustrate occupied units. User bookings persist locally. Cancellation releases a unit. Storage is re-read before booking and cross-tab events refresh the UI, but localStorage is not transactional: production race protection requires a server/database.
7. LikeC4 is the architecture viewer. `system.c4` describes responsibilities; `modules.c4` is generated from real local ESM imports. `npm run arch` watches src changes and regenerates the dependency model; build/check also run arch:sync. Model edits trigger viewer updates. Semantic architecture still requires review.
8. Initial decision: no hosting, backend framework, database provider or payment provider was selected. Update: Vercel hosts the static demo, with GitHub Pages also configured; backend, database and payments remain undecided.
9. Assets: generic photos from Unsplash (photo-1566073771259-6a8506099945 and photo-1611892440504-42a792e24d32). Font: Manrope via Google Fonts with system fallback. No personal data is requested by the demo.
10. Publishing: both Vercel and `.github/workflows/pages.yml` publish only `dist/site`: HTML, CSS, JavaScript, images and Leaflet. LikeC4 is a local development tool (`npm run arch`) and is not included in public artifacts. Its model is still checked in CI. Public access does not turn localStorage into shared inventory.
11. Vercel hosts https://vercel-site-puce-two.vercel.app and is connected to the GitHub repository. `vercel.json` runs `npm run build`. GitHub Pages and its publishing workflow are disabled after its delayed initial deployment; the old public architecture was removed. The workflow is retained as an inactive website-only fallback.


## Interface contract

Primary task: select a sanatorium on a map, choose dates/guests, a free room and a tariff, inspect the total, create and cancel a clearly identified demo booking. Visual direction: calm forest green, warm white, compact controls, photography and geographic price pins. Target viewports: 1440x900 and 390x844.

States: map loading; empty filtered list; invalid dates; missing map tiles with usable list; successful local confirmation; storage error with no false confirmation. Permission requests are not used: no geolocation, notifications or payment access.

## 2026-10-22 — Vue staff workspace

The user replaced the vanilla-only constraint with Vue 3, Pinia and FSD; i18n is explicitly deferred. Both the public booking site and staff workspace now use Vue SFCs. Vite replaces the development file server and hand-written static build. Leaflet is imported from its package; the duplicate vendor directory and vanilla entry points are retired.

FSD uses app, pages, widgets, features, entities and shared. Slices expose root APIs. `scripts/check-fsd.mjs` checks local import direction and cross-slice public entry points; the architecture generator now walks Vue/JS recursively and draws actual slice dependencies. This is a static import check, not arbitrary semantic verification.

Rooms are normalized as physical inventory, tariffs are scoped to a resort, bookings snapshot their price and descriptive fields. The public site and staff console share the same demo transport/database. Admins create/archive resorts and assign managers; managers operate only their own resort in the adapter. Conflicting updates return 409 using record versions. Referential deletion is refused; bookings are cancelled and resorts archived to retain history.

`shared/api` provides interchangeable demo and HTTP transports. The demo implements API-shaped operations in app/providers; the HTTP contract is documented separately. There is no backend, real authentication, immutable audit or shared multi-device data yet. Role selection is intentionally labelled demo. A future server must independently enforce every permission and integrity constraint.
