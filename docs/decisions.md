# Decisions — 2026-10-22

Chronological decision history. Earlier sections describe their stage, not the current implementation. For current capabilities read [product.md](product.md), for verification/deployment read [verification.md](verification.md). Later entries supersede earlier choices explicitly.

## Historical stage — initial vanilla prototype

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

## Historical interface contract — initial prototype

Primary task: select a sanatorium on a map, choose dates/guests, a free room and a tariff, inspect the total, create and cancel a clearly identified demo booking. Visual direction: calm forest green, warm white, compact controls, photography and geographic price pins. Target viewports: 1440x900 and 390x844.

States: map loading; empty filtered list; invalid dates; missing map tiles with usable list; successful local confirmation; storage error with no false confirmation. Permission requests are not used: no geolocation, notifications or payment access.

## 2026-10-22 — Vue staff workspace (historical stage before backend)

The user replaced the vanilla-only constraint with Vue 3, Pinia and FSD; i18n is explicitly deferred. Both the public booking site and staff workspace now use Vue SFCs. Vite replaces the development file server and hand-written static build. Leaflet is imported from its package; the duplicate vendor directory and vanilla entry points are retired.

FSD uses app, pages, widgets, features, entities and shared. Slices expose root APIs. `scripts/check-fsd.mjs` checks local import direction and cross-slice public entry points; the architecture generator now walks Vue/JS recursively and draws actual slice dependencies. This is a static import check, not arbitrary semantic verification.

Rooms are normalized as physical inventory, tariffs are scoped to a resort, bookings snapshot their price and descriptive fields. The public site and staff console share the same demo transport/database. Admins create/archive resorts and assign managers; managers operate only their own resort in the adapter. Conflicting updates return 409 using record versions. Referential deletion is refused; bookings are cancelled and resorts archived to retain history.

`shared/api` provides interchangeable demo and HTTP transports. The demo implements API-shaped operations in app/providers; the HTTP contract is documented separately. There is no backend, real authentication, immutable audit or shared multi-device data yet. Role selection is intentionally labelled demo. A future server must independently enforce every permission and integrity constraint.

## 2026-10-22 — Django backend and manager approval

The user selected Django + DRF + PostgreSQL and explicit manager approval. The modular backend is in `backend/booking`: models, serializers, services and HTTP views. Existing Vue API paths remain stable. Website and manual bookings start `pending`; both pending and confirmed reservations block overlapping dates for the same physical room. Rejection or cancellation releases inventory. Pending requests currently have no automatic expiry; managers must process them. Expiry policy, notification delivery and payments are future decisions.

Guest checkout uses name/phone and an opaque server-session owner; staff accounts use email/password and Django cookie sessions. Guest self-registration and cross-device guest accounts are not implemented. New managers receive an admin-set initial password; email invitations/reset delivery are not yet connected. Passwords are never returned or audited. POST/PATCH/DELETE require CSRF even for anonymous requests/login.

The API calculates prices, snapshots booking details, serializes changes per resort, checks record versions and records audit in the same transaction. PostgreSQL exclusion constraint independently rejects overlapping pending/confirmed rows. A UUID request key prevents duplicate booking submission; reused keys with a different payload or owner return 409. Checkout dates are exclusive. Catalog deletion with historical booking references is refused.

Local development uses Vite's same-origin /api proxy. Production requires an HTTPS same-origin reverse proxy (or an explicitly configured hosting proxy), private PostgreSQL, backups and secrets. Vercel remains a separate demo until a real backend host is selected and verified. No automatic publication of an unconfigured API build.

## 2026-10-22 — Expanded platform, profiles and commerce simulator

The user clarified that the platform is much broader than the initial booking flow. Completing an implementation step must not be described as completing the whole product. `docs/product.md` now owns the capability map and explicitly separates implemented source from proposed future work; `docs/verification.md` continues to own evidence and deployment state.

Discovery remains map-first, with categories in the header. Dates move out of the home search and into the selected property's profile. Properties and physical rooms have stable routes, descriptions, class/amenities and photo/video galleries. Category/class choices are initially fixed in code, not user-configurable taxonomies or certified ratings.

Tariffs distinguish regular and discounted prices. Discounts apply to the full nightly room-plus-supplement amount, rounded half-up to integer KZT before multiplying by nights. Server price snapshots include regularNightly, discountPercent, priceKind, nightly and total. Catalogue edits do not rewrite them.

The user specified a 70% partial refund. The implemented schedule is 100% when at least 48 hours remain, 70% from exactly 24 to less than 48 hours, and 0% below 24 hours. The property advertises a configurable check-in time and IANA timezone; the resulting timestamp and policy are frozen in each new booking. Both staff and guest cancellation use that schedule. A different policy for provider-caused cancellation remains unresolved. Preview is informational; cancellation recomputes under the transaction lock and stores the final result.

`backend/commerce` is a separate Django app for demo payment attempts and refunds. It is an internal Kaspi-themed simulator, not a connection to a Kaspi API or official sandbox. Payment follows manager confirmation, belongs to the website booking owner and is allowed before check-in. Simulated failure can retry, while idempotency and a database constraint prevent multiple successful payments. Booking cancellation, refund and audit share one transaction. No money or bank credentials are involved.

Reviews are tied one-to-one to an owned completed confirmed stay. They support rating, text and photos, plus moderation and a staff reply. Only approved reviews are public and affect aggregate rating. General public comments, discussions, editing/appeals and a final moderation policy remain separate future work.

File upload is now implemented locally: staff catalogue images/video and eligible guest review images. Images are decoded/re-encoded with EXIF removed; videos receive only basic header/size checks. Files live in local Django storage, not cloud object storage. Quotas, orphan cleanup, media-reference ownership, transcoding and production serving remain future work. Existing media sources may also be validated HTTPS URLs.

Guest ownership still depends on the browser's server session; guest accounts, recovery and cross-device access are not implemented. Notification delivery, reservation/payment expiry, real payments, cloud API/DB deployment, pagination and seasonal pricing remain outside this delivered step. Vercel remains a separately deployed static demo until explicitly connected to a deployed API. The generated FSD graph follows current imports; the semantic system map is updated with catalogue, reviews, media and commerce responsibilities.

## 2026-10-23 — Analytics, session profiles, stay operations and receipt provenance

The user added staff analytics as a separate page. Its metrics are event-based: request value by booking creation, successful demo payments by payment creation and refunds by refund creation. Net receipts may be negative and are not profit; costs/taxes/commissions are absent. Reviews count all created records, while average uses approved records. Periods are inclusive in Asia/Almaty, with equal-length previous periods and zero-filled day/week/month buckets. Tenant filters apply on the server. Breakdowns cap at500 ranked records but total/series cover the entire permitted scope. Legacy demo refunds without timestamps are excluded from period accounting and disclosed, not assigned fabricated dates.

Guest history now has a session-owned GuestProfile with contact details, still without guest registration or cross-device recovery. Staff guest views expose only their scoped booking history. Separate check-in/check-out timestamps track actual operations on confirmed paid bookings; check-in requires a stay date and cancellation is refused after arrival. Early checkout does not implicitly rewrite inventory dates or refund rules.

The user clarified that the eventual payment receipt must originate from Kaspi. Current payment is a simulator, so the delivered JSON/PDF is explicitly source:demo, non-fiscal and not a bank receipt. Future real integration must obtain the provider's receipt file/URL after verified payment rather than presenting a generated document as provider evidence. No provider API was invented or connected.

A successful demo payment freezes receipt details without phone, including original amount and booking/resort/room/tariff information. Refund information is appended separately. Legacy paid rows freeze missing receipt metadata on first authorized read with a restoration label. JSON/PDF access requires the guest owner or a staff member with resort access; responses are no-store. The UI can download/share a file through a user action, with no public personal-data share token or automatic external message. Backend PDFs use pinned ReportLab and embedded Noto Sans under included SIL OFL licence; static demo uses the same licensed regular font.

## 2026-10-23 — Phone accounts, languages and separate web surfaces

The user selected Russian, Kazakh and English, and explicitly deferred real SMS delivery. `shared/i18n` owns vue-i18n JSON dictionaries, locale persistence and formatting. Tests compile every message and check key/placeholder parity. Catalogue content is author-supplied; translation of that content is separate from interface localization.

GuestAccount is separate from staff User. Browser sessions keep a stable guest account identity and auth-version; reset revokes old sessions. Register adopts only the initiating anonymous owner's profile/history, while login never merges by phone. OTP is hashed, short-lived, single-use, browser-bound and attempt-limited. Demo issue/redeem require DEBUG plus an explicit flag; production stays closed until real delivery is implemented. The static transport mirrors these semantics for fictional data but is not a security boundary.

The guest site and staff workspace have separate Vite route entries/builds and Vercel projects. `#surface-routes` is resolved at build time and manifest checks prevent the wrong pages from entering each build. Shared FSD layers and one Django domain API remain the foundation. Separate static origins do not share demo storage; a cloud API is required for shared inventory and cross-device operation. Staff receipt routes require staff authentication; actual receipt access remains server-scoped.

Future iOS/Android clients are planned, not implemented. Keep the transactional modular backend; add mobile auth, versioned API compatibility, account deletion, secure device storage and store release workflows before a native release. External registrations and launch gates are recorded in `docs/production-readiness.md`. This entry supersedes earlier statements that guest registration and i18n were deferred.
