# Проверки

## 08.11.2026 — переход к реальной кассе и регистрация без SMS

- Владелец явно выбрал Altyn Bulak / Көктерек. Backend ограничивает новые production attempts списком `altun,kokterek`; frontend показывает доступность по тому же списку. Existing attempts/verify/refund сохраняются; отозванный объект не запускает новый create job.
- Реальный API вернул `environment=live`, что первоначально было отвергнуто. Существующий неоплаченный счёт восстановлен GET, отменён и проверен; слепого повторного POST не было. После исправления получена настоящая `qr.kaspi.kz` ссылка. Владелец самостоятельно оплатил **100 KZT**, независимый GET подтвердил **CHARGE** 08.11.2026 21:41:41 Asia/Almaty, аккаунт/кассу/заказ/сумму/валюту. Счёт вне бронирования; владелец запретил возврат. Real refund не проверен и не заявляется.
- Production webhook создан с отдельным секретом, лишняя первоначальная подписка без секрета удалена с разрешения владельца. В конце настройки остаётся одна подписанная production подписка. Секреты не находятся в Git/frontend; настраиваются только для Django/Vercel.
- `booking.0012_guest_phone_verification` применена в Supabase `tynys_stage`. Временный direct register — отдельный server flag, без DEBUG/демо-OTP. Старые и новые временные номера не считаются подтверждёнными. Reset без challenge не разрешён.
- Полная регрессия **260 Django tests** на отдельном PostgreSQL 17 прошла; затем **58 targeted payment tests** после normalizer live, включая чужую среду, webhook-only trigger, allowed scope/revocation/recovery. Auth coverage: duplicate/concurrent register, CSRF, no-reset bypass, password hashing и owner isolation.
- **111 frontend tests**, FSD **124 files / 315 imports**, build/build:surfaces/arch:check — pass. Local PNG QR генерируется локально без внешнего сервиса: allowed production390px → ссылка+QR, excluded390px без действия оплаты, existing sandbox1440px сохраняет тестовый режим; overflow отсутствует. Production dependencies audit: 0 vulnerabilities.
- Реальный компонент регистрации проверен на local fixture при 390/1440 px: no overflow; submit отправляет только name/password/phone и переходит в профиль, SMS-поля отсутствуют. Recovery в KK закрыт с объяснением. Это UI fixture, не доказательство deployed регистрации.
- **Опубликовано, runtime/frontend `6848cd7`:** API `dpl_BM7v1xBGBvdpS5GXn7VVCgrA4gwb`, public `dpl_7ucUcNKSSEdLr3H5WXjNm92kYCdV`, staff `dpl_GENKexkjdXeEwVsLe8VsZWUJ9nYr` — READY. Stable URLs: [клиенты](https://vercel-site-puce-two.vercel.app), [сотрудники](https://tynys-staff.vercel.app/staff/login), [API](https://tynys-api.vercel.app). Health live/ready HTTP200; обе website API-прокси возвращают production/available=true и только `altun,kokterek`. Index/entry JS совпадают с опубликованными артефактами. LikeC4 и native не публиковались.
- Через опубликованный public API проверены регистрация вымышленного QA-гостя без OTP, logout и повторный вход по паролю. `phoneVerified=false`, восстановление пароля без SMS закрыто. Credentials сохранены только в игнорируемом 0600 файле.
- Через тот же public API создана бронь Altyn Bulak с серверной суммой **24 000 KZT**; облачный worker получил настоящую ссылку Kaspi. Счёт **не оплачивался**: бронь отменена, номер освобождён, provider GET подтвердил `CANCELLED`, `deactivated_at` заполнен. Create/deactivate/verify jobs завершены `done`; повторная GET-сверка восстановилась после временного `bank_unavailable`. Денег/возвратов по этой проверке нет. Это проверка production checkout/cancel, не доказательство оплаченной production-брони.
- **Инцидент webhook HTTP401 устранён:** production-подписка первоначально отправляла события в старый runtime с sandbox-секретом. После публикации согласованной production-конфигурации настоящее `payment.cancelled` принято **08.11.2026 21:54:18 Asia/Almaty**: XPayment показывает «Доставлен», **HTTP200, 0-я попытка**, предупреждение о недоставке снято. В Django ровно один `WebhookDelivery` этого события. Старые exhausted401 сохранены в истории; они не переименованы в успешные. HMAC/tenant/environment проверки не ослаблялись. Технические 100 KZT отдельно проверены GET и по просьбе владельца не возвращались.


## 08.11.2026 — XPayment v2: сквозная песочница

- Начальная полная регрессия: **243 Django tests** на изолированном PostgreSQL 17. После учёта фактических ответов refund повторно прошли **109 commerce tests**. Ruff, migration drift и `git diff --check` — pass. `commerce.0007` применена в Supabase `tynys_stage` (новых таблиц нет).
- **102 frontend tests**, FSD **123 files / 313 imports**, build, public/staff surfaces и arch:check — pass. RU/KK/EN parity сохранена. Реальный компонент оплаты проверен на локальном изолированном UI harness при 390/1440 px без overflow; это UI-проверка, не банковская операция.
- Внешний sandbox API v2: создание/GET, paid, declined, failed, expired, cancel, полный и частичный возвраты прошли. Фактические QR_TOKEN_CREATED, `{data,total}` и REFUNDED/PARTIALLY_REFUNDED добавлены в адаптер и регрессию. Запросы выполнялись только тестовым ключом/кассой test.
- Подписка XPayment создана с разрешения владельца; тестовые уведомления оплаты/возврата доходят до облачного callback. Две вымышленные брони автоматически confirmed после независимого GET, обе видны staff workspace. Отмена через опубликованный HTTPS API рассчитала 100%/70%; сервер независимо подтвердил возвраты **24 000 / 16 800 KZT**, по одному применённому charge/refund, sandbox, все jobs done. Номера освобождены.
- После открытия sandbox gate создана третья бронь и checkout через **публичный сайт `/api/v1`**, без локального override. Ссылка создана облачным scheduler; реальный тестовый исход XPayment автоматически дал `succeeded/confirmed` через опубликованный API. Затем отмена через тот же сайт завершилась полным sandbox-возвратом **24 000 KZT**; номер освобождён. Внешняя QR-страница показывает сумму/статус, без кнопок результата: UI-подсказка исправлена. Обработчик запускается раз в минуту, поэтому создание/сверка могут ждать следующего tick; это текущий предел тестового стенда, не мгновенная банковская обработка.
- Vercel READY: API `dpl_GvcyB6gRxK4v7XyhMfA3rbhjKRx1` (runtime 7c16e01), public `dpl_6rB7NQB1oETpmQNafxXrFSnhKxMt`, staff `dpl_Aw2yYwEFEhBvdXHk1puVEHHvRF59` (frontend dce1960). Stable public/staff `/api/v1/payments/config`: XPayment/sandbox/available=true; health live/ready 200. Оба опубликованных index/entry JS совпали с изолированными артефактами; private env paths 404. Только выбранные сайты/API, без LikeC4/native/секретов.
- Реальные денежные операции не выполнялись; production acceptance false. Ключи/секреты только в игнорируемых 0600 файлах и серверных настройках Vercel. Старые опубликованные в чате live-ключи необходимо заменить до реального пилота. Реальные чеки, split, SMS и денежная приёмка остаются открытыми в production-readiness.md. iPhone не пересобирался.

## 08.11.2026 — обязательный профиль, 15 минут, документы и бухгалтер всей платформы

- **226 Django tests** passed on isolated PostgreSQL 17. Coverage: registered guest ownership/profile contacts, no anonymous creation, frozen retry deadline, child validation/no IIN persistence, global accountant reads with forbidden operational writes, manager document tenancy, expense idempotency/void/version/CSRF/mode isolation, finance sums and XLSX formula escaping. **96 frontend tests** pass; FSD 120 files / 307 imports, migration drift, changed-file Ruff, Django deploy check, build, public/staff route boundaries and architecture validation pass.
- Browser local real-API QA: anonymous checkout returns to selected room/dates after login; guest name/phone inputs absent; one 12-digit child input, no child DOB/confirmation fields; request contains derived DOB only, no full IIN or contacts. Booking opens payment view with 15:00; reload uses same deadline. 390px view, no page overflow/errors. These are fictional fixtures, not real identity verification.
- Document export bug was not reproducible in the old published admin path: 3 types × PDF/XLSX returned valid bytes, and browser clicks downloaded both formats. New UI adds PDF preview, inline loading/errors and persistent Download/Open links. Local registered guest's own released act/invoice PDF/XLSX and preview tested at 390px. Published manager own-booking document GET returned 200; foreign-access denial is covered by PostgreSQL tests. No new public share URL.
- Platform accountant browser QA: all properties available, expense saved locally, report XLSX downloaded, PDF preview and both file downloads work; analytics/planner accessible at 1440/390px, no mutation controls for accountant, no console page errors. Published accountant independently logged in and repeated report/preview/download/planner checks. Actual Django Admin superuser login verified.
- Supabase staging **commerce/0006** applied. AccountingExpense RLS=true; anon/authenticated SQL SELECT both false. Existing schema/catalogue preserved. No native app rebuild/sync/install; no real payment/SMS performed.
- Vercel READY: API `dpl_7tDEcardMNQYraW96fYo1dx9jcDb`; staff final `dpl_3gXFw1xAeZtGRiZ4xt89w26EfvgE`; public `dpl_F83Txf4h3U2UZtD38LwGaLAroeDL`. Stable public/staff/API URLs retained. Live/ready probes HTTP200. Artifacts isolate selected website/API, not LikeC4/native/config secrets.
- Live API through website proxies: global accountant accounting/workspace/analytics/XLSX HTTP200, operational write403; anonymous guest booking401. Fictional registered guest booking used profile contacts, returned **900-second hold**, retry retained deadline, then cancelled successfully. Live public mobile layout preserved room/date return after login and the new child form.
- Limits: public new registration/reset requires a real SMS provider (DEBUG/demo OTP remain off). Fictional test guest credentials saved only in ignored 0600 backend/.env.stage.accounts. Payment checkout remains available=false until bank acceptance. Accounting copies are unsigned/not registered ESF; manual expenses are not bank transactions; commission is an estimate before settlement/refund reconciliation; full double-entry/profit/period closing remains unimplemented. Owner chose own cabinet, no 1C connection is claimed. See accounting.md and production-readiness.md.

## 08.11.2026 — бухгалтерия, галерея, детский возраст и публикация

- **217 Django tests** on isolated PostgreSQL 17 passed (booking + commerce). Includes actual checkout creating drafts, idempotency, snapshot immutability, accountant/admin/manager access, tenant/guest ownership, CSRF, password hashing, literal SQL search injection, spreadsheet formula escaping and DOB/age validation. Migration drift, Ruff and `check --deploy` passed.
- **94 frontend tests**, FSD **113 files / 283 imports**; build, public/staff surfaces, route isolation and LikeC4 validation passed. No native build/sync/install. RU/KK/EN keys/placeholders remain aligned.
- Local real API multipart upload: two JPEGs + 1.1 MB MP4 attached to both resort and room, persisted and reloaded. Browser observed image 2/3 after navigation/swipe, video readyState 4 / playing / duration 5.055 s, enlarged viewer pauses the inline player. Desktop and 390 px checks have no document overflow. QA video: MDN CC0 flower.mp4, only local fixture.
- Three XLSX templates sanitized (no source IIN/IBAN/people preserved), rendered PDF pages inspected; Russian amount in words, blank signatures/stamps, draft/unsigned notices. Local browser released act and downloaded protected PDF HTTP 200. These are not registered ESF or bank receipts; PKO release is blocked.
- Supabase staging migrations booking/0010, commerce/0004 and commerce/0005 applied. Four new tables have RLS enabled, anon/authenticated SELECT denied; owning Django role used because connector DDL role lacked ownership. Existing private schema and data preserved.
- Vercel **READY**: API `dpl_8PvYBWr44PrDHNPetnmhmdtLGMCy`, staff `dpl_7JoRjXPBYkt6WEyZ91AkxwYduTb3`; public `dpl_HMwFX4dxyeHiYYdtZbPQKwJ5My7z`. Stable addresses: [public](https://vercel-site-puce-two.vercel.app), [accounting](https://tynys-staff.vercel.app/staff/accounting), [Django Admin](https://tynys-api.vercel.app/django-admin/). Artifacts contain only selected sites/API; no env secrets, native app or LikeC4.
- Published accountant browser login/redirect passed at 1440 and 390 px; RU/KK/EN switched, no pageerror, unauthorized operational route redirects to accounting. Screenshots: output/accounting-live-desktop.png, accounting-live-mobile.png, accounting-live-kk.png, accounting-live-en.png.
- Live HTTP: health/live, health/ready and catalog 200. Authenticated accountant/accounting 200; workspace and analytics 403; foreign resort and unknown document 404; manager/accounting 403; anonymous/accounting 401. Demo accountant created via admin API, scoped to one resort; password only in ignored mode-0600 backend/.env.stage.accounts. Live public expanded gallery opens and loads at 390 px.

Limits: no real personal data/bank charge used; Halyk/XPayment acceptance gates remain closed, public simulator and demo OTP disabled. Upload cap 4 MB. Full accounting ledger, bank reconciliation acceptance, official ESF/EDS, cash operations, document list beyond latest 200 and government eligibility are not complete. Six-digit hint is optional/unverified; parent confirms DOB, server stores only age at check-in. See production-readiness.md.

## 06.11.2026 — подготовка XPayment / Kaspi

- Backend: **201 тест** на отдельном реальном PostgreSQL 17 — pass. После уточнения блокировок job и восстановления при закрытом gate повторены **38 payment flow/concurrency тестов** — pass. Из новых проверок: 21 transport-тест адаптера и 16 integration flow-тестов. Проверены закрытые gates, merchant/provider binding, HMAC/dedup, подписанный fake-success без подтверждения, поздние/неверные платежи, восстановление без повторного POST, возврат и разделение финансовых источников.
- Frontend: **92 теста**, FSD **108 files / 269 imports**; `npm run build`, `npm run build:surfaces`, `npm run arch:check` — pass. RU/KK/EN parity сохранена. Ruff, `makemigrations --check --dry-run`, `git diff --check` — pass. Новая migration `commerce.0004` прошла на тестовой PostgreSQL; cloud schema этой итерацией не менялась.
- UI проверен на изолированном mock harness: desktop 1440×1000 и mobile 390×844, без горизонтального overflow. Открытие сохранённого XPayment при другом текущем provider, недоступная конфигурация без ссылки, RU/KK/EN. Снимки: `output/xpayment-desktop.png`, `output/xpayment-mobile-en.png`, `output/xpayment-unavailable-mobile-kk.png`. Это не банковские/live-site проверки.
- Офлайн `check_xpayment`: настройки отсутствуют, оба gate false; секреты не выводятся, сетевых запросов нет. Подготовлены [инструкция подключения](xpayment-integration.md) и `backend/.env.xpayment.example`.

Банковская приёмка XPayment не выполнялась: аккаунт/ключи владельца отсутствуют, создание реальных платежей/возвратов и регистрация подписки не производились. Денежный sandbox в опубликованной документации не найден; mock transport и подписанный webhook-тест не означают оплаты. Флаги включения и проверки протокола закрыты. Реальные чеки, split/выплаты санаториям, нагрузка/SLA остаются работами [единого реестра](production-readiness.md). Деплой этой версии не выполнялся; iPhone-приложения не обновлялись.

## 05.11.2026 — общий облачный API и Halyk sandbox

- Backend: **164 теста** на отдельном реальном PostgreSQL 17, включая duplicate/concurrent CHARGE, чужой owner/tenant, CSRF/Bearer, forged callback, late/extra/mismatched charge, unknown-create recovery, no network inside SQL transaction, refund intent/verification, lease recovery и schema/provider fixtures. Ruff и migration drift — pass; stage `check --deploy` — 0 issues.
- Frontend: **90 тестов**, FSD 107 files / 263 imports; build, API build:surfaces и LikeC4 validate — pass. RU/KK/EN key/placeholder parity сохранены.
- Supabase: Django migration chain применён в отдельную private tynys_stage; 33 RLS tables, restrictive server login, TLS verify-full, private S3 write/read/delete собственного JPEG — pass. Старый tynys сохранён.
- Live HTTPS: public и staff `/api` обращаются к одному Django. Тестовая бронь `07b77f32…` с public видна manager Altun; чужой guest session её не видит; checkout gate возвращает 503. Этой вымышленной записи сократили hold для проверки cron: pg_cron самостоятельно перевёл её в expired; HTTP tick 200.
- Через браузер создана бронь `ce3d1022…`, №112, 12–15 ноября; она видна в кабинете сотрудника. Проверены 390px и 1280px, без overflow документа. Платёжный диалог показывает недоступность sandbox; финальный client console — без ошибок. Снимки `output/halyk-{guest,staff}-live-mobile.png`, `output/halyk-payment-unavailable-mobile.png`.
- Vercel: отдельные client/staff/API проекты, API регион icn1 рядом с Supabase Seoul. Использовать реальный cwd артефакта и `--local-config vercel.json`: при вызовах из корня с одним --cwd наблюдалось наследование чужих routing settings. API не должен содержать frontend rewrite на самого себя. Итоговые deployment IDs/SHA — `output/halyk-final-deployment.json`.
- **Банковская приёмка не завершена:** shared Halyk OAuth, create/recovery, lookup, deactivate/ANNULLED работают; Visa/Mastercard 455, AMEX 3340, lookup REJECT. Нет доказательства успешного CHARGE/refund/callback. Protocol gate закрыт, public simulator выключен; реальные деньги/персональные данные не использовались. Подробности: [halyk-sandbox.md](halyk-sandbox.md).
- SMS отсутствует: DEBUG=False, demo OTP выключен; регистрация/сброс через SMS пока недоступны. Vercel uploads ограничены 4 MB. Не проверены production capacity, backup restore, настоящий эквайринг, официальные документы. Native iPhone/Android не менялись.


## Календари доступности и гостевой пароль — 5 ноября 2026

- Календарь класса на странице санатория и отдельный календарь физического номера; интерфейс явно различает области. Занятые ночи, эксклюзивный день выезда, вместимость, активные/истёкшие удержания и непрерывная доступность одного номера проверены в demo и Django. Редактирование брони отменено пользователем и не добавлено.
- `npm test`: **90 tests**, FSD **103 files / 252 imports**; `npm run build`, `npm run build:surfaces`, `npm run arch:check` pass. Backend: **142 tests** на изолированном локальном PostgreSQL 17 (не SQLite); Ruff и migration drift pass. Для тестов поднят отдельный процесс PostgreSQL: Docker daemon не отвечал. Производственная БД не менялась.
- В браузере проверены выбор класса, перенос диапазона в поиск, занятость отдельного номера, разрешённый выезд перед занятой ночью, RU/KK/EN и мобильная ширина 390 без overflow; desktop 1280. В календаре названия месяцев/дней берутся из переводов, включая қазақша в WebKit. Guest register/reset: 8–128 символов без требований к составу; серверные тесты проверяют границы, хеширование и отзыв сессий. Staff policy сохранена.
- Public Vercel deployment `dpl_J3mG1QGEoKwJLjyK36swU3rzgwtT` **Ready**: https://vercel-site-puce-two.vercel.app. Опубликован только `dist/site` из изолированного каталога. HTML и entry assets на публичном alias побайтно совпали со сборкой; SHA-256 index `ffecd0065b65d74887147803024de95123fb9e9d8e168e53bec350709665e85c`. Deep links `/resorts/altun`, `/rooms/altun-112`, `/account/register`, `/account/reset-password` — 200; файлы секретов/backend/architecture — 404. Staff index до/после не изменился.
- Live room calendar проверен на 390×844, browser warnings/errors пусто. Снимок `output/calendar-room-live-mobile.png`; HTTP evidence `output/calendars-live-check.json` (игнорируются Git). Сайт остаётся demo с локальными данными браузера. Backend API не опубликован, Supabase не обновлялся; iPhone-сборки не трогали.

## Публикация кабинета сотрудников — 5 ноября 2026

- Обновлён только production-проект `tynys-staff`: https://tynys-staff.vercel.app/staff/login. Vercel deployment `dpl_7eR1SKdK7EkAz4QgwiQBsvVznqru` — **Ready**, production alias проверен. Исходный код: `026dc4f8d99812ebbfc382292bbb3ed3efc58782`; оба GitHub CI runs этого commit завершились success.
- Заново собран `dist/staff` с `VITE_DATA_MODE=demo`, `VITE_APP_SURFACE=staff` и ссылкой на публичный сайт. CLI загрузил только изолированный статический staff-артефакт; backend, секреты и LikeC4 не публиковались. Git-привязка гостевого проекта не изменялась.
- Независимые HTTP-запросы к `/`, `/staff/login`, `/staff/bookings`, `/receipts/demo-check` возвращают 200 и опубликованный index с SHA-256 `aca93da81057c07e9c387b68b6d18949a50fd1433d1a7c548db63d03e3d95c0d`, совпадающим с локальной сборкой. Entry assets совпали побайтно. `/.env`, `/backend/.env`, `/architecture/system.c4` возвращают 404. Index гостевого сайта до/после публикации совпал.
- В браузере без Vercel-авторизации проверены вход через demo-account, новый план размещения, отсутствие пункта тарифов и перезагрузка прямой страницы календаря. Browser errors/warnings: пусто. Снимок: `output/staff-planner-vercel-live.png` (локальный, игнорируется Git).
- Это обновление демо-сайта с браузерным хранилищем. Общий облачный Django API, Supabase-миграции и банковская оплата этой публикацией не подключены. iPhone-приложения не пересобирались, не синхронизировались и не устанавливались.


## План размещения сотрудников — 4 ноября 2026

- `npm test`: **83 tests**, FSD **100 files / 243 imports**. `npm run build`, `npm run build:surfaces`, `npm run arch:check` pass. RU/KK/EN key/placeholder parity and literal references checked. Tariff editor removed from staff source/navigation; existing public tariff contract retained.
- `backend/.venv/bin/python backend/manage.py test booking commerce --noinput`: **135 tests**, real local PostgreSQL 17. New coverage: room-only seasonal price and payment/receipt, immutable snapshot, guest tariff requirement, notes scope/version/CSRF/redaction and atomic rollback. Existing payment/refund/concurrency/auth suites pass. Ruff check/format and migration drift pass.
- Migration **0009** applied to an isolated local `tynys_planner_qa` database and recreated in test DB; no Supabase/production migration. UI QA used fictional rooms/guests with actual local Django HTTP transport, not production data.
- Desktop 1280px and mobile 390×844: calendar/colors, empty-cell room/date preset, staff form without tariff, room-only booking for 26,000 KZT, internal note save/reload/history, simulator payment -> green confirmed card + receipt link; recorded checkout -> purple card. Mobile document width 390px (no page overflow); calendar/tabs scroll internally. RU/KK/EN visible labels checked. Browser error/warning log empty.
- Evidence (ignored local files): `output/staff-room-planner-desktop.png`, `output/staff-stay-card-mobile.png`. These show the local QA instance; no real payment, cloud/runtime capacity or native install is proved.
- Limits: window-scoped/paginated API and real-time refresh remain future work. Late walk-ins/deposits/room-date amendments/early-checkout interval release need their own services and decisions. No iPhone rebuild/sync/install; Android remains deferred.


## Автоматическое оформление после оплаты и комиссия — 27 октября 2026

Это обновление заменяет более ранний сценарий подтверждения управляющим. Новые заказы ожидают оплату; успешная демонстрационная оплата атомарно оформляет бронь, ручное подтверждение/отклонение отклоняется API. Неуспешная попытка не оформляет бронь. Удержание по умолчанию 30 минут (настраивается на сервере, ограничено временем заезда); истечение освобождает инвентарь. Для production требуется периодический запуск expire_payment_holds и обработка поздних событий реального банка.

- **131 backend-тест** прошёл на PostgreSQL; после финальных изменений дополнительно **16** проверок checkout/concurrent payment/Admin. Проверены идемпотентность и конкурентная оплата, атомарный rollback при ошибке аудита, истечение и повторная продажа, команды очистки, запрет ручного подтверждения, staff/guest scoping, диапазон/приватность/замораживание комиссии. Migration drift и Ruff check/format проходят. Миграция booking 0008 применена только локально.
- **77 frontend-тестов**, FSD 98 файлов / 238 импортов; public/staff builds, route boundaries, RU/KK/EN и LikeC4 проходят. Правила demo обновлены вместе с HTTP-контрактом. Устаревшие тесты ожидания управляющего заменены проверками платежного сценария; ограничения доступа/конкурентности сохранены.
- UI проверен при 1280×720 и 390×844. Администратор сохраняет тестовые 7,25% и видит значение после повторного открытия. Гостевой заказ на 10–13 ноября, номер 112, 72 000 ₸ сразу открывает демо-оплату; проверены отказ и последующий успех. Без действия управляющего статус стал «Оформлена», появилась квитанция. В staff видны та же запись и комиссия 5 220 ₸. Переполнения документа на узком экране не найдено. Снимок: `output/checkout-commission-desktop.png`.

Комиссия — только неизменяемый расчёт от суммы заказа. Ненастроенная ставка не подменяется нулём; банк, эквайринг, split, перечисления санаториям и распределение комиссии при возврате не подключены. Исходники интерфейса сотрудников общие для сайта и приложения; установленный iPhone оставлен без обновления. Существующие nullable hold-данные не освобождаются миграцией автоматически; стратегия переноса старых заказов остаётся решением перед реальным запуском.

Реальные Kaspi/Halyk, облачный Django/API/Supabase runtime, госинтеграции и миллионная нагрузка не проверялись. GitHub PR обновляется; это не production-деплой сайтов, backend или приложений. Требования и состояния — в [едином реестре](production-readiness.md).

## Сезонные цены, детские тарифы и эксплуатация — 27 октября 2026

- Backend: **124/124** теста `booking commerce` на настоящем PostgreSQL. Новые проверки: периоды цен и границы дат, запрет пересечений в PostgreSQL, права санатория, версии/атомарность изменений, неизменность snapshot/квитанции, возраст 0–2/3 и старые заявки без возраста, health/readiness. Ruff check/format и отсутствие migration drift подтверждены.
- Миграции booking 0006/0007 применены только локально. Сезонная цена выбирается для каждой ночи; скидка округляется отдельно для каждой ночи. Непостоянная цена возвращает `nightly: null` и `nightlyBreakdown`; перед API rollout требуется совместимость установленных клиентов, см. [api-contract.md](api-contract.md).
- Frontend: **74/74** теста, FSD — 98 файлов / 236 импортов. `npm run build`, `npm run build:surfaces`, `npm run arch:check` проходят; проверены границы web-сборок и паритет RU/KK/EN. Отдельная регрессия отклоняет некорректные возрасты без записи брони/аудита.
- Локальный demo UI проверен на 1280×720 и 390×844: сохранение/повторное открытие сезонного периода и флага тарифа; заявка на 31 октября — 2 ноября, два гостя, ребёнок 2 лет. При комнате 24 000 / 30 000 ₸ по сезонам и тарифе 4 500 ₸ сумма **63 000 ₸**, строки 28 500 + 34 500, статус `pending`. Горизонтального переполнения в проверенных формах нет, браузерный журнал ошибок/предупреждений пуст. Снимки: `output/pricing-period-desktop.png`, `output/pricing-breakdown-mobile.png`.
- `/health/live` проверяет процесс, `/health/ready` — простой запрос к БД с ограничением SQL-времени. Это не мониторинг всей системы, проверка S3/провайдеров или нагрузочная сертификация.
- [Единый реестр R01–R34](production-readiness.md) содержит состояния, внешние решения и критерии приёмки. [SRE-проект](sre.md) фиксирует предлагаемые SLO, ограничения, нагрузочные профили, восстановление и требования к эксплуатации. Миллионная нагрузка не измерялась и не заявляется как поддерживаемая.

В этой поставке облачный Django не размещался, Supabase не мигрировался, сайты не перепубликовывались. iOS не пересобирался/не синхронизировался/не переустанавливался; Android отложен. Государственные программы исследованы по официальным источникам, но проверка права, бюджетное финансирование, официальные документы/ЭЦП и интеграция с госпорталами ещё не реализованы. Реальные SMS/Kaspi и общий облачный API для всех клиентов остаются работами реестра.

## Установка на личный iPhone — 27 октября 2026, предыдущая поставка

После проверки симуляторов оба приложения были подписаны, установлены и запущены на iPhone 13 через режим разработчика. Это подтверждает dev-установку и запуск, но не облачную синхронизацию, оплату или полный набор native API-сценариев. Приложения остаются demo с отдельными хранилищами; App Store/TestFlight не публиковались. Следующий пакет обновления отложен по просьбе владельца.

## Историческая проверка двух приложений iOS в симуляторе — 27 октября 2026

- `Тыныс` (kz.tynys.booking) и `Тыныс Команда` (kz.tynys.staff) имеют отдельные Xcode projects, bundles, routes и sandbox. Оба собраны Xcode 26.6 для arm64/x86_64 Simulator (`BUILD SUCCEEDED`) и установлены/запущены в iPhone 17 / iOS 26.5. Это не подпись или установка на физический телефон.
- В симуляторе проверены гостевой каталог/профиль, открытие карты и выбор санатория, вход рабочего demo, обзор, меню управления и карточки номеров. Исправлены сдвиг плавающей кнопки при нажатии, safe-area карты/статусной строки; native scrolling включён. Native Share PDF, фото/видео picker, Keychain API-login и реальные HTTP-запросы к облаку ещё требуют end-to-end проверки с подключённым backend/устройством; успешная компиляция не заменяет её.
- `npm test`: **69** тестов + FSD; `npm run build`, `build:surfaces`, `build:apps`, `arch:check` проходят. Guest/staff page exclusion проверяется для обеих мобильных сборок. API-варианты также компилируются с примером HTTPS endpoint; запросы к этому примеру не выполнялись. `npm audit`: 0 vulnerabilities (включая dev). Transitive xcode/uuid закреплён на 11.1.1; обе pbxproj разбираются и Capacitor sync проходит.
- `backend/.venv/bin/python backend/manage.py test booking commerce --noinput`: **114** тестов на PostgreSQL, включая 7 новых staff-native сценариев: tenant scope, pending/confirmation, guest/staff/cookie isolation, replay и concurrent refresh, password/role/resort/deactivation invalidation, per-device logout/expiry. Ruff и migration drift проходят. Identity 0002 применена только к локальной БД; облачная Supabase-схема ею ещё не обновлялась.
- Browser UI: 1365×900 и 390×844, карта, RU/KK/EN. У guest artifact в DOM **0** ссылок `/staff`; на профиле нет категорий, нет горизонтального overflow. Сайт сохраняет свою навигацию, отдельные mobile tabs присутствуют только в приложениях.
- Локальные снимки: `output/ios-guest-catalogue.png`, `output/ios-guest-map.png`. Последующие native snapshots сохраняются в output; не публикуются вместе с сайтами.

По умолчанию обе iOS сборки — **demo**. Их данные и аккаунты не синхронизируются между приложениями/сайтами. Облачный Django/PostgreSQL/S3 runtime, реальные SMS/Kaspi, native guest registration/reset, удаление аккаунта, push/deep links и физическое устройство не проверены/не завершены. Android не создан. Подпись Apple ID и установка на личный iPhone — следующий отдельный шаг. Инструкции: [ios.md](ios.md). В этой итерации Vercel/App Store/TestFlight не публиковались.

## Историческая проверка файлов, мобильных сессий, Django Admin и Supabase — 23 октября 2026

Текущая реализация проверена локально с настоящим PostgreSQL 17. Отдельно через официальный коннектор Supabase создана и проверена облачная структура; это не подтверждение соединения запущенного Django с облаком.

- Backend: **107/107** (`backend/.venv/bin/python backend/manage.py test booking commerce --noinput`). Проверены изоляция mobile Bearer/cookie и staff, ротация/replay/revoke/reset, конкурентные сессии, частные файлы/аватары, владение медиа, лимиты/Range/очистка и read-only Django Admin. В дополнительном review исправлены обход проверки ссылок через encoded URL и HTTP 500 при слишком длинном Range; регрессии включены. Migration drift, Django check, Ruff check/format — pass.
- Первый чистый GitHub runner выявил отсутствие static manifest для Django Admin. В CI перед тестами добавлен `collectstatic --noinput`, как и в инструкции локального запуска; CSS не подменяются тестовыми заглушками.
- Frontend: **59/59**, FSD — 87 файлов / 214 импортов. `npm run build`, `npm run build:surfaces`, `npm run arch:check` — pass. Проверены обе границы сборок и паритет RU/KK/EN.
- Браузер: в demo и через локальный Django выполнены загрузка фото санатория с сохранением/повторным открытием, регистрация вымышленного гостя, загрузка/замена/удаление аватара и восстановление после reload. Ширины 390/1440px, без горизонтального переполнения и ошибок консоли в проверенных сценариях. Ключевые снимки: `output/playwright/api-avatar-mobile.png`, `output/playwright/media-avatar-desktop.png`, `output/playwright/media-avatar-mobile.png`.
- Django Admin `/django-admin/` отвечает отдельной формой входа. Superuser-only доступ, поиск/фильтры, счётчики, запреты записи/удаления и скрытие секретов проверены серверными тестами. Админка работает на локальном backend; в статические Vercel-сборки она не входит.
- Supabase `uchqzxxqioixhzbnwcak`: 25 таблиц в закрытой схеме `tynys`, 26 записей Django migrations, RLS на всех 25 таблицах, USAGE для `anon`/`authenticated` отсутствует. `btree_gist` и `no_overlapping_active_bookings` присутствуют. Аккаунты и брони в облако не переносились. Private bucket `tynys-private`: 40 MiB, JPEG/MP4/WebM, без клиентских политик.
- Облачный bootstrap получен из реальных миграций в одноразовой локальной базе; восстановление в другой базе, `migrate --check`, отсутствие новых миграций и защита от повторного применения проверены. SHA-256: `d09e525d407e569ad75ac5bec1fa03297a14a02363558122818024580bc1ba6a`. Источник: `scripts/export-django-schema.py`; SQL и manifest — `output/supabase-bootstrap-20261023.*`.
- Supabase advisors: нет ERROR/WARN; INFO `RLS enabled no policy` соответствует намеренному запрету клиентского доступа. INFO о неиспользованных индексах ожидаемо для пустой базы, индексы не удалялись. [RLS advisory](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy), [unused-index advisory](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).

Гостевой сайт и staff опубликованы отдельно из `dist/site` и `dist/staff`; Vercel сообщает READY. Прямые страницы возвращают HTTP 200 и тот же index.html, что проверенные локальные артефакты. Веб-публикации остаются demo с раздельным хранилищем origins. LikeC4, backend и секретные настройки не публиковались.

Остаётся: реальная runtime-проверка Django → Supabase PostgreSQL/S3 после заполнения секретов/CA, ограниченная серверная роль с RLS-политиками, cloud hosting и same-origin API proxy, реальные SMS/Kaspi, native-регистрация/reset и сами iOS/Android клиенты. Для масштаба ещё нужны пагинация/поиск больших реестров, нагрузочные замеры, фоновые задачи, проверки/транскодирование видео, backup/restore и эксплуатационный мониторинг. [Подключение Supabase](supabase.md), [критерии запуска](production-readiness.md). Это фундамент, а не завершение всей платформы.

## Историческая проверка аккаунтов, языков и отдельного кабинета — 23 октября 2026

Текущая проверка дополняет реализованные ранее бронирования, аналитику и квитанции. Услуги SMS и Kaspi не подключены; реальные персональные данные не использовались.

- `npm test`: **50/50**, FSD — 85 файлов / 210 импортов. Новые сценарии: телефонный формат, регистрация с переносом только своей анонимной истории, вход без объединения чужой истории, выход, сброс/отзыв сессий, OTP browser/purpose binding, TTL/попытки/повтор отправки, скрытые хеши вместо паролей. Все RU/KK/EN сообщения компилируются; ключи, named/list placeholders и статические обращения проверены.
- Django + реальный PostgreSQL: **76/76** (`manage.py test booking commerce`), включая запрет изменения подтверждённого телефона и сброс старых сессий. Drift check — без изменений, Django check — 0 замечаний, Ruff check/format — pass. Миграция 0004 применена локально.
- Combined build, `build:surfaces`, `check-surfaces.mjs`, API public build и LikeC4 — pass. Manifest подтверждает: public не содержит staff-страниц, staff не содержит гостевого каталога/регистрации; API build не содержит demo transport. Архитектура: 34 FSD-среза.
- В браузерах проверены регистрация → выход → вход → сброс → новый вход через настоящий локальный Django и отдельно browser-demo. Подтверждённый телефон read-only. Результат сброса переключается EN→KK без raw keys. API-профиль при 390px: axe 0, overflow 0. Первоначальный отказ CSRF на новом локальном порту исправлен добавлением точного dev-origin и полным перезапуском Django; production trusted-origins не ослаблялись.
- Каталог RU/KK/EN при 390/1440px: axe 0, overflow 0. До открытия карты ресурсов Leaflet/тайлов нет, после открытия загружаются; Escape возвращает фокус, поиск сохраняется. Zoom/reset перенесены так, чтобы выбранная карточка на мобильном экране их не перекрывала. Через EN UI создана pending-заявка.
- Staff: RU/KK/EN формы санатория/номера/тарифа/аккаунта, перевод статусов, CSV, гостевая история и аналитика. Сохранён скидочный тариф и подтверждена заявка. Отдельная production-сборка: `/` ведёт на вход, управляющий видит свой объект, `/staff/accounts` недоступен; ссылки на сайт внешние, квитанции остаются на staff-origin. 390/1440px без переполнения; чистая консоль в финальном standalone smoke.
- Дополнительная live-проверка выявила Leaflet `_leaflet_pos` при быстром закрытии карты во время CSS zoom. Старый код воспроизвёл 2 ошибки за 5 циклов. Отключена CSS zoom-анимация, начальный/reset fitBounds выполняется без анимации, callbacks защищены после teardown. Новый код: 20 open/zoom/Escape циклов без ошибок, оставшихся dialog/map containers и потери фокуса; `npm test` повторно 50/50. Это исправление поведения, а не подавление ошибки.
- Первый GitHub backend job не стартовал из-за кавычек Docker health-command. Исправлен синтаксис runner; frontend и backend jobs на следующем commit прошли в GitHub. Состояние конкретного последнего commit видно в PR checks.

Артефакты: `output/frontend-tests-final.log`, `output/build-surfaces-final.log`, `output/build-api-final.log`, `output/architecture-final.log`; `output/playwright/public-i18n/design-evidence.json` (ECC checker pass), скриншоты `auth-*-reset-kk-mobile.png`, `auth-api-profile-en-mobile.png`, `marketplace/standalone-staff-*.png` и `marketplace/i18n-staff-*`.

Ограничения: это не нагрузочная проверка и не полный аудит безопасности/доступности. Native-приложения, mobile-token auth, удаление аккаунта, реальные SMS/платежи, cloud API/БД и production media pipeline ещё не реализованы/размещены. Статические origins имеют раздельное demo-хранилище. Описания объектов остаются языком автора; серверный PDF пока русский (в UI есть пояснение), browser-demo PDF локализован. Для запуска см. [production-readiness.md](production-readiness.md).

## Историческое расширение платформы — 23 октября 2026

Проверена локальная интеграция Vue/FSD → Django 5.2.18 / DRF 3.18.3 → PostgreSQL 17. Платежи и квитанции остаются демонстрационными. Исторические разделы ниже описывают предыдущие состояния, а не текущий объём возможностей.

### Автоматические проверки

- `npm test`: 42 теста прошли; FSD — 73 JS/Vue-файла, 157 импортов. В том числе события/периоды аналитики и доступ по санаторию, CSV-инъекции, возвраты на точных границах 24/48 часов, дата квитанции около полуночи в часовом поясе санатория, замороженные условия/скидки, повтор оплаты, отзывы, профили, квитанции, заселение/выезд, multipart/CSRF и защищённое скачивание PDF.
- `npm run build`, отдельная `VITE_DATA_MODE=api npx vite build --outDir dist/api-check` и `npm run arch:check`: проходят. В API-сборке нет демо-транспорта и клиентского PDF-генератора; архитектура содержит 31 FSD-срез.
- `backend/.venv/bin/python backend/manage.py test booking commerce --noinput`: 65 тестов прошли на настоящем PostgreSQL. Покрыты tenant/owner isolation, транзакции и конкуренция, фото/видео, отзыв после проживания, метрики, профили, заселение/выезд, платежи/возвраты и защищённые неизменяемые квитанции. Неподдерживаемые методы action-endpoints возвращают 405, а не 500.
- `makemigrations --check --dry-run`: изменений нет. `manage.py check`: без замечаний. Ruff check и format: проходят. Миграции применены к локальной БД.
- `npm audit --omit=dev`: известных уязвимостей нет. Старое значение coverage ниже относится к предыдущей версии; новое покрытие не измерялось.

### Браузер: настоящий локальный API

Отдельные сессии гостя и управляющего. Все использованные контакты, отзывы, платежи и материалы — тестовые.

| Сценарий | Результат |
| --- | --- |
| Карта → профиль санатория → даты → страница номера → тариф | Пройден; даты выбираются внутри выбранного санатория |
| Тариф со скидкой 20%, 3 ночи, 2 гостя | 79 200 ₸; обычная цена 99 000 ₸ |
| Бронь → pending → подтверждение управляющим | Пройден; сайт не подтверждает автоматически |
| Неудачная демо-оплата → успешная повторная попытка | Пройден; статус оплаты отображается у гостя и сотрудника |
| Отмена более чем за 48 часов | Предпросмотр и фактический демо-возврат 100% — 79 200 ₸ |
| Изменение времени заезда санатория на 16:30 | Новая бронь использует 16:30; старая сохраняет прежние 14:00 |
| Загрузка фото и тестового WebM для номера | Пройден; видео воспроизводится на мобильной ширине |
| Завершённое проживание → отзыв с фото → ответ и одобрение управляющим | Пройден; опубликованный отзыв виден в профиле санатория |
| Профиль → история → демо-квитанция → PDF | Пройден; исходные 79 200 ₸ и отдельный возврат 100% видны после отмены |
| Аналитика управляющего | До сценария заселения: поступления 178 200 ₸, возвраты 79 200 ₸, остаток 99 000 ₸ и отзыв; значения совпали с тестовыми событиями |
| Оплаченная бронь на сегодня → заселение → выезд | Пройден на 24 000 ₸; фильтр «Проживают · оплачено», профиль гостя и квитанция проверены; после выезда строка перешла в «Выселены», история/оплата сохранены |

Локальные API-снимки и скачанный PDF: `output/playwright/marketplace/`. Визуально просмотрены страницы санатория, отзыва, возврата, аналитики, проживающих гостей и квитанции. Проверены десктоп 1440×900 и мобильный экран 390×844. Axe-core WCAG 2 A/AA, 2.1 AA, 2.2 AA: 0 найденных нарушений на проверенных страницах санатория, собственных броней и квитанции на мобильной ширине, аналитики на десктопе. Горизонтального переполнения документа не обнаружено; таблицы прокручиваются внутри контейнера. Это не полный аудит доступности.

### Браузер: статическое демо

Проверены выбор категории/номера/тарифа, pending → подтверждение → ошибка/успех оплаты → возврат, профиль и неизменность прошлой брони после изменения контактов, история сотрудника, PDF с кириллицей и тенге. Проверена загрузка, ошибка, пустой результат, частично доступная карта, отказ доступа, Escape и восстановление фокуса. Отдельные результаты и снимки: `output/playwright/public-expansion/design-evidence.json`.

Кнопка «Поделиться» при отсутствии поддержки Web Share скачивает PDF и объясняет дальнейшее действие. Этот fallback проверен с браузерной подменой наличия API; настоящий системный диалог отправки на физическом телефоне и доставка файла другому человеку не проверялись. Для мобильных и десктопных страниц квитанции и профиля сотрудника axe не нашёл нарушений. Визуальная регрессия без сохранённого baseline остаётся INCONCLUSIVE; полевые Core Web Vitals и нагрузка не измерялись.

### Публикация текущего демо

23 октября обновлён production-сайт https://vercel-site-puce-two.vercel.app/; Vercel deployment `dpl_GuCNPqBpDXXCPCmMbvja7LxngeZu` имеет статус READY. Загружены только файлы `dist/site` и конфигурация статических маршрутов (без backend, секретов и LikeC4). Прямые маршруты профиля, аналитики, комнаты и квитанции возвращают приложение; профиль открылся в браузере без Vercel-авторизации. `/architecture/system.c4` возвращает 404. После обновления вкладки проверен вход демо-управляющего и открытие аналитики на ширине 390 px без переполнения. SHA-256 опубликованного index.html совпал с локальным dist/site/index.html. Это публикация текущей локальной сборки, не подтверждение GitHub CI или публикации backend.

### Границы этого этапа

Backend/БД пока работают локально, не опубликованы в облаке. Реальный Kaspi API, чеки банка и реальные списания не подключены. Демо-квитанция явно помечена «Не чек Kaspi» и не является фискальным документом. Профиль гостя привязан к cookie браузера; регистрации, восстановления и межустройственного доступа пока нет.

Ручная неоплаченная бронь не может быть заселена, пока не реализован отдельный учёт ручной оплаты. Заселённую бронь отменять нельзя; досрочный выезд не сокращает занятый диапазон и не создаёт возврат. Автоистечения pending нет. Медиа хранятся локально; S3/CDN, суммарные квоты, антивирусная проверка и транскодирование видео ещё не реализованы. Docker runtime и удалённый CI в этой проверке не запускались. Аналитика показывает поступления и возвраты; расходы и прибыль не рассчитываются. Остальные направления развития отражены в `docs/product.md`.

## Историческая проверка Django / PostgreSQL — 22 октября 2026

Текущая локальная версия: Django 5.2.18, DRF 3.18.3, PostgreSQL 17; Vue в API-режиме. Публичная Vercel-версия остаётся демо.

- PostgreSQL: миграции применены; `btree_gist` и exclusion constraint созданы. Проверка отсутствующих миграций — без изменений.
- 20 backend-тестов прошли: пароль/выход, CSRF (включая гостя и login), роли и tenant scope, guest ownership, pending/confirmation/rejection/cancellation, версия записи, цены, ссылки из истории, CRUD, отключение аккаунта, rate limit, no-store и валидация.
- Конкурентный тест с двумя соединениями: один запрос 201, второй 409, одна бронь и одна запись истории. Прямая попытка вставить пересекающуюся бронь в БД также отклонена.
- Coverage backend/booking: 91% строк (без тестов и миграций), services 96%, serializers 97%, models 100%, views 88%. Команда seed_demo проверена отдельно вручную, в coverage её вызов не входит.
- Ruff: pass. `check --deploy` с DEBUG=False: без замечаний. Bandit: без найденных проблем. pip-audit: известных уязвимостей нет после обновления DRF.
- 17 frontend-тестов и FSD (40 файлов, 75 импортов): pass. Сборки demo и api проходят; в api-сборке нет demo-чанка. LikeC4 валиден. Добавлен backend CI job с PostgreSQL 17; удалённый запуск CI пока не выполнялся.

Браузер: локальный Vue API-режим + работающий Django + PostgreSQL. Отдельные сессии гостя и управляющего. Через карту выбраны Altyn Bulak, номер 111 и питание; заявка на 3 ночи для 2 гостей получила pending, стоимость 99 000 ₸. Управляющий вошёл по паролю, увидел только свой санаторий, подтвердил заявку; гость увидел confirmed в своих бронированиях. Десктоп 1440×900 и мобильный экран 390×844 визуально просмотрены. На мобильных экранах кабинета/собственных броней нет горизонтального переполнения и найденных axe нарушений WCAG 2 A/AA, 2.1 AA, 2.2 AA. Артефакты: output/backend-*.png. Это не полный аудит доступности или нагрузочное тестирование.

Ограничения: backend не опубликован в облаке, Docker image не проверен запуском (во время настройки Docker получил ошибку диска; для тестов использована отдельная локальная PostgreSQL 17). Нет оплаты, email/SMS, приглашений/восстановления пароля по email и личных клиентских аккаунтов. Гостевой доступ привязан к браузерной сессии. Pending-заявки освобождаются вручную; срока автоматического истечения нет. Перед публичным трафиком нужны hosting, HTTPS/proxy, резервные копии и защита от массовых гостевых заявок.

## Историческая проверка Vue-демо — 22 октября 2026

Текущая версия: Vue 3 / Pinia / FSD, общий демо-каталог гостевого сайта и кабинетов. Предыдущие проверки vanilla-прототипа не считаются проверкой этой миграции.

## Автоматические проверки

- `npm test`: 16 тестов прошли. Даты, цена, пересечения, роли и изоляция санаториев, публикация, версии записей, ссылки из истории, отмена, отключение/переназначение управляющего, миграция старых броней, ошибки localStorage и HTTP-адаптер.
- FSD: 40 JS/Vue-файлов и 71 локальный импорт; направления слоёв и публичные API срезов проверены.
- `npm run build` и `npm run arch:check`: успешно. Отдельная сборка `VITE_DATA_MODE=api` проходит и не содержит demo-чанка; реального API пока нет.

## Браузерные сценарии

Проверена production-сборка локально в Chrome на 1440×900, 768×1024, 390×844 и 375×812. Тестовые данные создавались только в локальном браузере.

| Сценарий | Результат |
|---|---|
| Администратор создаёт санаторий с меткой на карте | Пройден |
| Публикация без номера и тарифа | Отклонена с объяснением, форма сохраняет ввод |
| Добавить комнату и тариф → опубликовать | Пройден; санаторий появляется на гостевой карте |
| Создать управляющего → войти этим аккаунтом | Пройден; виден только назначенный санаторий |
| Ручная бронь, 18 000 + 4 500 × 2, на 3 ночи | 81 000 ₸ |
| Отмена ручной брони | Номер освобождён, запись осталась |
| Бронь через карту сайта | Появилась в кабинете управляющего |
| История действий | Отображает автора, время и «было / стало» |
| Управляющий открывает /staff/accounts напрямую | «Раздел недоступен» |
| Поиск без результатов | Пустое состояние и сброс фильтров |
| Отказ картографических тайлов | Предупреждение, каталог остаётся доступным |
| Загрузка рабочего пространства | Видимый статус, без ложного пустого результата |
| Мобильная ширина | Нет переполнения документа; таблицы прокручиваются внутри |
| Клавиатура | Tab переводит фокус на поля; native dialog удерживает фокус, Escape закрывает форму |

## ECC Browser QA

Использованы `frontend-design-direction` и `browser-qa`. Исправлены контраст подписей и фокусируемость прокручиваемых таблиц. Повторный axe-core по WCAG 2 A/AA, 2.1 AA, 2.2 AA: 0 найденных нарушений на семи разделах кабинета, гостевой странице, форме санатория и опубликованной странице входа. Это не полный аудит доступности: screen reader и физические мобильные устройства не проверялись.

Локальные артефакты: `output/playwright/workspace/`. Снимки визуально просмотрены. Автоматическая визуальная регрессия: **INCONCLUSIVE**, сохранённого baseline для новой Vue-версии нет. Полевые Core Web Vitals и INP не измерялись. Ошибки сети в локальном логе относятся к намеренно заблокированным OSM-тайлам; до этого в чистой сессии ошибок не было.

## Публикация

Vercel сообщает READY. Прямой адрес https://vercel-site-puce-two.vercel.app/staff/login открывается без Vercel-авторизации; ресурсы приложения возвращают HTTP 200. На опубликованной версии выполнены только проверки чтения. Мутации и входы ролей проверены на локальной production-сборке. LikeC4 в артефакт публикации не включён.

Ограничения: нет бэкенда, настоящей авторизации, общей базы между устройствами, реального наличия и платежей. Демо-роли и localStorage не обеспечивают безопасность. Серверные сессии, CSRF и транзакционная защита броней требуют интеграционных проверок после реализации API.

## 08.11.2026 — клиенты, сотрудники и обязательный аккаунт санатория

- Backend: **236 тестов** на отдельном PostgreSQL 17. Покрыты NOT NULL владельца, несколько санаториев одного manager, отзыв доступа после передачи, запрет назначения accountant, отсутствие утечки владельца в public catalog, аккаунт до создания объекта, admin-only directory, поиск/профиль без броней, CSRF/version и отзыв guest sessions. Первоначальный seed проверен с superuser, созданным со стандартной ролью manager. Старые manager-клиенты могут вернуть неизменённый accountId без смены владельца. Ruff и migration drift — pass.
- Frontend: **101 тест**, FSD **123 files / 313 imports**, `npm run build`, API `build:surfaces`, `arch:check` — pass. Добавлены проверки уникальных пунктов меню и гонок guest restore/login/logout, включая restore во время login и ошибку сети; RU/KK/EN parity сохранена.
- Supabase staging: migration `booking.0011_resort_account` применена. 6 существующих объектов сохранены; `account_id NOT NULL`, 0 санаториев без аккаунта. Старые manager assignments сохранены, остальные закреплены за существующим platform admin. `check --deploy`: 0 issues.
- Live API: admin видит клиентов, все санатории имеют аккаунт; manager workspace соответствует `resortIds` и owner, чужой directory403; accountant directory403, workspace/analytics200; guest directory401. Без создания настоящих клиентов или сообщений WhatsApp.
- Live browser (Chrome, 1440px/390px): admin clients search/profile/access controls, employee list, responsible-account selector, unique sidebar routes, public WhatsApp URL, guest login → profile → reload без предложения регистрации. JS page errors: 0; mobile document overflow: false. Fictional QA identities only. Evidence: `output/ownership-live-{clients-desktop,clients-mobile,accounts-desktop,owner-editor,profile-mobile}.png`.
- Only API/public/staff website artifacts published. LikeC4 and iPhone binaries are not deployed. SMS and real bank acceptance gates stay unchanged; this delivery does not claim production capacity or completion of the platform.

Final Vercel READY deployments: api `dpl_D3wdzXCCivx8P9opFkVuwfLiWQb5`, staff `dpl_7YCCnWXveNYpwHAgUkwTsLXsJY3z`, site `dpl_5ZyR5jy3CuXHhYhxA9oDvjsgzDki`. Public alias: https://vercel-site-puce-two.vercel.app; staff: https://tynys-staff.vercel.app; API: https://tynys-api.vercel.app. Final read-only browser smoke passed with zero page errors; no native sync/install.

## 08.11.2026 — публикация санаторного оформления

- Код: merge `4e7afc6`, сохранены изменения `af66ac4` и дизайн `58c08f7`. GitHub: `codex/platform-foundation`.
- 101 frontend test, FSD 123 files / 313 imports, build, API build:surfaces и arch:check — pass. Backend код в этой поставке не менялся; повторные backend-тесты не запускались.
- Public: `dpl_EaV2KQhuR7ZVB3ZyExCyDMp1QHer` — READY; https://vercel-site-puce-two.vercel.app.
- Staff: `dpl_9WAsXwqVu2NCRh7aqmMMxPYcXgof` — READY; https://tynys-staff.vercel.app.
- Независимый браузер: опубликованные JS entrypoints соответствуют локальным артефактам, SHA-256 логотипов совпадает. Проверены каталог/API, вход тестового admin, workspace, уникальная навигация с клиентами, бухгалтерия, карта/Escape/focus, guest login и profile reload. 1440×1000 и 390×844: без переполнения документа и JS page errors. Использованы только существующие вымышленные QA-аккаунты; деловые записи не изменялись.
- Артефакты проверки: `output/design-release/live.json` и PNG в той же папке. Существующий API https://tynys-api.vercel.app сохранён. LikeC4 и iPhone приложения не опубликованы; платёжные и SMS gates не менялись.

## 08.11.2026 — повторная публикация всех web-сервисов

По запросу владельца заново собраны и опубликованы public, staff и Django API из `62b58e85468c665ce072108ecaf125300275c515`. До публикации GitHub API подтвердил этот же commit в `main` и рабочей ветке. Новый дизайн и управление аккаунтами сохранены.

- api: `dpl_2emcAfHZSefnzWNSJgMuSjLyfEQz` — READY, https://tynys-api.vercel.app.
- staff: `dpl_y2rSqT5WzHf3PbMeWm92121fbF3j` — READY, https://tynys-staff.vercel.app.
- site: `dpl_FSG8RsExrZYrpYatk4sqP4nWTZpi` — READY, https://vercel-site-puce-two.vercel.app.

Проверки: 101 frontend test, 236 backend tests на PostgreSQL 17, FSD 123/313, build, API build:surfaces, LikeC4 validate. Migration drift отсутствует, Supabase migrations применены, check --deploy без замечаний. `/health/live`, `/health/ready`, Django Admin login возвращают HTTP 200. Публичные JS-файлы сверены по SHA-256 с выбранными артефактами, адреса соответствуют свежей сборке. Admin/manager/accountant read-scope повторно проверен без изменения деловых данных.

Browser smoke: каталог, карта/клавиатура, staff login, план размещения, уникальная навигация и бухгалтерия проверены на 1440px/390px; скриншоты в `output/republish-20261108`. Полный smoke затем остановился на navigation timeout /profile; повторный запуск — на HTTP timeout главной страницы. Независимые curl/urllib проверки тех же адресов вернули 200 и совпадающие файлы. Эти тайм-ауты не считаются пройденным полным browser smoke.

LikeC4 не опубликован; native iPhone/Android сборки не обновлены. Платёжные и SMS gates, данные и секреты окружения не изменены.

Отдельная финальная browser-проверка гостя прошла: redirect на вход, вход существующего QA-аккаунта, профиль и reload на 390px, zero page errors. Для диагностического повтора Chromium запущен с отключёнными HTTP/2 и QUIC; этот результат отделён от двух предыдущих тайм-аутов. Evidence: `output/republish-20261108/profile-mobile.png`, `/tmp/republish-profile-check.log`.
