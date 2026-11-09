# Tynys — Google Play preparation

Checked against official documentation on 2026-11-10. This is a draft; no account registration, submission, payment or publication has occurred.

## Owner registration

1. Open https://play.google.com/console/signup with the Google account that will own the apps.
2. Choose the account type based on the real operator. Google recommends Organization for commercial/business activity, and requires it for health/medical or government apps. Do not classify a booking marketplace as a government/medical service merely because it lists sanatoriums.
3. Owner reviews/accepts the Developer Distribution Agreement and pays the one-time US$25 registration fee. These are owner actions, not automated submission steps.
4. Complete Google identity/contact verification. Personal: legal name/address, contact and public developer email. Organization: verified organization name/address, D-U-N-S, website, organization phone and contacts. D-U-N-S application is free; no fictitious company details.
5. For a newly created personal account, verify access to a real Android device using the Play Console app. An emulator does not replace this verification. Each app needs a closed test with at least 12 opted-in testers continuously for 14 days before applying for production access. Google reviews that application; passing 14 days is not instant publication. Internal testing can begin earlier.

Sources:
- https://support.google.com/googleplay/android-developer/answer/6112435?hl=en
- https://support.google.com/googleplay/android-developer/answer/13634885?hl=en
- https://support.google.com/googleplay/android-developer/answer/13628312?hl=en
- https://support.google.com/googleplay/android-developer/answer/14316361?hl=en
- https://support.google.com/googleplay/android-developer/answer/14151465?hl=en

## Proposed store metadata — verify against final Android UI

### Guest

Package proposal: kz.tynys.booking. Free download. Category proposal: Travel & Local. Adults booking travel for themselves/family; final target audience/content-rating declarations are owner decisions, not guessed values.

| Locale | Name | Short description |
| --- | --- | --- |
| ru-RU | Тыныс | Санатории Казахстана: выбор размещения, бронирования и билеты. |
| kk | Тыныс | Қазақстан шипажайлары: демалысты таңдау, броньдау және билеттер. |
| en-US | Tynys | Find sanatorium stays in Kazakhstan and manage your bookings. |

Russian full-description draft:

Тыныс помогает выбрать размещение в санаториях Казахстана и следить за своими бронированиями.

• Каталог и карта санаториев.
• Фотографии, описания и календарь доступности размещения.
• Стоимость выбранных дат и сумма оплаты при бронировании.
• История бронирований и билет для предъявления в санатории.
• Профиль гостя и контактные данные.

Для управления бронированиями нужен аккаунт Тыныс. Доступность объектов, цены и способы оплаты зависят от выбранного санатория. Приложение не подтверждает государственные льготы и не заменяет медицинскую консультацию.

Do not promise native registration/reset until those routes work. Do not advertise verified official subsidies, medical treatment advice, universal payment acceptance or government affiliation.

### Staff

Package proposal: kz.tynys.staff. Free download. Category proposal: Business. Account provided by platform administrator; no public self-registration promised.

| Locale | Name | Short description |
| --- | --- | --- |
| ru-RU | Тыныс Команда | Бронирования, план размещения и работа команды санатория. |
| kk | Тыныс Команда | Шипажай тобына арналған броньдар мен орналастыру жоспары. |
| en-US | Tynys Team | Manage sanatorium bookings, arrivals and your team's workspace. |

Russian full-description draft:

Тыныс Команда — рабочее приложение для сотрудников санаториев, подключённых к платформе Тыныс.

• Просмотр бронирований и плана размещения.
• Сведения о гостях и прибытии в рамках назначенных прав доступа.
• Проверка билета гостя по QR-коду и оформление приёма.
• Работа с размещением, ценами и профилем организации.
• Аналитика и бухгалтерские разделы для соответствующих ролей.

Доступ предоставляет администратор платформы. Набор разделов зависит от роли сотрудника и назначенных санаториев. Отметка сотрудника о получении оплаты на месте не является банковской или фискальной квитанцией.

### Metadata still needed from owner

- Actual legal operator/developer name and verified support email.
- Privacy contact, approved retention/deletion policy and public privacy URL.
- Target countries and final audience/content-rating answers.
- App access instructions and dedicated reusable reviewer accounts using fictional data. Never expose platform-admin production credentials or unrelated live guests.
- Screenshots captured from final Android builds and approved brand assets. Do not reuse screenshots that promise absent features.

## Technical release gates

- Target API 36 or newer (effective 31 Aug 2026); Capacitor8 documents minSdk24, compile/target36 and Android Studio Otter2025.2.1+.
- Two isolated package IDs, routes and Android Keystore-backed token stores. Current repository only implements TynysKeychain for iOS; Android bridge must be added, with no plaintext fallback.
- Signed release AAB and Play App Signing; protect and back up upload keystore outside Git. Verify final AAB/manifest before upload.
- Validate 16KB native-library compatibility; Java/Kotlin-only apps without bundled .so files already support it, but verify actual APK/AAB and emulator runtime.
- Runtime camera permission only for scanning; system media/file picker for occasional uploads. Do not request broad READ_MEDIA_IMAGES/VIDEO, contacts or SMS permissions for these workflows.
- Test API login/refresh/logout, restart, back navigation, deep links to Kaspi, uploads, PDF sharing and tenant boundaries. Emulator checks are not physical-payment or camera acceptance.

Sources:
- https://support.google.com/googleplay/android-developer/answer/11926878?hl=en
- https://capacitorjs.com/docs/updating/8-0
- https://developer.android.com/studio/publish/app-signing
- https://developer.android.com/guide/practices/page-sizes
- https://support.google.com/googleplay/android-developer/answer/15800983?hl=en

## Publication blockers in current source

1. No privacy-policy route/link found; Data safety must describe actual user data and SDK/backend handling. Public active non-PDF privacy URL plus in-app access is required. Do not declare that the app collects no data.
2. No account-deletion request pathway found. If signup is in app or the app directs to web signup, provide both in-app entry and external request URL; retention for financial/legal records must be explained. Disabling an account is not deletion.
3. Native registration/password recovery still intentionally unavailable; existing-account login only. Resolve the product flow or describe it accurately.
4. Public text/photo reviews are UGC. No guest-facing reporting/blocking pathway found. Add content rules/acceptance, reporting and appropriate moderation/blocking before public release.
5. Store reviewer access must remain usable, with English instructions and fictional records. Do not bypass production authorization or provide a real unrestricted admin account.
6. No registered developer account yet; identity verification, test-track conditions, Play review and owner-supplied legal facts remain external gates.

Sources:
- https://support.google.com/googleplay/android-developer/answer/10144311?hl=en
- https://support.google.com/googleplay/android-developer/answer/10787469?hl=en
- https://support.google.com/googleplay/android-developer/answer/13327111?hl=en
- https://support.google.com/googleplay/android-developer/answer/9876937?hl=en
- https://support.google.com/googleplay/android-developer/answer/15748846?hl=en

## Payments

Sanatorium accommodation is a physical service. Google Play Billing must not be used for physical-service purchases, so current external Kaspi/XPayment flow can remain for accommodation bookings. This does not automatically authorize any future paid digital SaaS features/subscriptions in the staff app; evaluate those separately. Clear total/pay-now/onsite amounts must remain accurate.

Source: https://support.google.com/googleplay/android-developer/answer/9858738?hl=en
