# Halyk ePay: состояние sandbox и запуск

## Что опубликовано

- Клиентский сайт: https://vercel-site-puce-two.vercel.app
- Кабинет сотрудников: https://tynys-staff.vercel.app/staff/login
- Общий Django API: https://tynys-api.vercel.app/api/v1
- Техническая консоль: https://tynys-api.vercel.app/django-admin/
- Liveness/readiness: `/health/live`, `/health/ready`.

Это тестовое окружение с вымышленным каталогом. iPhone-приложения не пересобирались и по-прежнему используют прежнюю конфигурацию. Production readiness и список решений владельца: [production-readiness.md](production-readiness.md).

## Ограничение банка — Gate A открыт не полностью

Проверка общих официальных credentials 05.11.2026:

| Операция | Наблюдаемый результат |
| --- | --- |
| OAuth client_credentials | 200; токен не сохраняется в логах |
| OAuth password из примера | 401; выбран работающий client_credentials для lookup/deactivate |
| Создать invoice с вымышленными недоставляемыми контактами | 400/code1079 SMS error, но invoice создаётся и находится ACTIVE |
| Пустой lookup | TotalCount=0, Records=null |
| Непустой lookup | account_id пустой; transaction accountID содержит отправленную opaque-привязку |
| Открыть hosted payment page | Работает |
| Оплатить официальными тестовыми Visa/Mastercard | Отказ 455 / 3DSecure |
| Официальная тестовая AMEX | Отказ 3340 |
| Независимый transaction lookup | resultCode=101, statusName=REJECT |
| Деактивация | PUT 200, независимый lookup ANNULLED |

**Успешный CHARGE, доставка callback и реальный sandbox refund ещё не подтверждены.** Поэтому `HALYK_EPAY_PROTOCOL_VERIFIED=False`, публичная банковская оплата сообщает недоступность, `PAYMENTS_ALLOW_SIMULATOR=False`. Автоматическое подтверждение проверено тестами с контролируемыми банковскими ответами, но не выдаётся за успешную банковскую операцию.

Для завершения Gate A нужен совместимый тестовый invoice terminal/настройка 3DS со стороны Halyk или исправление общего стенда. После этого: успешный CHARGE → одна confirmed-бронь → повтор callback no-op → отмена → independently verified refund; отдельно timeout/поздняя оплата/deactivation. Только после этих доказательств включить gate. Реальный эквайринг не включать: provider конфигурация намеренно принимает только sandbox.

Официальные источники: [тестовые данные](https://epayment.kz/docs/Test-credentials), [invoice API](https://epayment.kz/docs/invoice-link-API), [статусы](https://epayment.kz/docs/check-status-payment), [возвраты](https://epayment.kz/docs/vozvrat-chastichnyi-vozvrat).

## Границы и контракт

[payments.openapi.yaml](contracts/payments.openapi.yaml) — схема. [fixtures](contracts/fixtures/halyk-sandbox.json) — обезличенные формы ответов. Создание принимает bookingId/requestKey/locale, сумму и контакты клиента не принимает. Shared sandbox получает только вымышленные контакты сервера. Один PaymentAttempt на бронь, уникальный ограниченный invoice pool, frozen KZT amount и actor binding. Неизвестный исход POST восстанавливается lookup; новая ссылка не создаётся вслепую.

Callback — только сигнал durable job, GET — только локальное чтение. PaymentEvent с CHARGE применяется один раз под тем же resort lock, что бронь/expiry/cancellation. Поздние, повторные и несовпадающие списания сохраняются без подтверждения в reconciliation. RefundRequest сохраняет намерение атомарно с отменой; успешный HTTP POST не равен возврату. Исторический Kaspi-themed demo и PDF не переименовываются в Halyk; официальный receiptUrl пока null. Финансовая аналитика выбирает demo или sandbox, не смешивает суммы.

## Cloud configuration

Django credentials только в закрытом `backend/.env.stage` и Vercel server Environment Variables. Отдельный логин/схема `tynys_stage`, старый `tynys` сохранён. Supabase transaction pooler, TLS verify-full с публичным CA `backend/certs/supabase-ca.crt`, DB_CONN_MAX_AGE=0, prepared statements/server-side cursors выключены. Схема не выдаётся anon/authenticated; RLS включён, Django владеет своими таблицами. При будущих миграциях проверить grants/RLS новых таблиц.

Private bucket `tynys-private`, S3 key `tynys-django-vercel-sandbox`; secret только на сервере. Запись/чтение/удаление собственного тестового JPEG проверены. На Vercel текущие uploads ограничены 4 MB (`MEDIA_UPLOAD_MAX_BYTES`, `VITE_UPLOAD_MAX_BYTES`); лимит function body 4.5 MB не позволяет заявлять работу больших видео. Следующий шаг — авторизованный direct upload/finalization либо отдельный media backend. [Ограничение Vercel](https://vercel.com/docs/functions/limitations#request-body-size).

pg_cron `tynys-stage-payments-tick` каждую минуту вызывает `/internal/payments/tick` через pg_net. Bearer secret читается из Vault, не записан literal в cron SQL. Endpoint без секрета 401; gate=false всё равно освобождает expired holds. Bounded worker: до 5 jobs / 45 секунд между заданиями, lease120с, durable retry/dead-letter. Это не доказательство SRE/миллионной нагрузки. Нужны alerts, reconciliation ownership, резервирование/restore и нагрузочные проверки.

`DEBUG=False`, demo OTP выключен. Пока нет SMS-провайдера, регистрация и сброс по SMS недоступны. Анонимная браузерная бронь сохраняется в серверной сессии. Два начальных staff аккаунта и случайные пароли находятся только в игнорируемом локальном `backend/.env.stage.accounts`; не вставлять их в README, git или сообщения. Manager ограничен Altun; superuser открывает readonly Django Admin.

## Проверки и эксплуатация

- Backend: `DATABASE_URL=<isolated PostgreSQL URL> backend/.venv/bin/python backend/manage.py test booking commerce --noinput`; не направлять test runner на Supabase staging/production.
- `backend/.venv/bin/ruff check backend`; `manage.py makemigrations --check --dry-run` с локальным PostgreSQL.
- `npm test`, `npm run build`, API `npm run build:surfaces`, `npm run arch:check`.
- Локальный worker: `manage.py reconcile_payments --limit 20`; gate должен быть проверен. `expire_payment_holds` работает независимо от банка.
- Деплой: backend allowlist artifact отдельно, public только dist/site, staff только dist/staff. Перед публикацией API-сборки задать VITE_DATA_MODE=api, VITE_API_BASE=/api, VITE_UPLOAD_MAX_BYTES=4000000 и адреса сайтов. Native/LikeC4 не публиковать.
- Не запускать migrate в Vercel build. Миграции заранее отдельным операторским шагом с проверкой target и backup; текущая staging schema создана пустой и заполнена только вымышленными данными.
- Не сбрасывать InvoicePool и не удалять финансовые события. При gate/worker сбое закрыть новые checkout, сохранить verification/deactivation существующих попыток и разобрать dead jobs. Учесть: текущий общий gate останавливает все bank jobs; аварийное отключение только новых checkout — отдельная операционная доработка до production.

Для Vercel CLI запускать deploy **из каталога выбранного артефакта** с `--local-config vercel.json`; одного --cwd недостаточно для воспроизводимости наблюдавшейся конфигурации. Frontend routes содержат API proxy, backend routes — нет, иначе получится цикл. API project functionDefaultRegions=icn1 проверен по live X-Vercel-Id.
