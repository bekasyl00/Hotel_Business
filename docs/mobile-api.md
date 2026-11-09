# Native guest API

The Django API supports native guest access independently of browser cookies. Capacitor clients exist for iOS and Android, with two separate applications on each platform: guest `kz.tynys.booking` and staff `kz.tynys.staff`. See [ios.md](ios.md) and [android.md](android.md) for build/distribution instructions, and [verification.md](verification.md) for observed results. Staff has separate web and native sessions; a guest Bearer token never grants staff access, even if the request also carries a staff cookie.

The paths below use the `/api/v1` prefix. The same endpoints remain available at `/api` for the existing web client. Send JSON bodies and use HTTPS outside localhost.

| Method/path | Request | Result |
| --- | --- | --- |
| POST `/mobile-auth/login` | `{phone,password,deviceName}` | New device token family and account/profile |
| POST `/mobile-auth/refresh` | `{refreshToken}` | Rotated access and refresh tokens |
| POST `/mobile-auth/logout` | `{}` + Bearer | Revoke current device, HTTP 204 |
| GET `/mobile-auth/sessions` | Bearer | Current account's active device sessions |
| DELETE `/mobile-auth/sessions/:id` | Bearer | Revoke owned device, HTTP 204; foreign ID 404 |

Login/refresh return `{tokenType:"Bearer",accessToken,refreshToken,expiresIn,refreshExpiresAt,deviceId,account,profile}`. Access tokens expire after 15 minutes. A token family expires 30 days after login; refreshing does not extend that absolute lifetime. Refresh immediately invalidates the preceding access token and marks the presented refresh token consumed. Reusing any consumed refresh token revokes the entire device family, including newly issued access tokens. Clients must serialize refresh requests and replace stored credentials atomically; retrying a consumed token requires signing in again. Refresh calls must omit the expired access token from `Authorization`.

Send `Authorization: Bearer <accessToken>` on the existing guest API: profile, own bookings, reviews/media and receipts/payments. Ownership is resolved from the account's existing profile, exactly as in cookie authentication. No caller-supplied owner ID is trusted. An invalid, expired or revoked Authorization token returns 401 and cannot fall back to a browser cookie or anonymous booking. Server storage contains only HMAC-SHA256 token hashes. Password reset/account deactivation invalidate every device through the account's authentication version/active state.

Both platforms use the same `TynysKeychain.read/write/clear` JavaScript contract. The iOS bridge implements per-bundle Keychain storage with WhenUnlockedThisDeviceOnly. The shared Android bridge in `native/android` uses a non-exportable AndroidKeyStore AES-256 key, AES-GCM with a fresh IV per write, and ciphertext-only atomic storage in the app's no-backup directory. Guest and staff packages have separate Android UIDs, vault namespaces and credentials. A missing/unusable key or damaged ciphertext does not enable a plaintext fallback; credentials never belong in preferences, browser storage, logs, URLs or analytics. Device attestation, biometrics and push notifications are not implemented. A compiled simulator/emulator build does not certify physical-device or cloud API integration. `deviceName` identifies the app audience and platform for display, not a cryptographic device binding. `lastUsedAt` records credential issuance/refresh, not every API request.

Native login requires an existing guest account. The app's registration/recovery screens hand off to the configured public website's fixed HTTPS `/account/register` or `/account/reset-password` route in the browser. The link carries no native credentials, return-path query or automatic login exchange; after completing an available website flow, the user returns to the app and signs in. Website availability still follows server configuration: temporary phone/password registration can be enabled while SMS is pending, whereas recovery must not bypass its challenge requirement. Real SMS and a native-specific challenge transport remain outstanding. Demo OTP requires both DEBUG and GUEST_AUTH_DEMO_OTP. Native login does not verify phone ownership by itself.

Browser mutations still require the existing cookie/CSRF handshake. Native credential endpoints consume JSON credentials rather than cookies. Other guest mutations bypass CSRF only after a valid explicit Bearer token has been authenticated. No wildcard CORS is added. Web pages should continue using HttpOnly sessions rather than persisting these tokens in localStorage.

Run `backend/.venv/bin/python backend/manage.py cleanup_mobile_sessions` as a scheduled maintenance job to delete expired device families and their consumed-token hashes. Keep consumed hashes until the absolute family expiry so replay detection remains possible. Configure request/credential log redaction and edge abuse controls before public traffic; the API shares web/native password attempt limits and limits refresh attempts in PostgreSQL.

Tests in `booking/test_mobile_auth.py` cover guest ownership, cookie/role isolation, web CSRF, expiry, reset, per-device revocation and concurrent refresh replay against PostgreSQL.


## Separate staff app

`/staff-mobile-auth/login` accepts `{email,password,deviceName}` and returns the same token envelope with `user` (the existing staff account serializer) instead of guest `account/profile`. `/refresh`, `/logout`, `/sessions` and `/sessions/:id` use the same methods as their guest equivalents. Access expires after 15 minutes; the staff family expires after **12 hours** without extending its absolute lifetime. Web/native login share the existing PostgreSQL staff-attempt budget.

`ts_a_` / `ts_r_` credentials use separate StaffDevice/StaffRefreshToken records. A guest token cannot access these endpoints; staff credentials cannot be used for guest profile/authentication. Staff API permissions and resort scope remain in domain services. A staff Bearer does not sign into Django Admin or create a browser cookie. Password, role, resort assignment, superuser flag changes and deactivation invalidate the issued credential version. Concurrent refresh reuse commits family revocation. Per-device deletion checks ownership. `cleanup_mobile_sessions` removes expired families for both audiences.

Apply identity migration 0002 before serving staff-native traffic. Native app files and API transport are shared, but bundle IDs, routes, storage, audience and credentials are separate. Browser writes continue to require CSRF; the wrapper skips it only after successfully authenticating an explicit native token. The mobile client serializes refresh and never retries a consumed token following an uncertain result.


Web-only temporary signup (08.11.2026): `GUEST_AUTH_ALLOW_UNVERIFIED_REGISTRATION` can enable web phone/password registration while SMS is pending. It does not add a native registration/reset endpoint or relax Bearer/CSRF rules. Existing native login/refresh account data now includes `phoneVerified:boolean`; temporary and demo accounts remain false. No phone-only reset is introduced.


## Android APK distribution

The current Android delivery is two signed release APKs distributed by download links; Google Play publication is deferred by the owner. Each package bundles its audience-specific API build and uses the same Django endpoints and financial rules as iOS/web. No remote Capacitor `server.url`, backend credentials or private signing material belongs in an APK. Preserve and privately back up the distribution signing keys: future APK updates must retain the package ID and compatible signature. A later Google Play transition must account for those existing installed signatures. Release commands and verification criteria are documented in [android.md](android.md); signed build creation, emulator/device tests and public-link delivery are separate results recorded in [verification.md](verification.md).
