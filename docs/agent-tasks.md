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
