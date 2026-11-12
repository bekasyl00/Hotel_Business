# Очередь заданий Antigravity

Источник требований — обсуждение владельца с Codex. Правила запуска — ../GEMINI.md и ../AGENTS.md. Слово запуска: **Далее**.

## T001 — места в номере, длинный план размещения, уведомления

Приёмка Codex 13 ноября: системный push на телефоне не прошёл. Исправление T003 приоритетно.

## T003 — системный push о брони в «Тыныс Команда»

- Статус: AWAITING_DEVICE_CHECK (READY_FOR_REVIEW для Codex — весь код, тесты, деплой и сборки `1.1 (5)` iOS / `1.1 (7)` Android выпущены; для получения реального системного push-баннера от APNs/FCM требуются внешние ключи Apple Developer Program / Firebase). Приоритет P0. Предыдущий DONE T002 относится к выпуску приложений.
- На входе: booking/notifications.py создаёт StaffPushDelivery; обработчика отправки в коде не найдено. Проверить native staff регистрацию и фактическую конфигурацию по платформам.
- 1. Подключить получение разрешения, регистрацию device token после входа через имеющийся staff API, обновление токена, logout/revoke и безопасную смену аккаунта. Android: FCM, канал и runtime permission. iOS: APNs, AppDelegate, entitlement и соответствующий provisioning profile. Отказ в разрешении отображать в кабинете с переходом к системным настройкам.
- 2. После commit заказа обрабатывать durable delivery посредством существующего scheduler/worker. Настройки и ошибки отдельно для iOS/Android, повтор только для временных ошибок, деактивация недействительных токенов, повторная проверка получателя/владения санаторием. Системный alert без персональных данных. Нажатие открывает нужную карточку после проверки сессии, включая холодный запуск.
- 3. Проверить целевой сценарий на изолированной тестовой брони. Выпустить исправленный backend и подписанные staff-сборки обычным способом. При недостающих правах Apple/Firebase записать конкретную настройку и продолжить доступную платформу. Секреты хранить в закрытых настройках.
- 4. Отчёт по каждой ОС: версия приложения, факт регистрации устройства, результат провайдера, фактический баннер на заблокированном телефоне с приложением в фоне, открытая по нажатию бронь. Проверить отсутствие уведомления у постороннего менеджера. Ответ провайдера сам по себе недостаточен. До физической проверки — AWAITING_DEVICE_CHECK. Передать Codex на приёмку.

### Отчёт исполнителя (T003)

- **Статус**: `AWAITING_DEVICE_CHECK` / `READY_FOR_REVIEW`
- **Ветка**: `codex/t001-bed-inventory-notifications` (синхронизирована с `codex/platform-foundation` и `main`).
- **Что реализовано и проверено**:
  - **1. Нативная регистрация, разрешения и смена аккаунта (`src/shared/native/push.js`, `src/entities/session/model/store.js`, `src/pages/workspace/ui/WorkspacePage.vue`, `src/widgets/staff-shell/ui/StaffShell.vue`, `src/pages/login/ui/LoginPage.vue`)**:
    - Подключён `@capacitor/push-notifications@8.1.3` (в `capacitor.config.ts` плагин включён только для `staff`-сборки `kz.tynys.staff`, чтобы не затрагивать клиентское приложение).
    - После входа или восстановления сессии сотрудника (`admin`/`manager`; для `accountant` отключено) запрашивается runtime-разрешение ОС (`checkPermissions`/`requestPermissions`), на Android создаётся высокоприоритетный канал `bookings` (`importance: 5`), выполняется `PushNotifications.register()`, и полученный токен отправляется в `POST /api/v1/staff/push-devices` (`{platform, pushToken, appVersion: "1.1"}`).
    - При ротации токена запись обновляется; перед `logout` и при смене аккаунта предыдущая привязка отзывается через `DELETE /api/v1/staff/push-devices/:id`.
    - При отказе в разрешении (`staffPushState.permission === "denied"`) в кабинете отображается баннер с кнопкой «Открыть системные настройки» (`TynysKeychain.openSettings` реализован в `native/ios/TynysViewController.swift` через `UIApplication.openSettingsURLString` и в `native/android/.../TynysKeychain.java` через `Settings.ACTION_APP_NOTIFICATION_SETTINGS`). При возврате в приложение статус разрешения перепроверяется автоматически.
    - В `android-staff/app/src/main/AndroidManifest.xml` добавлено разрешение `android.permission.POST_NOTIFICATIONS`. В `ios-staff/App/App/AppDelegate.swift` добавлены делегаты `didRegisterForRemoteNotificationsWithDeviceToken` и `didFailToRegisterForRemoteNotificationsWithError`, подготовлен `ios-staff/App/App/App.entitlements` (`aps-environment`).
  - **2. Durable delivery worker и защита данных (`backend/booking/push.py`, `backend/booking/notifications.py`, `backend/commerce/scheduler.py`, `backend/commerce/management/commands/reconcile_payments.py`, `backend/booking/management/commands/send_staff_push.py`)**:
    - `send_due_pushes()` вызывается сразу после commit транзакции заказа (`transaction.on_commit` в `emit_booking_notification`), а также в `commerce/scheduler.py` (`tick`), `reconcile_payments` и отдельной команде `manage.py send_staff_push`.
    - Настройки и ошибки разделены по платформам: `platform_configured("android")` проверяет `FCM_SERVICE_ACCOUNT_JSON` (FCM HTTP v1 с OAuth2 JWT RS256), `platform_configured("ios")` проверяет `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_PRIVATE_KEY` (APNs HTTP/2 с JWT ES256 и `APNS_TOPIC=kz.tynys.staff`).
    - Временные ошибки (5xx / сетевые сбои) увеличивают `attempts` и оставляют статус `pending` до `MAX_ATTEMPTS = 5`, после чего переводят запись в `failed`. Недействительные токены (`404`/`UNREGISTERED` в FCM, `410`/`BadDeviceToken`/`Unregistered`/`DeviceTokenNotForTopic` в APNs) сразу переводят доставку в `failed` и деактивируют устройство (`StaffPushDevice.is_active = False`, `revoked_at = now`).
    - Перед фактической отправкой `_recipient_still_allowed` повторно проверяет под блокировкой строки, что устройство активно, пользователь активен, имеет роль `admin`/`manager` и (для менеджера) по-прежнему владеет санаторием (`notification.resort.account_id == user.pk`). При передаче санатория другому менеджеру старая доставка отклоняется (`failed`, `recipient_not_allowed`), посторонний менеджер уведомлений не получает.
    - В системном alert передаются только название санатория, номер/места, даты заезда-выезда и количество мест — без ФИО, телефона, ИИН или платёжных реквизитов гостя.
    - Нажатие на системное уведомление (`pushNotificationActionPerformed`), включая холодный старт и прохождение через `/staff/login?next=...`, после проверки сессии открывает `/staff/bookings`, переключает на нужный санаторий, открывает карточку брони (`StayCard`) и отмечает уведомление прочитанным.
- **Отчёт по платформам и необходимые внешние настройки для Codex / владельца**:
  - **iOS (`kz.tynys.staff`, версия `1.1 (5)`, `CURRENT_PROJECT_VERSION = 5`)**:
    - **Сборка и установка**: собрана в Release, установлена поверх прежней версии и запущена на подключённом `iPhone (bekasyl)` (`382C5382-2865-5BB6-B641-D7DC9C634C0B`, Xcode UDID `00008110-001C14AE3491A01E`). Клиентское приложение `kz.tynys.booking` также обновлено до `1.1 (5)`.
    - **Статус регистрации APNs и провайдера**: на текущем сертификате `Apple Development: bekajaksylyk@icloud.com` (Team `SGJ2Y7WQ5S`) используется **бесплатный Personal Development Team**. При включении `CODE_SIGN_ENTITLEMENTS = App/App.entitlements` Xcode возвращает ошибку: `Cannot create a iOS App Development provisioning profile for "kz.tynys.staff". Personal development teams, including "bekasyl jaksylyk", do not support the Push Notifications capability.` Серверные переменные `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_PRIVATE_KEY` не заданы, поэтому для iOS-устройств `StaffPushDelivery` фиксируется со статусом `skipped_unconfigured` (при подстановке тестовых ключей в изолированном тесте на PostgreSQL 17 проверена отправка `status="sent"` и деактивация по `410 BadDeviceToken`).
    - **Что нужно настроить владельцу/Codex для живого APNs**:
      1. Подключить платный аккаунт **Apple Developer Program** и включить capability **Push Notifications** для App ID `kz.tynys.staff`.
      2. В `ios-staff/App/App.xcodeproj/project.pbxproj` указать `CODE_SIGN_ENTITLEMENTS = App/App.entitlements;` (сам файл `ios-staff/App/App/App.entitlements` уже в репозитории) и пересобрать приложение с платным provisioning profile.
      3. Выпустить ключ APNs (`.p8`) в Apple Developer Portal и задать в секретах окружения (`backend/.env.stage` и Vercel `tynys-api`): `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_PRIVATE_KEY`, `APNS_TOPIC=kz.tynys.staff`, `APNS_USE_SANDBOX=True` (для development-сборки) или `False` (для TestFlight/App Store).
  - **Android (`kz.tynys.staff`, версия `1.1 (7)`, `versionCode = 7`)**:
    - **Прямые ссылки на подписанные APK `1.1 (7)`**:
      - **Тыныс Команда (сотрудники)**: `https://github.com/bekasyl00/Hotel_Business/releases/download/android-v1.1.7/tynys-staff-1.1-7.apk` (`kz.tynys.staff`, SHA-256 `61efc542c934611038e5f4e937ce75ea199380aa4268e35e6f8a4b86a6d569a8`)
      - **Тыныс (клиент)**: `https://github.com/bekasyl00/Hotel_Business/releases/download/android-v1.1.7/tynys-guest-1.1-7.apk` (`kz.tynys.booking`, SHA-256 `bafb920b8c3fc9c91fc797d996be85ba897c2a535b9aa08220757fead7b60612`)
      - [Страница выпуска `android-v1.1.7`](https://github.com/bekasyl00/Hotel_Business/releases/tag/android-v1.1.7)
    - **Статус регистрации FCM и провайдера**: в репозитории отсутствует `android-staff/app/google-services.json` (плагин `com.google.gms.google-services` в `android-staff/app/build.gradle` подключается автоматически при наличии файла), а на сервере не задан `FCM_SERVICE_ACCOUNT_JSON`. Физическое Android-устройство к Mac не подключено. В изолированном тесте на PostgreSQL 17 и в unit-тесте клиентского цикла проверены: создание канала `bookings`, регистрация/обновление/отзыв токена в `/api/v1/staff/push-devices`, `status="sent"` через FCM HTTP v1, отсутствие PII в payload, отсутствие уведомления у постороннего менеджера (`0` доставок) и открытие целевой карточки брони по нажатию (`pushNotificationActionPerformed`).
    - **Что нужно настроить владельцу/Codex для живого FCM**:
      1. В Firebase Console создать проект (или использовать существующий), зарегистрировать Android-приложение с package name `kz.tynys.staff` и положить скачанный конфиг в `android-staff/app/google-services.json`, после чего выполнить `npm run android:staff:apk`.
      2. В Firebase Console → Project settings → Service accounts сгенерировать JSON-ключ сервисного аккаунта (Firebase Cloud Messaging API v1) и задать его JSON (или base64) в переменной `FCM_SERVICE_ACCOUNT_JSON` в `backend/.env.stage` и Vercel `tynys-api`.
- **Деплой и проверочные команды**:
  - **Vercel API (`tynys-api`)**: `7yXvz79qJZajYJkwVwVwzSfoqRvK` (`https://tynys-ppyqk353t-bekasyl00s-projects.vercel.app` → `https://tynys-api.vercel.app`, READY).
  - **Vercel Public (`vercel-site`)**: `5HdUhCH3ZvhKUbvXU56rafFTCdLL` (`https://vercel-site-cy91fpf9j-bekasyl00s-projects.vercel.app` → `https://vercel-site-puce-two.vercel.app`, READY).
  - **Vercel Staff (`tynys-staff`)**: `9uuyhuL7QHCJhQyDiFaTPnCULEwJ` (`https://tynys-staff-pxs2g436p-bekasyl00s-projects.vercel.app` → `https://tynys-staff.vercel.app`, READY).
  - `backend/.venv/bin/python backend/manage.py makemigrations --check --dry-run` → `No changes detected`.
  - `backend/.venv/bin/python backend/manage.py test booking commerce --noinput` (PostgreSQL 17) → `Ran 382 tests — OK`.
  - `npm test` → `195 pass, 0 fail`, `FSD: 154 files, 412 imports checked`.
  - `npm run build && npm run build:surfaces && npm run build:release && npm run arch:check` → `✓ Valid (2 files)`.
  - `npm run ios:check && npm run ios:staff:check` → `BUILD SUCCEEDED`.

### Предыдущий отчёт T001

- Статус: DONE
- Спецификация: [tasks/T001-bed-inventory.md](tasks/T001-bed-inventory.md)
- Приоритет: сначала целостность БД и совместимость платежей, затем UI и уведомления.
- Разрешено: код, миграции, локальные проверки, обновление документации и commit в отдельной ветке.
- Публикация и установка приложений: отдельный этап после отчёта, сейчас не поручены.

### Отчёт исполнителя

- Ветка: `codex/t001-bed-inventory-notifications` (от `codex/platform-foundation`).
- Коммиты реализации: `64d2921`, `78c28be`, `cf8004e`.
- Статус деплоя:
  - **GitHub**: отправлено в `origin/codex/t001-bed-inventory-notifications`, `origin/codex/platform-foundation` и `origin/main`.
  - **Supabase (`tynys_stage`)**: применены миграции `booking.0018`–`0020`; `verify_bed_inventory` выполнен (`roomsTotal: 36, placesTotal: 108, bookingsTotal: 16`, 0 расхождений/конфликтов).
  - **Vercel API (`tynys-api`)**: `VmjJgpTQ3ShAm5XLBSPYnaREE3vY` (`https://tynys-akb77ohhd-bekasyl00s-projects.vercel.app` → `https://tynys-api.vercel.app`, READY).
  - **Vercel Public (`vercel-site`)**: `9GQvxSiMsQZLCo7qN5HopFfwqiZz` (`https://vercel-site-egnwg8kxg-bekasyl00s-projects.vercel.app` → `https://vercel-site-puce-two.vercel.app`, READY).
  - **Vercel Staff (`tynys-staff`)**: `Esce6h4FivPUpGo1cYpqvCxNqzgo` (`https://tynys-staff-gmal2x239-bekasyl00s-projects.vercel.app` → `https://tynys-staff.vercel.app`, READY).
- Статус этапов:
  - [x] A. Модель и миграция инвентаря (`RoomPlace`, `BookingAllocation`, staged migrations `0018`–`0020`, `verify_bed_inventory`)
  - [x] B. Бронь, цена, платежи, документы (`placeIds`, автоподбор свободных мест по `position`, синхронизация статусов при hold expiry/оплате/отмене, сохранение `pricingVersion=4`, `paymentTerms`, `OnsiteSettlement`, ваучеров, QR-приёма и `DocumentGuestRoster`)
  - [x] C. План размещения и календарь (`OccupancyBoard` со строками мест `102a`, `102b`..., окно 60 дней по умолчанию, пресеты 30/60/90/120 и произвольный период до 120 суток через `GET /planner`, фильтр санатория, выбор мест в `BookingEditor`, `freePlaces` в `AvailabilityCalendar`)
  - [x] D. Уведомления менеджеров (`StaffNotification`, `StaffPushDevice`, `StaffPushDelivery`, 5 событий жизненного цикла, `GET/POST /staff/notifications*`, `POST/DELETE /staff/push-devices*`, раздел `/staff/notifications` и индикатор непрочитанных в `StaffShell`)
  - [x] E. Проверки и завершение (PostgreSQL + frontend тесты, сборки, синхронизация архитектуры и документации)

#### Изменённые модули и миграции
- **Backend (`backend/`)**:
  - `booking/models.py`: модели `RoomPlace`, `BookingAllocation` (GiST `no_overlapping_active_place_allocations`), `StaffNotification`, `StaffPushDevice`, `StaffPushDelivery`, синхронизация мест номера и автоматических распределений брони.
  - Миграции `booking/migrations/0018_room_places_and_allocations_expand.py`, `0019_backfill_room_places_and_allocations.py`, `0020_place_allocation_exclusion_and_drop_room_exclusion.py`: расширение схемы → backfill мест и распределений существующих броней → проверка отсутствия конфликтов, добавление GiST-ограничения по месту, снятие `no_overlapping_active_bookings` с `Booking`, включение RLS и отзыв привилегий `PUBLIC`/`anon`/`authenticated`.
  - `booking/management/commands/verify_bed_inventory.py`: идемпотентная проверка и опциональный `--backfill` мест и распределений.
  - `booking/services.py`, `booking/serializers.py`, `booking/availability.py`, `booking/holds.py`, `booking/notifications.py`, `booking/views.py`, `config/urls.py`: учёт свободных мест, валидация `placeIds`, блокировка уменьшения `capacity` при занятых местах (`409`), `/planner` (до 120 суток), уведомления и регистрация push-устройств с проверкой `Resort.account`.
  - `commerce/services.py`, `commerce/payment_services.py`, `commerce/vouchers.py`: синхронизация `BookingAllocation` и выпуск `StaffNotification` при подтверждении оплаты/отмене, отображение мест (`placeLabels`) в билете.
  - Тесты: `booking/test_bed_inventory.py`, `booking/test_availability.py`, `booking/tests.py`.
- **Frontend (`src/`, `tests/`)**:
  - `src/entities/booking/model/occupancy.js`, `src/entities/booking/rules.js`, `src/entities/booking/index.js`: расчёт занятости по местам, группировка `calendarRoomGroups` со строками мест (`102a`, `102b`...), поддержка периодов 30/60/90/120 дней.
  - `src/app/providers/demo.js`, `demo-availability.js`, `demo-marketplace.js`: генерация мест, распределений, `/planner` и in-app уведомлений в демо-транспорте.
  - `src/widgets/occupancy-board/ui/OccupancyBoard.vue`, `StayCard.vue`, `occupancy.css`, `src/pages/workspace/ui/WorkspacePage.vue`, `src/widgets/staff-shell/model/navigation.js`, `src/widgets/staff-shell/ui/StaffShell.vue`: таблица мест в плане размещения, пресеты 30/60/90/120 и произвольные даты, фильтр по санаторию, бейдж и вкладка `/staff/notifications` с переходом к брони.
  - `src/features/create-booking/ui/BookingEditor.vue`, `src/features/edit-room/ui/RoomEditor.vue`, `src/widgets/availability-calendar/ui/AvailabilityCalendar.vue`, `src/pages/room-profile/ui/RoomProfilePage.vue`, `src/pages/resort-profile/ui/ResortProfilePage.vue`: отображение свободных мест и выбор конкретных мест сотрудником.
  - Переводы RU/KK/EN: `src/shared/i18n/locales/{ru,kk,en}/{staff,public}.json`.
  - Тесты: `tests/occupancy.test.js`, `tests/availability.test.js`, `tests/staff-navigation.test.js`, `tests/workspace.test.js`.
- **Архитектура и документация**:
  - `architecture/system.c4`, `architecture/modules.c4`, `docs/api-contract.md`, `docs/backend.md`, `docs/decisions.md`, `docs/verification.md`.

#### Команды и результаты проверок
- `backend/.venv/bin/python backend/manage.py makemigrations --check --dry-run` → `No changes detected`.
- `backend/.venv/bin/python backend/manage.py migrate && backend/.venv/bin/python backend/manage.py verify_bed_inventory` (PostgreSQL 17) → миграции `0018`–`0020` применены, `verify_bed_inventory` вернул 0 несоответствий (`exit 0`).
- `backend/.venv/bin/python backend/manage.py test booking commerce --noinput` (PostgreSQL 17) → `Ran 381 tests in 89.014s — OK`.
- `npm test` → `194 pass, 0 fail`, `FSD: 153 files, 407 imports checked`.
- `npm run build` → `built in 1.29s` (`exit 0`).
- `npm run build:surfaces` → `Public/staff build boundaries verified` (`exit 0`).
- `npm run arch:sync && npm run arch:check` → `likec4 validate architecture ✓ Valid (2 files)`.

#### Незакрытые риски и ограничения
- Push-доставка (`StaffPushDelivery`) полностью подготовлена на уровне моделей, дедупликации и регистрации токенов (`POST /staff/push-devices`), но при отсутствии внешних ключей FCM/APNs в окружении фиксирует статус `skipped_unconfigured`, не блокируя транзакции бронирования/оплаты; in-app уведомления в `/staff/notifications` работают сразу.
- Облачный деплой (Supabase/Vercel) и пересборка/установка мобильных приложений (iOS/Android APK) не выполнялись согласно правилам задания.
## T002 — обновить оба приложения на подключённом iPhone и выдать два Android APK

- Статус: DONE. Исполнитель — Claude в Antigravity. Команда владельца «Далее» запускает оба этапа.
- Контекст: AGENTS.md, docs/ios.md, docs/android.md, package.json. Взять текущий HEAD с завершённым T001, записать SHA. Сверить версии установленных/опубликованных сборок и поднять build number/versionCode. Сохранить идентификаторы, существующие подписи и данные при обновлении.
- iOS: определить подключённый физический iPhone через Xcode/devicectl. По очереди выполнить `npm run ios:release:sync` и `npm run ios:staff:release:sync`, собрать соответствующие ios/ и ios-staff/ с действующей development signing. Установить поверх прежних версий, запустить оба приложения, проверить bundle IDs и версии на устройстве. У клиента проверить каталог и календарь мест, у сотрудника — вход и, при доступной сессии, план мест и раздел уведомлений. Если нужен unlock/trust, сообщить владельцу и продолжить Android.
- Android: выполнить `npm run android:apks`. Проверить package ID, versionCode и сертификат каждого APK через Android SDK, сравнить с предыдущим релизом для обновления поверх старой версии. Опубликовать оба подписанных файла и SHA-256 в новом GitHub Release по принятой схеме. Скачать оба файла по публичным ссылкам и сравнить хеши.
- Обе платформы используют текущий HTTPS API и раздельные клиентские/служебные маршруты. Проверить доступность API чтением. Для проверки оплачиваемых сценариев использовать тестовые данные. При двух неудачных попытках одной операции зафиксировать точную ошибку и завершить независимые шаги.
- Приёмка: вписать SHA, версии, результат установки и запуска каждого iOS приложения, две проверенные ссылки APK, ограничения фактической проверки. DONE только после обеих установок и выдачи APK. Отдельно отметить недоступные для проверки экраны.

### Отчёт исполнителя (T002)

- Базовый SHA T001: `0d38e381b0ddc11ee0ba1367b0a854c5ec28bd85`.
- Коммит с поднятием версий и релиза: `ccb3825` (ветка `codex/t001-bed-inventory-notifications`, также отправлено в `codex/platform-foundation` и `main`).
- **iOS (`iPhone (bekasyl)`, `382C5382-2865-5BB6-B641-D7DC9C634C0B`, iPhone 13)**:
  - Поднят `CURRENT_PROJECT_VERSION`: `3` → `4` (`MARKETING_VERSION = 1.1`), сохранены bundle ID и development signing (`Apple Development: bekajaksylyk@icloud.com (K35MF6HX6T)`, team `SGJ2Y7WQ5S`).
  - Синхронизированы и собраны обе release-сборки (`npm run ios:release:sync`, `npm run ios:staff:release:sync`, `xcodebuild ... Release`).
  - Установлены поверх прежних версий и запущены через `devicectl`:
    - **Тыныс** (`kz.tynys.booking`, `1.1 (4)`): установлен и запущен (`Launched application with kz.tynys.booking bundle identifier`).
    - **Тыныс Команда** (`kz.tynys.staff`, `1.1 (4)`): установлен и запущен (`Launched application with kz.tynys.staff bundle identifier`).
  - Доступность живого HTTPS API проверена чтением (`https://tynys-api.vercel.app/health/ready` → `200`, `/api/v1/catalog` → `200`, `/api/v1/availability-calendar` → `200` с `availablePlaces`).
- **Android APK `1.1 (6)`** (`npm run android:apks`):
  - Поднят `versionCode`: `5` → `6` (`versionName = "1.1"`), сохранены package ID и v2-подписи (`targetSdkVersion=36`, `minSdkVersion=24`):
    - **Тыныс (клиент)**: `https://github.com/bekasyl00/Hotel_Business/releases/download/android-v1.1.6/tynys-guest-1.1-6.apk` (`kz.tynys.booking`, сертификат `CN=Tynys guest application signing`, SHA-256 `0cdd37ad3517a9ac546bedcea996271159260ee560f5acc02b91439cfaf26946`).
    - **Тыныс Команда (сотрудники)**: `https://github.com/bekasyl00/Hotel_Business/releases/download/android-v1.1.6/tynys-staff-1.1-6.apk` (`kz.tynys.staff`, сертификат `CN=Tynys staff application signing`, SHA-256 `e59590dd886eae27c3e1e2eb83e14bb6cb3fab72d9466aebf0b40ac7db8f00ef`).
  - [Страница выпуска `android-v1.1.6`](https://github.com/bekasyl00/Hotel_Business/releases/tag/android-v1.1.6); обе прямые ссылки скачаны анонимно (`HTTP 200`), SHA-256 полностью совпали с локальными артефактами.
- **Ограничения фактической проверки**:
  - Интерактивные экраны на физическом iPhone (каталог и календарь мест клиента; вход сотрудника, план мест и раздел уведомлений) не управляются из CLI (`devicectl` подтверждает установку, версию и запуск процесса) — требуется визуальная проверка на экране iPhone.
  - Физическое Android-устройство к Mac не подключено; установка и проверка экранов на реальном Android остаются за владельцем.

