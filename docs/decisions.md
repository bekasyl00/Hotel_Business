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

## 2026-10-23 — Native API, Django operations and owned media

The user requested a stronger server foundation for a future iPhone application, the actual Django administrative site, ordinary photo/video file selection and a guest avatar. The backend remains a transactional modular Django application shared by public web, staff web and future native clients. `/api/v1` and legacy `/api` route to the same handlers; copying business rules into a mobile backend would create inconsistent inventory/payment behavior. The native application itself is not implemented.

`identity` stores native guest device sessions and consumed refresh hashes. `booking/mobile_auth.py` issues opaque 15-minute access tokens and rotating refresh tokens within an absolute 30-day family lifetime. Tokens are stored server-side as HMAC hashes. Refresh invalidates the previous access token; reuse of a consumed refresh token revokes its family. Password reset/auth-version and account deactivation apply to native credentials as well. Guest Bearer identity is separate from staff User, never elevates a simultaneous staff cookie and cannot fall back to anonymous/cookie identity after invalid Authorization. Browser mutations retain CSRF. Native registration/recovery still require the current browser-bound challenge flow; real SMS and a dedicated native challenge transport remain outstanding. `docs/mobile-api.md` records the contract and maintenance command.

The actual Django console is `/django-admin/`, with `/admin/` as a redirect on the backend host. It is separate from the deployed Vue staff site. `platform_admin_site` allows only active staff superusers and provides database-backed counters plus search/filter/read pages for domain models. It replaces the mutable generic UserAdmin and excludes password/OTP/token hashes, ownership secrets and private storage keys. Domain writes stay in the existing transactional service workflows through the staff application; arbitrary admin edits must not bypass reservations, refunds, versions or audit. The login has shared PostgreSQL attempt limits. MFA/SSO and sensitive-record read auditing remain future work; see `docs/admin.md`.

New media has `MediaAsset` metadata tied to catalogue resort, review booking or avatar profile. Normal editor inputs select files from a device. Registered guests can replace/remove their avatar; anonymous guests cannot. Uploads enforce image decoding/EXIF removal, size/count/rolling-byte limits and basic MP4/WebM headers. Video transcoding, codec/duration checks and malware scanning are not implemented. Catalogue/review references validate ownership and media kind before save. The static demo uses IndexedDB for blobs and stable local references, with object URLs created for display; it remains per-browser demonstration storage, not durable shared hosting.

Private delivery uses stable `/api/media/files/:id` URLs with access evaluated on every request. Public visibility requires attached published catalogue content or an approved review; avatars stay owner/scoped-staff protected. Local files are outside the legacy public media root and support range delivery. Supabase S3 configuration uses a private bucket; authorized requests redirect to a URL valid for 60 seconds, which remains usable by its possessor until expiry. Never persist those expiring links in the catalogue. `cleanup_media` dry-runs by default and removes only metadata-backed unreferenced files older than a day when explicitly run with `--delete`. Object-store writes and PostgreSQL commits are not atomic; inventory reconciliation and a complete retention/recovery procedure remain necessary.

Supabase is the selected managed PostgreSQL and private object storage provider. In the supplied project `https://uchqzxxqioixhzbnwcak.supabase.co` (ap-northeast-2), a schema-only export from actual Django migrations was applied to the empty private tynys schema: 25 tables, 26 migration records, RLS enabled and no anon/authenticated schema access. The private tynys-private bucket has been verified. No user or booking data was copied. Django runtime credentials, least-privileged server-role policies and successful application uploads remain unverified. `config/infrastructure.py` prepares PostgreSQL-only connections, an optional dedicated schema/TLS options, pool compatibility and private S3 storage. It does not connect the public browser directly to Supabase or replace Django authentication. `docs/supabase.md` owns the setup/runbook. No cloud backend is claimed from this local source change, and the Vercel demonstration remains a separate environment until the API is deployed and connected.

This entry supersedes earlier current-state statements that native tokens, media ownership/quota checks and guest avatars were absent. It does not close real SMS/Kaspi, cloud deployment, native app release, workspace pagination, account deletion or production load/restore verification.


## 2026-10-27 — Two independent Capacitor iOS applications

- User selected Capacitor and explicitly required separate guest/staff applications, not a website with an audience switch. Separate bundle IDs, Xcode projects and Vite artifacts; shared Vue/FSD domain code. Guest has no staff pages or links. Staff gets phone navigation and card presentation for operational tables. Sites remain independent build surfaces.
- Bundle local assets; never point `server.url` to Vercel. API builds require HTTPS `/api/v1`. Default is explicit demo; separate app demo databases do not synchronize. A shared deployed Django is required for actual cross-device bookings.
- Implement native staff credentials in a separate namespace/models; retain guest isolation and service-layer tenant scoping. 15-minute access, 12-hour absolute staff family, rotating refresh/replay revocation, password/role/resort version validation. Web/native failed-login budget is shared.
- Keychain per bundle ID, no shared access group, no credentials in JS browser storage/logs. One-use rotation is serialized and marked pending before transmission. Offline logout clears local credentials and reports unconfirmed server revocation.
- Common Swift Keychain bridge, native file sharing, privacy manifest, safe areas and native file pickers. App Store readiness is not claimed: native SMS/OTP transport, account deletion, deployed integrations and device/release checks remain. See ios.md and verification.md.


## 2026-10-27 — Mutable product scope, pricing and launch register

The user clarified the product can change substantially: commercial stays, official social-benefit funding and documents must not be modeled as one hotel booking/payment state. Keep the current transactional Django module structure, establish domain boundaries for future benefits/funding/ledger/documents, and use docs/production-readiness.md R01–R34 as the canonical work register. docs/sre.md owns proposed capacity/SLO/load/DR decisions; no claim of Kaspi-scale throughput is supported by current tests. Per-resort locking, unpaginated workspace and large native video downloads are explicit scaling limitations. Android is deferred to the end; do not rebuild/reinstall iPhone apps in this stage.

Implement now: per-room nonoverlapping price periods (exclusive end), per-night integer half-up discounted price and frozen breakdown. Catalogue changes retain resort transaction locking and version/audit; DB exclusion rejects overlaps. `nightly=null` on nonuniform stays is explicitly documented; client rollout must precede enabling seasonal pricing for older API consumers. No catalogue-edit repricing of existing bookings.

User clarified free under-three tariff is an employee choice, not unconditional entitlement. The opt-in switch on each tariff waives only that tariff supplement; room price and all-person capacity remain. Children use declared completed years at check-in, with an adult required. Other age groups, separate places/services and document checks remain R14/R21; do not infer DOB from IIN.

Research identifies national IPAR-based and regional social programmes with differing conditions. Proposed manual/external verification and funding workflows are documented, not active government integrations. Current Supabase region (historical ap-northeast-2) and the Kazakhstan residency requirement require an operator/legal/infrastructure decision before real personal data; subscription upgrade is not a solution to data residency. No new real IIN, medical information, payment or government credentials were used. Official documents require approved issuer/requisites/signature/registration; a stamp image is not proof.

Add minimal live/ready probes with no secrets or DB dependence for liveness. Queues, caches, autoscaling, metrics, error budgets and DR are future implementation and operations, not claims of this patch.

## 2026-10-27 — Payment-first commercial orders and configurable commission (supersedes manager approval)

User removed manager confirmation: new commercial orders hold inventory pending payment, then successful server payment automatically confirms the booking. Manual confirmed/rejected transitions are forbidden. This supersedes earlier approval instructions. Paid/cancelled/expired, funding entitlement and actual bank settlement remain separate concerns. Real Kaspi first, Halyk later: no provider credentials/contracts or real callback endpoints have been invented.

Admin enters commission per resort in staff web/mobile source UI; null means unconfigured, zero explicitly no commission. Freeze rate and half-up KZT amount from the booking total at creation. Manager cannot edit, public/guest output hides terms. Estimates are not payouts/profit; bank fees, split settlement and refund commission allocation require the operator/bank/accountant decision.

New holds default to 30 minutes (server configurable 1–120), capped at advertised check-in. Expiry is audited and idempotent, serializes with payment and inventory under the resort lock; command must be scheduled in deployed environment. Legacy null-expiry holds are preserved pending an explicit migration policy. Old confirmed/unpaid records can still pay. Late bank success after expiry needs reconciliation/refund and cannot blindly confirm a re-sold room.

Only simulator implementation is active: unique successful payment, receipt/status/audit in one transaction; repeat requests cannot confirm twice. Scoped staff simulator is limited to staff-created bookings; no manual payment approval for guest-created orders. Browser CSRF and native audience isolation remain. iPhone rebuild/install remains deferred.


## 2026-11-04 — Staff room planner and room-only manual pricing

The user scoped the hotel-style placement grid to employee surfaces. `/staff/bookings` now defaults to a room/date calendar; list remains for all statuses, including cancellations/expiry. Purple means recorded checkout, blue recorded check-in without checkout, green confirmed/not-arrived, amber an unpaid hold. Calendar dates never invent arrival or departure. It uses the property's timezone, exclusive checkout, clipped bars, separate overlap lanes, room/guest/ID search and 7/14/30-day ranges. Empty active room cells start the ordinary transactional order form. Stay actions reuse existing services; no browser date/color can confirm payment.

The tariff navigation/editor and selector in new staff bookings are removed. Manual booking without `tariffId` prices only the room's seasonal/base price; no hidden default tariff or surcharge. Migration 0009 makes the protected tariff FK nullable and adds `staff_notes`; it does not delete historical tariffs, snapshots or payments. Public checkout and old native callers that still explicitly send a tariff retain their contract pending a separately coordinated public pricing change. Historical terms remain visible in the card. Existing payment-first holds, commission snapshots, capacity and refund rules remain.

`POST /api/v1/bookings/:id/notes` (also `/api`) accepts `version` and `staffNotes` up to 2000 characters. It requires scoped staff identity and browser CSRF, locks the resort, checks version and commits audit with the update. Audit stores operation/version/length, not note text. Guest serializers and demo guest output omit notes. The detail card combines dates, lead guest/count/ages, frozen nightly charges, payment/receipt, notes and recent available audit. It is not an official guest registry or fiscal document.

Boundaries: calendar reads existing unpaginated workspace; date-scoped paginated API/virtualization remain required for large properties. Manual refresh; no real-time sync claim. Same-day orders after advertised check-in, late/walk-in payments, deposits, changing dates/rooms and freeing an early-departure interval require additional explicit workflows; current server constraints remain. iOS binaries and Android are untouched. Migration rollback to non-null tariff is unsafe once room-only rows exist; use forward fixes rather than assigning invented tariffs to history.


## 2026-11-05 — Halyk ePay sandbox before Kaspi: implementation plan

User selected Halyk ePay sandbox first, with an exact booking-amount payment link and automatic server-verified confirmation; Kaspi follows later. This supersedes the previous provider order, not the payment-first booking, frozen pricing/commission, ownership or bounded-hold rules. The requested AI implementation guide is docs/halyk-epay-implementation-plan.md. It is a plan, not an implemented adapter or a verified bank connection.

Official invoice-link documentation has separate sandbox credentials, required email/phone, day-based expiry, and distinct lookup/deactivation authentication. The implementation must verify compatibility with transaction-status credentials before enabling checkout. A return URL, unauthenticated callback, HTTP 200 or a successful status-query result cannot independently confirm a booking. Durable reconciliation must handle lost callbacks, expired holds, late charges and refunds outside database network transactions. Existing simulator history remains separate from bank sandbox facts. No native rebuild, cloud migration, payment or deployment was performed for this documentation change.


## 2026-11-05 — Guest availability calendar and simpler guest password

The user withdrew booking editing after considering payment differences. No amendment endpoint, date/room mutation or edit button is introduced. Frozen booking/payment/receipt terms and existing staff notes remain unchanged.

Public resort pages show a mini calendar only after selecting a room class, filtered by guest capacity. The user's final clarification keeps both scopes: a class-wide calendar on the resort page and a separate exact-room calendar on each room profile. The optional `roomId` must belong to the selected resort/class; visible headings and hints distinguish the two scopes. The bounded no-store API returns daily aggregate availability and continuous-room checkout choices, without guest/booking identities. Day-of-departure remains exclusive, active payment holds block nights, expired holds do not, and property timezone/check-in time controls same-day selection. First click selects arrival; second selects a valid departure within 30 nights and runs the existing full-stay availability check. Creation remains authoritative and transactional.

Guest registration and reset accept 8–128 Unicode characters without mandatory character classes or a common/numeric-password block, as requested. Staff Django validators are unchanged. OTP challenges, authentication limits, hashing and session revocation remain in force. Demo and Django share this policy. This delivery does not rebuild/sync/install either iPhone application.


## 2026-11-05 — Halyk sandbox и общее тестовое окружение

Реализованы отдельные PaymentAttempt/Event, RefundRequest и durable PaymentJob. Только проверенный server-to-server CHARGE с совпадением invoice/terminal/account/amount/currency может автоматически подтвердить pending-бронь. Callback/redirect не являются доказательством; неизвестный исход создания и финансовые расхождения не допускают повторной оплаты вслепую. Старый Kaspi-themed симулятор и его история сохранены отдельно.

Общие официальные sandbox-доступы работают с client_credentials для invoice lookup/deactivation. Live обнаружено: create HTTP 400/code1079 создаёт ACTIVE invoice, поэтому восстановление через lookup обязательно; empty lookup возвращает Records:null; invoice account_id пустой, transaction accountID содержит переданную привязку. Visa/Mastercard отклонены 455 (3DS), AMEX 3340. Успешного CHARGE нет: HALYK_EPAY_PROTOCOL_VERIFIED=False, production payments и публичный simulator выключены. Полная банковская приёмка не завершена.

Django опубликован отдельным Vercel проектом tynys-api, Supabase restored ACTIVE_HEALTHY. Отдельная private schema/роль tynys_stage сохраняет старый tynys; Django migrations применены, вымышленный каталог загружен. TLS verify-full, transaction pooler, приватный S3 write/read/delete проверены. pg_cron вызывает защищённый bounded tick раз в минуту. Это staging с вымышленными данными, не production по нагрузке/праву/платежам. iPhone не пересобирался.

## 2026-11-06 — Kaspi через XPayment, подготовка без приёма денег

По запросу владельца добавляется сторонний XPayment как отдельный банковский provider, рядом с Halyk и историческим симулятором. Владелец ещё не зарегистрирован. Опубликованный API является production; денежный sandbox не документирован. Поэтому подготовка и локальные transport-тесты не считаются банковской приёмкой, а `XPAYMENT_ENABLED` и `XPAYMENT_PROTOCOL_VERIFIED` остаются выключенными. Инструкция и источники: [xpayment-integration.md](xpayment-integration.md).

Provider/environment/merchant scope сохраняются в попытке; смена выбранного нового checkout не должна менять исполнение старых jobs и возвратов. Один attempt на бронь, server-owned amount, tenant/guest ownership, bounded hold и подтверждение под resort lock сохраняются. Подписанный XPayment callback долговечно дедуплицируется и лишь запускает GET-сверку. Он не подтверждает бронь, даже если провайдер прислал `payment.completed`: кабинет умеет отправлять подписанные тестовые события без оплаты.

Не переносим Halyk-специфичные invoice/terminal/refund правила в XPayment и не считаем неизвестный исход POST разрешением повторить списание/возврат. Чеки не генерируются от имени Kaspi; документированный receipt API отсутствует. Один подключённый аккаунт не решает выплаты разным санаториям и комиссию: R01/R16–R19 остаются открытыми до согласования договоров/сверки. Регистрация, реальные денежные операции и обновление установленных iPhone-приложений не входят в эту подготовку. Публикация и результаты проверок фиксируются отдельно.


## 2026-11-08 — Бухгалтерия, документы и медиагалерея

Отдельная роль `accountant` и маршрут `/staff/accounting`: доступ только к назначенному санаторию, финансовым агрегатам/реестру, реквизитам и документам. Администратор назначает роль; управляющий не получает финансовый кабинет автоматически. Operational API отвергает accountant; frontend-guard не считается защитой. Native accountant login пока не добавляется, установленные приложения не меняются.

Очищенные от исходных персональных данных копии трёх присланных XLSX используются как шаблоны, исходные файлы не включаются в репозиторий. Фактический check-out в одной транзакции готовит draft акта/счёта-фактуры. Бухгалтер проверяет реквизиты/НДС и публикует неподписанную копию после сверки полной оплаты. Снимок published неизменяем; исправление через void и новый документ. Нумерация отдельная по санаторию/году/виду. ПКО пока только draft, т.к. банковская оплата не является кассовой операцией. Нет ЭЦП, подстановки печатей, регистрации в ИС ЭСФ или замены банковского чека. Это ещё не полноценный ledger/налоговый учёт.

Первым шести цифрам ИИН нельзя доверять как подтверждённой дате рождения: [разъяснение МВД](https://www.gov.kz/org/migration/press/news/details/132237?lang=ru). UI допускает только необязательную шестизначную подсказку; родитель проверяет/редактирует и подтверждает дату. Полный ИИН не собирается, подсказка не уходит в API. Backend вычисляет завершённые годы на дату заезда и отбрасывает DOB до snapshot/audit: сохраняется только возраст. Старые клиенты могут передавать заявленные годы. Это не проверка личности или льготы. Тарифный opt-in under-three сохраняется.

Галерея получила стрелки, свайп, увеличенный просмотр и native video controls. Файлы сохраняются прежним multipart API с MediaAsset и проверкой области доступа; signed storage URLs не записываются в каталог. RU/KK/EN ключи сохраняют паритет.


## 2026-11-08 — Уточнения владельца: профиль, детский демо-ввод, 15 минут и глобальный бухгалтер

Новая гостевая бронь только после входа; сервер берёт имя/телефон из аккаунта, старые присланные поля игнорируются. Контакты/срок старой брони не меняются при идемпотентном повторе. Новый TTL 15 минут, максимум до check-in. Это заменяет прежние 30 минут и разрешение новых анонимных заказов; legacy-история сохранена. После login возвращаем выбранный номер/даты/тариф, после создания — бронь и оплату.

Владелец явно потребовал одно поле из 12 цифр без DOB/checkbox. Реализована условная демо-интерпретация первых шести цифр для детского возраста: без проверки личности, checksum и официального права. Полный ввод существует только в компоненте, не отправляется/не логируется/не хранится. Производственная достоверная проверка возраста остаётся R14/R21; прежнее решение о подтверждении даты пользователем заменено.

После сообщения о несрабатывающем скачивании проверены опубликованные PDF/XLSX всех трёх видов и браузерные клики: ошибки сервера не воспроизведены. Добавлены preview, загрузка/ошибка рядом с кнопкой, постоянная повторная Download/Open ссылка. Managers получают read-only документы своих броней, гости — только выпущенные собственные копии.

Владелец расширил accountant до всей платформы с аналитикой/планом, затем выбрал собственный кабинет без 1C. Права на чтение отделены от операций размещения и администрирования. Ручные расходы отдельны от банковских событий; idempotency, positive bounds, mode separation, immutable void history. Расчётная комиссия, денежный поток и стоимость заказов отображаются раздельно, чистая прибыль/банк balance не выдумываются. Официальные документы/подписи, закрытие периодов, двойная запись и settlement остаются открытыми. Нативные приложения не пересобираются.

## 2026-11-08 — Аккаунты партнёров, каталог клиентов и достоверный вход

Пользователь подтвердил публичный WhatsApp +77782764005, «Бекасыл Админ». На staff login размещена ссылка wa.me с локализованным обращением; автоматическая отправка сообщений не производится. Подключение санатория — ручное администратором.

Каждый Resort имеет обязательный account FK (PROTECT) на ответственный staff User. Один аккаунт управляет несколькими санаториями. Новый manager создаётся без объектов; затем admin назначает его в настройках санатория. Передача использует версию санатория, resort lock и общий transaction advisory lock для согласования с изменениями ролей. Прежний User.resort остаётся для совместимости, но не даёт прав. Все чтения, медиа, документы и операционные записи ограничены Resort.account. Смена владельца повышает User.version обоих аккаунтов и отзывает native credentials. Бухгалтер не может владеть санаторием; смена владельца на accountant запрещена. Отключённый staff-аккаунт сохраняет привязки, административный контроль остаётся.

Миграция 0011 назначает прежнего manager соответствующего санатория, иначе существующего активного platform admin. Если такого аккаунта нет, миграция останавливается; аккаунт/пароль не выдумывается. Seed требует предварительного admin. Для переноса уже закреплённого объекта служит только versioned resort workflow, не legacy resortId в редакторе сотрудника.

Администратор видит paginated /clients, поиск по имени/телефону, зарегистрированные аккаунты отдельно от legacy browser profiles, историю гостя даже без бронирований. Управление доступом не редактирует подтверждённый телефон, не объединяет по телефону, не даёт impersonation. Отключение/включение повышает auth_version и отзывает web/native гостевые сессии; брони и документы сохраняются. Менеджер/бухгалтер не получают общий каталог клиентов.

Гостевой /profile требует входа на web и native; сохранённые в старом браузере имя/история не означают авторизацию. Pinia объединяет параллельные restore и игнорирует запоздалый ответ до login/logout. Ошибка сети не превращается в скрытый logout. Навигация сотрудников формируется единожды по роли, без повторяющихся analytics/planner. Установленные iPhone приложения не обновляются.


## 2026-11-08 — XPayment v2 и выделенная песочница

Владелец подключил кассу и передал API v2. Read-only запрос принят HTTP 200, но денежные операции не проводились. Новый кабинет предоставляет sandbox с ключом xapi_test_ и кассой test; это заменяет прежнее наблюдение об отсутствии опубликованной тестовой среды. Владелец выбрал сам создать тестовый ключ. Новый транспорт выбирает фиксированный API v1/v2, проверяет тип ключа/окружение и в v2 кассу. Сохраняется legacy v1 production scope; v2 scope включает нормализованную кассу и окружение.

commerce.0007 разрешает XPayment sandbox без изменения старых сумм/событий. Среда фиксируется в попытке и финансовой аналитике. Подписанные callback sandbox не могут запустить production-попытку; подтверждение всё равно требует независимого GET. Смена настроек не перенаправляет старые задания к другой кассе/среде. Одна активная конфигурация XPayment на развёртывание: перед переключением закрыть/сверить старые попытки или сохранить отдельное окружение обработчика. Тесты транспорта и проверка ключа не дают разрешения публично принимать реальные деньги. Production gates остаются закрыты до отдельной приёмки. iPhone не пересобирается.


## 2026-11-08 — отдельное включение принятой XPayment sandbox

Настоящая песочница провайдера прошла paid/declined/failed/expired/cancel и полный/частичный refund. Облачные webhook и GET подтвердили две вымышленные брони общего API; опубликованный API отмены вернул 100%/70%. Разрешается sandbox checkout с отдельным `XPAYMENT_SANDBOX_PROTOCOL_VERIFIED`; `XPAYMENT_PROTOCOL_VERIFIED` остаётся false. Публичный UI явно сообщает об отсутствии списания. Наблюдаемые refund-list `{data,total}` и REFUNDED/PARTIALLY_REFUNDED учитываются только с независимой проверкой суммы/полноты/принадлежности; отражённый возврат не создаёт повторную оплату. Sandbox-приёмка не закрывает реальный пилот, фискализацию или marketplace settlements.


## 2026-11-08 — реальные оплаты выбранных санаториев и временная регистрация

Владелец отказался от публичного sandbox и явно выбрал Altyn Bulak (`altun`) и Көктерек (`kokterek`) для подключённой кассы. Новые production attempts проверяют `XPAYMENT_PRODUCTION_RESORT_IDS` на сервере под блокировкой санатория; пустой список закрывает создание. Удаление объекта из списка блокирует ещё не начатый create job, но не recovery/verify/refund. Старые попытки сохраняют окружение; sandbox не превращается в production. На момент переключения существующие sandbox оплаты отменены/возвращены либо истекли.

Фактический API v2 возвращает `environment=live`. Только на внешней границе это значение преобразуется в production; sandbox/неизвестные значения по-прежнему изолированы. Владелец сам оплатил реальную ссылку на 100 KZT; независимый GET подтвердил CHARGE, кассу/аккаунт/заказ/сумму/валюту. По прямому ответу владельца этот платёж **не возвращать**. Он технический, без бронирования, не добавляется в отчёты бронирований; учесть отдельно при сверке кассы. Подписанный production webhook настроен с разрешения владельца. Возвраты бронирований 100%/70%/0% сохраняются, реальные перевод/возврат не объявляются завершёнными без проверки провайдера. Фактического real refund этого этапа нет.

До SMS-провайдера владелец разрешил регистрацию по имени/телефону/паролю без OTP. Это отдельный `GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION` по умолчанию false, не комментирование защиты и не универсальный код. Номер является неподтверждённым логином; nullable phone_verified_at не заполняется для старых/demo/временных аккаунтов. CSRF/хеширование/лимиты/изоляция истории сохраняются. Вход по паролю доступен; сброс без доказательства владения номером запрещён. Challenge-код оставлен для будущего SMS. Установленные iPhone приложения не меняются.

## 2026-11-08 — комиссия сверх проживания, билет и оплата на месте

Уточнено с владельцем: платформа получает отдельную комиссию **сверх** цены санатория, а всю базовую стоимость клиент оплачивает на месте. Например 280000 KZT проживания + 10% = 308000 всего; онлайн 28000, санаторию 280000. Для Altyn Bulak и Көктерек владелец выбрал 10%; это значение существующей административной настройки commissionPercent, не жёсткая константа и не новый произвольный default 10000. Не применять ранее предполагавшуюся модель вычитания аванса из цены проживания.

Сервер под блокировкой санатория фиксирует paymentTerms v1: accommodationTotal, onlineAmount, onsiteAmount, total, mode=percent и value. OnlineAmount округляется half-up до KZT; неположительная/неуказанная комиссия и результат меньше 1 KZT запрещают новую бронь. Booking.total остаётся базой для совместимости; полная клиентская цена — paymentTerms.total. Публичное bookingFeePercent только для чтения и предварительного отображения. Изменение настройки не изменяет условия старых заказов. Старые брони без paymentTerms получают при чтении v0/full/onsite=0 и сохраняют прежнюю полную онлайн-оплату без backfill. Staff-only commissionTerms теперь имеют basis=accommodation_markup, но не являются банковским split/payout.

Подтверждение брони происходит после проверенной сервером онлайн-оплаты комиссии. Возврат по прежним границам 48/24 часов рассчитывается от фактически полученной онлайн-суммы, не от суммы проживания. Для оплаченной истории создан защищённый билет JSON/PDF; после отмены/возврата он остаётся доступен и показывает недействующий статус. Это собственный билет бронирования, не чек Kaspi и не фискальный документ. Доступ: владелец гостевой брони, управляющий своего объекта, администратор/бухгалтер; открытой публичной ссылки нет.

Оплату базовой стоимости наличными/картой в санатории отмечает администратор или управляющий, только в даты проживания по часовому поясу объекта и до выезда. Сумма берётся из снимка; обязательны актуальная версия и явное подтверждение получения. OnsiteSettlement хранит одну неизменяемую отметку на бронь, метод, сотрудника и время; одинаковый повтор идемпотентен. Это утверждение сотрудника, а не независимый банковский факт. После него обычная отмена блокируется для сверки; заселение новых заказов требует отметку. Бухгалтер не получает право операционного подтверждения.

Счёт-фактура/акт санатория остаются на базовую стоимость проживания. PaidAmount этих документов использует отметку санатория; комиссия/её возврат и общая цена хранятся отдельно. Публикация требует полного подтверждения оплаты на месте. Бухгалтерские received/refunded/net содержат только онлайн-события; onsiteDue/onsiteRecorded показываются отдельно по выбранной когорте созданных заказов. Старые опубликованные документы не переписываются. Полноценный учёт наличных, исправление ошибочной отметки, ПКО/ЭСФ, фискализация, выплаты и банковские комиссии остаются самостоятельными задачами.

Для задержки подготовки оплаты добавлено опциональное выполнение одного leased job в HTTP checkout/refresh после commit; долговечная очередь и scheduler остаются обязательными. Неясный результат внешнего создания восстанавливается GET-сверкой, а не повторным списанием/POST. Ускорение интерфейса не является доказательством оплаты и не обещает конкретную задержку провайдера.

Профиль санатория и номера сохраняет имеющийся контент, но располагает description → галерею фото/видео → необязательный descriptionAfter. У санатория добавлены необязательные публичные staffWhatsApp и twoGisUrl с серверной валидацией; комнаты показывают контакты родительского объекта. booking.0013 и commerce.0008 — аддитивные миграции без изменения старых снимков. Изменения относятся к web/API; установленные iPhone приложения не пересобираются. Факты применения миграций, проверок и публикации фиксируются отдельно, не выводятся из наличия кода.
