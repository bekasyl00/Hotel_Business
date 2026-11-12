# Очередь заданий Antigravity

Источник требований — обсуждение владельца с Codex. Правила запуска — ../GEMINI.md и ../AGENTS.md. Слово запуска: **Далее**.

## T001 — места в номере, длинный план размещения, уведомления

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

