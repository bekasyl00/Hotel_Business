# Онлайн-наблюдение Tynys

Артефакты для Grafana Cloud или собственного Grafana/Prometheus. Наличие файлов не означает подключённый сбор метрик или доставку уведомлений. Актуальное доказательство публикации — в `docs/verification.md`.

## Подключение без отдельного сервера Prometheus

В Grafana Cloud доступна интеграция **Metrics Endpoint**: облачный сборщик опрашивает защищённый HTTPS endpoint, поэтому постоянно включённый компьютер/сервер Alloy не нужен. Для текущего serverless API экспортируются агрегаты из общей PostgreSQL. Счётчики процесса Django нельзя выдавать за общий трафик: следующий запрос может попасть на другой экземпляр Vercel.

1. В серверной конфигурации Django/Vercel задаётся отдельный случайный `METRICS_BEARER_TOKEN` длиной не менее 32 символов. Он не является ключом БД, платежей или аккаунта. Хранить только в серверных секретах и защищённой настройке Grafana; не вставлять в Git, JSON dashboard или URL. Перепубликовать API после изменения переменной окружения.
2. В Grafana Cloud: **Connections → Add new connection → Metrics Endpoint**. Создать scrape job `tynys-api` для `https://tynys-api.vercel.app/internal/metrics`, аутентификация **Bearer**, токен из серверной конфигурации. Интервал **60 секунд**, HTTPS verification включён. Не опрашивать через клиентский `/api` proxy и не открывать endpoint без авторизации.
3. Нажать **Test Connection**, сохранить и дождаться нескольких сборов. В Explore проверить `up{scrape_job="tynys-api"}`, затем `tynys_metrics_snapshot_timestamp_seconds{scrape_job="tynys-api"}`. Grafana Metrics Endpoint назначает `job` с внутренним namespace, а выбранное имя сохраняет в `scrape_job`. Dashboard и правила фильтруют **`scrape_job="tynys-api"`**, не внутренний `job`. Если имя отличается, одинаково изменить его в настройке dashboard и правилах. Успешный тест соединения ещё не доказывает постоянный сбор.
4. В **Dashboards → New → Import** загрузить `grafana-dashboard.json`, выбрать созданный Prometheus/Grafana Cloud Metrics data source. Стабильный UID: `tynys-operations`. Платежные панели по умолчанию показывают production; можно выбрать sandbox или All. Heartbeat, holds и БД общие для развёртывания.

Ошибки endpoint: 404 — метрики выключены/токен не задан; 401 — неправильная авторизация; 503 — нет достоверного снимка БД. При этих ошибках нельзя заменять значения нулями. Нормальный ноль означает успешно прочитанную пустую очередь, а **No data** — отсутствие наблюдения. Проверяйте свежесть снимка вместе с остальными показателями.

## Алерты

`prometheus-alerts.yaml` — переносимые Prometheus alerting rules, а не Grafana provisioning JSON. В Grafana **Alerting → Alert rules → Import → Prometheus YAML file** загрузить этот файл, выбрать тот же data source и папку Tynys. Сначала проверить выражения в Explore и результаты preview, затем включить оценку с интервалом 60 секунд. Это Grafana-managed rules; dashboard сам алерты не создаёт.

Первый набор состоит из **шести** проверок: недоступность/отсутствие scrape, потеря свежего снимка, отсутствие успеха обязательного `payment_scheduler`, задержанные/мёртвые задания и незавершённая сверка реальных денег. Успешный ручной `payment_worker` не заменяет плановый запуск. Остальные показатели остаются на dashboard без отдельного шумного алерта до накопления наблюдений. В каждой проверке указаны `severity=page|ticket`, `owner=platform-admin` и ссылка на [конкретные действия администратора](../../docs/runbooks/operations.md). Пороговые значения и выдержка объяснены там; это начальные настройки пилота, а не подтверждённые SLO.

Для переноса в собственный Prometheus указать файл в `rule_files` и сохранить совместимую метку `scrape_job` у target:

```yaml
scrape_configs:
  - job_name: tynys-api
    scheme: https
    metrics_path: /internal/metrics
    scrape_interval: 60s
    authorization:
      type: Bearer
      credentials_file: /run/secrets/tynys_metrics_token
    static_configs:
      - targets: [tynys-api.vercel.app]
        labels:
          scrape_job: tynys-api
```

Файл токена предоставляет оператор закрытым способом. Перед перезагрузкой выполнить `promtool check rules ops/monitoring/prometheus-alerts.yaml`. YAML можно импортировать через официальный Grafana conversion API, но секреты доступа не должны попадать в командную строку, логи или репозиторий. Не выполнять массовый `sync` чужих правил.

После импорта настроить контакт и notification policy для `service=tynys-api`, сгруппировать по `alertname`, `provider`, `environment`. `page` направлять на оперативный контакт администратора, `ticket` — в выбранный канал задач; если он ещё не настроен, не считать такую маршрутизацию работающей. Отдельно включить сообщения о восстановлении. Сохранить семантику официального импорта Prometheus: пустой результат условного выражения означает отсутствие нарушения и Normal. Не переводить все такие результаты в NoData-аларм. Потерю самого сбора и снимка явно проверяют правила с `absent(...)`; ошибки выполнения запроса должны оставаться видимыми как ошибки, а не Normal. Отправить тест только на согласованный контакт и проверить фактическое получение; наличие правила не доказывает доставку. Для аварий мониторинга нужен внешний контроль: если сама Grafana недоступна, её собственный dashboard этого не исправит.

При импорте 09.11.2026 Grafana автоматически поставила **Normal** и для пустого результата, и для ошибки вычисления. После импорта у каждого из шести правил необходимо отдельно выбрать **Configure no data and error handling → Alert state if execution error or timeout → Error** и сохранить; пустой результат оставить **Normal**. На текущем развёртывании это выполнено для всех шести правил. Preview routing должен показывать согласованный email-контакт. Сейчас `page` и `ticket` оба направлены на email администратора; отдельной системы задач/эскалации нет.

## Что измеряется и что пока нет

- Очередь — постоянные записи PaymentJob и lease в PostgreSQL; значения являются gauges. `rate()` к ним применять нельзя.
- Возраст платежа/возврата — возраст нерешённой записи, не время банковской обработки. Webhook count отражает принятые дедуплицированные события за час, не доступность XPayment.
- Число подключений PostgreSQL включает служебные подключения; `max_connections` не равен лимиту клиентов Supavisor. Lock waits — количество ожидающих сессий в момент сбора, не p95 ожидания.
- Никакие ИИН, телефоны, booking IDs, суммы платежей, секреты или тексты ошибок не входят в labels.
- HTTP p95/5xx, frontend performance, DB CPU/IO, сохранность backup, DNS и независимые пользовательские проверки требуют других источников. Request logs уже дают обезличенные route/status/duration/request_id, но dashboard не изображает их метриками без отдельного надёжного конвейера логов.
- Сбор раз в минуту добавляет примерно 43 200 HTTP обращений за 30 дней и соответствующую нагрузку БД/потребление функций. Бесплатный план не означает неограниченный ресурс: проверять Billing/Usage Grafana, Vercel и Supabase; не включать платный upgrade автоматически.

Официальные инструкции: [Metrics Endpoint](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/integrations/metrics-endpoint-reference-setups/), [настройка Bearer scrape](https://grafana.com/docs/grafana-cloud/send-data/metrics/metrics-prometheus/prometheus-config-examples/integration-guide/), [импорт dashboard](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/import-dashboards/), [импорт Prometheus YAML в Grafana Alerting](https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/alerting/alerting-rules/alerting-migration/), [Prometheus alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).
