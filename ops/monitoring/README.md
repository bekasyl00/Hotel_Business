# Онлайн-наблюдение Tynys

Артефакты для Grafana Cloud или собственного Grafana/Prometheus. Наличие файлов не означает подключённый сбор метрик или доставку уведомлений. Актуальное доказательство публикации — в `docs/verification.md`.

## Подключение без отдельного сервера Prometheus

В Grafana Cloud доступна интеграция **Metrics Endpoint**: облачный сборщик опрашивает защищённый HTTPS endpoint, поэтому постоянно включённый компьютер/сервер Alloy не нужен. Для текущего serverless API экспортируются агрегаты из общей PostgreSQL. Счётчики процесса Django нельзя выдавать за общий трафик: следующий запрос может попасть на другой экземпляр Vercel.

1. В серверной конфигурации Django/Vercel задаётся отдельный случайный `METRICS_BEARER_TOKEN` длиной не менее 32 символов. Он не является ключом БД, платежей или аккаунта. Хранить только в серверных секретах и защищённой настройке Grafana; не вставлять в Git, JSON dashboard или URL. Перепубликовать API после изменения переменной окружения.
2. В Grafana Cloud: **Connections → Add new connection → Metrics Endpoint**. Создать scrape job `tynys-api` для `https://tynys-api.vercel.app/internal/metrics`, аутентификация **Bearer**, токен из серверной конфигурации. Интервал **60 секунд**, HTTPS verification включён. Не опрашивать через клиентский `/api` proxy и не открывать endpoint без авторизации.
3. Нажать **Test Connection**, сохранить и дождаться нескольких сборов. В Explore проверить `up{job="tynys-api"}`, затем `tynys_metrics_snapshot_timestamp_seconds{job="tynys-api"}`. Метка `job` должна быть именно `tynys-api`; если интеграция назначила другое значение, изменить её конфигурацию или одинаково заменить job в dashboard и правилах. Успешный тест соединения ещё не доказывает постоянный сбор.
4. В **Dashboards → New → Import** загрузить `grafana-dashboard.json`, выбрать созданный Prometheus/Grafana Cloud Metrics data source. Стабильный UID: `tynys-operations`. Платежные панели по умолчанию показывают production; можно выбрать sandbox или All. Heartbeat, holds и БД общие для развёртывания.

Ошибки endpoint: 404 — метрики выключены/токен не задан; 401 — неправильная авторизация; 503 — нет достоверного снимка БД. При этих ошибках нельзя заменять значения нулями. Нормальный ноль означает успешно прочитанную пустую очередь, а **No data** — отсутствие наблюдения. Проверяйте свежесть снимка вместе с остальными показателями.

## Алерты

`prometheus-alerts.yaml` — переносимые Prometheus alerting rules, а не Grafana provisioning JSON. В Grafana **Alerting → Alert rules → Import → Prometheus YAML file** загрузить этот файл, выбрать тот же data source и папку Tynys. Сначала проверить выражения в Explore и результаты preview, затем включить оценку с интервалом 60 секунд. Это Grafana-managed rules; dashboard сам алерты не создаёт.

Проверки покрывают недоступность/отсутствие scrape, потерю свежего снимка, обязательный `payment_scheduler` heartbeat, задержанные/мёртвые задания, неверные lease, зависшую очистку удержаний, незавершённую сверку денег, длительные возвраты и давление на БД. Успешный ручной `payment_worker` не заменяет heartbeat планового запуска. Пороговые значения — начальные эксплуатационные настройки, а не подтверждённые SLO.

Для переноса в собственный Prometheus указать файл в `rule_files` и проверить `promtool check rules ops/monitoring/prometheus-alerts.yaml` перед перезагрузкой. YAML можно импортировать через официальный Grafana conversion API, но секреты доступа не должны попадать в командную строку, логи или репозиторий. Не выполнять массовый `sync` чужих правил.

После импорта настроить контакт и notification policy для `service=tynys-api`, сгруппировать по `alertname`, `provider`, `environment`. Отдельно включить сообщения о восстановлении. При Grafana query error/no data оставить сигнал об ошибке, не переводить в Normal. Отправить тест только на согласованный контакт и проверить фактическое получение; наличие правила не доказывает доставку. Для аварий мониторинга нужен внешний контроль: если сама Grafana недоступна, её собственный dashboard этого не исправит.

## Что измеряется и что пока нет

- Очередь — постоянные записи PaymentJob и lease в PostgreSQL; значения являются gauges. `rate()` к ним применять нельзя.
- Возраст платежа/возврата — возраст нерешённой записи, не время банковской обработки. Webhook count отражает принятые дедуплицированные события за час, не доступность XPayment.
- Число подключений PostgreSQL включает служебные подключения; `max_connections` не равен лимиту клиентов Supavisor. Lock waits — количество ожидающих сессий в момент сбора, не p95 ожидания.
- Никакие ИИН, телефоны, booking IDs, суммы платежей, секреты или тексты ошибок не входят в labels.
- HTTP p95/5xx, frontend performance, DB CPU/IO, сохранность backup, DNS и независимые пользовательские проверки требуют других источников. Request logs уже дают обезличенные route/status/duration/request_id, но dashboard не изображает их метриками без отдельного надёжного конвейера логов.
- Сбор раз в минуту добавляет примерно 43 200 HTTP обращений за 30 дней и соответствующую нагрузку БД/потребление функций. Бесплатный план не означает неограниченный ресурс: проверять Billing/Usage Grafana, Vercel и Supabase; не включать платный upgrade автоматически.

Официальные инструкции: [Metrics Endpoint](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/integrations/metrics-endpoint-reference-setups/), [настройка Bearer scrape](https://grafana.com/docs/grafana-cloud/send-data/metrics/metrics-prometheus/prometheus-config-examples/integration-guide/), [импорт dashboard](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/import-dashboards/), [импорт Prometheus YAML в Grafana Alerting](https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/alerting/alerting-rules/alerting-migration/), [Prometheus alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).
