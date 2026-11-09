# Два приложения iOS — Capacitor

В репозитории два самостоятельных приложения на Capacitor 8 / Vue 3. Они устанавливаются рядом, имеют отдельные sandbox, Keychain и наборы маршрутов. Внутри находятся собранные HTML/CSS/JS; Vercel-сайт не открывается вместо приложения. Android пока не добавлен.

| | Гость | Сотрудник |
| --- | --- | --- |
| Название | Тыныс | Тыныс Команда |
| Bundle ID (предварительный) | kz.tynys.booking | kz.tynys.staff |
| Xcode project | ios/App/App.xcodeproj | ios-staff/App/App.xcodeproj |
| Vite mode / artifact | mobile / dist/mobile | mobile-staff / dist/mobile-staff |
| Навигация | Каталог, бронирования, профиль; карта плавающей кнопкой | Обзор, брони, аналитика, управление |
| Авторизация API | GuestAccount, /mobile-auth | User, /staff-mobile-auth |

Клиентское приложение не содержит страниц и входа сотрудников, даже скрытого пункта в DOM. Сотрудник не переключается на гостевые страницы: рабочие разделы открываются через «Управление». Таблицы рабочего приложения превращаются в карточки на узком экране. Сайт использует общие формы/сущности, но сохраняет собственную навигацию. Проверка `build:apps` запрещает страницы другой аудитории в каждой сборке.

## Запуск

Нужны Node 22+, Xcode 26+ и установленный runtime iOS Simulator. Swift Package Manager; CocoaPods не нужен. Минимальная версия этих приложений — iOS 16 (WebKit/Safari 16 build target); зависимости Capacitor поддерживают iOS 15+.

```sh
npm ci
npm run ios:sync
npm run ios:open
# Или выбрать симулятор командой npm run ios:run

npm run ios:staff:sync
npm run ios:staff:open
# Или npm run ios:staff:run
```

В Xcode выбрать схему App, симулятор iPhone и Run. Обе версии синхронизируются в разные каталоги. После изменения Vue-кода обязательно повторять `ios:sync` для соответствующего приложения; Xcode сам не запускает Vite.

```sh
npm test
npm run build:apps
npm run ios:check
npm run ios:staff:check
```

Последние две команды собирают unsigned simulator builds, **не** IPA для физического iPhone. Артефакты находятся в `output/ios-build` и `output/ios-staff-build`. Swift bridge и privacy manifest общие: `native/ios/`. Иконки/заставки производятся непосредственно из `public/assets/logo.svg` (AppKit SVG rendering; светлая guest и тёмная staff палитра) командой `swift scripts/render-ios-icons.swift`.

## API-сборка для установки и локальное demo

Для установки текущей версии используются отдельные release-команды:

```sh
npm run ios:release:sync
npm run ios:staff:release:sync
```

`scripts/build-mobile.mjs` собирает каждую аудиторию с общим `https://tynys-api.vercel.app/api/v1`, native Bearer/Keychain transport и ограничением загрузки 4 000 000 байт для Vercel. Проверяются build metadata, наличие native transport, отсутствие demo transport и страниц другой аудитории. Эти команды не зависят от сохранённого в shell demo-режима. `npm run build:apps:release` выполняет те же проверки без sync. Ни production-ключи, ни пароли в bundle не включаются.

Обычные `ios:sync`/`ios:staff:sync` и `build:apps` остаются локальными сборками с demo по умолчанию. Их отдельные sandbox не синхронизируются. Установка 27 октября была demo; источник данных новой установки нужно проверять отдельно по release metadata и фактическому запросу приложения.

Для разработки против другого API можно явно задать размещённый HTTPS Django:

```sh
VITE_DATA_MODE=api VITE_API_BASE=https://api.your-domain.kz/api/v1 npm run ios:sync
VITE_DATA_MODE=api VITE_API_BASE=https://api.your-domain.kz/api/v1 npm run ios:staff:sync
```

Это пример адреса для локальной разработки. Для текущей установки использовать release-команды выше. Валидатор не разрешает HTTP, credentials в URL, query/hash или другую API-версию. Supabase остаётся БД/хранилищем **за Django**; S3/DB/service keys никогда не попадают в мобильный bundle. `CapacitorHttp` обслуживает сетевые JSON/multipart запросы через native networking; браузерная API-сборка приложения намеренно не работает без native bridge.

Гостевой вход требует уже существующий аккаунт. Нативный transport регистрации/сброса с SMS пока не сделан: API-приложение явно объясняет это на соответствующих экранах; demo-регистрация/сброс остаются доступны с demo-кодами. Аккаунты сотрудников создаёт администратор, самостоятельной регистрации сотрудников нет.

## Сессии и файлы

- Keychain хранит access/refresh атомарной записью, только на текущем устройстве, при разблокированном экране. Service namespace зависит от bundle ID; общий Keychain access group не включён. В браузерном storage нет production-токенов.
- Транспорт разделяет audience и API origin, сериализует ротацию refresh, помечает незавершённую ротацию до отправки одноразового токена. При потере ответа требуется новый вход — consumed refresh не повторяется. Запросы мутаций при сетевой ошибке автоматически не повторяются.
- Выход удаляет локальные credentials даже без сети. Если серверный отзыв не подтверждён, интерфейс сообщает об этом; это не утверждение, что удалённая сессия отозвана.
- Авторизованные аватары/рабочие медиа загружаются через API в временные blob URL. Они освобождаются при смене аккаунта. Большие видео пока загружаются целиком, фоновой очереди/транскодирования нет.
- Фото/видео выбираются системным выбором файлов. Квитанция PDF сохраняется во временный cache и открывает системное меню «Поделиться»/«Сохранить в Файлы». После закрытия меню файл удаляется, оставшиеся временные PDF очищаются при старте. Настоящие чеки Kaspi ещё не интегрированы.
- Native bridge logs отключены (`loggingBehavior: none`), чтобы payload с credentials не попадал в Xcode/системные логи. Нет ATS-исключений, remote `server.url` или wildcard navigation.
- Оба `SceneDelegate` создают `TynysViewController`, который регистрирует `TynysKeychain`. Одной настройки storyboard недостаточно: programmatic scene entry point может её обойти. Нельзя заменять root controller на обычный `CAPBridgeViewController`; API-каталог и защищённая навигация зависят от доступа к vault.
- Safe area, поля 16px, зоны нажатия 44px, нижняя навигация и RU/KK/EN учтены. Карта и актуальные API-данные требуют сети; offline-бронь не обещается.

## Установка на личный iPhone

Для каждого проекта выбрать Apple Development Team в Signing & Capabilities и уникальный bundle ID при необходимости, подключить iPhone к Mac, доверить компьютер, включить Developer Mode и выбрать телефон в Xcode. Затем Run. Пароль Apple ID, код телефона и доверие профилю пользователь вводит на своих устройствах. Установка на симулятор не доказывает установку/подпись/доступ к сети на настоящем iPhone — это отдельная проверка.

Оба приложения можно установить рядом. Публикация в App Store/TestFlight в эту работу не входит. До неё нужны размещённый API, реальные SMS/Kaspi, native registration/recovery, удаление гостевого аккаунта, политика приватности/актуальные App Privacy сведения, поддержка, подпись Apple Developer и проверки на физических устройствах. Push и universal/deep links пока не реализованы. Требования Capacitor: https://capacitorjs.com/docs/ios ; конфигурация: https://capacitorjs.com/docs/config .
