# Native guest API

The Django API now supports native guest access independently of browser cookies. Two Capacitor iOS applications now exist; see [ios.md](ios.md). Android is not implemented. Staff has separate web and native sessions; a guest Bearer token never grants staff access, even if the request also carries a staff cookie.

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

The native app must keep credentials in OS-protected storage such as iOS Keychain or Android Keystore-backed storage, never ordinary application preferences, logs, URLs or analytics. The iOS bridge implements per-bundle Keychain storage with WhenUnlockedThisDeviceOnly. Device attestation, biometrics and push notifications are not implemented. A compiled simulator build does not certify physical-device or cloud API integration. `deviceName` is a user-facing label, not a cryptographic device binding. `lastUsedAt` records credential issuance/refresh, not every API request.

Native login requires an existing guest account. Registration and recovery currently use the existing web OTP challenge flow; real SMS and a native-specific challenge transport remain outstanding. Demo OTP requires both DEBUG and GUEST_AUTH_DEMO_OTP. Native login does not verify phone ownership by itself.

Browser mutations still require the existing cookie/CSRF handshake. Native credential endpoints consume JSON credentials rather than cookies. Other guest mutations bypass CSRF only after a valid explicit Bearer token has been authenticated. No wildcard CORS is added. Web pages should continue using HttpOnly sessions rather than persisting these tokens in localStorage.

Run `backend/.venv/bin/python backend/manage.py cleanup_mobile_sessions` as a scheduled maintenance job to delete expired device families and their consumed-token hashes. Keep consumed hashes until the absolute family expiry so replay detection remains possible. Configure request/credential log redaction and edge abuse controls before public traffic; the API shares web/native password attempt limits and limits refresh attempts in PostgreSQL.

Tests in `booking/test_mobile_auth.py` cover guest ownership, cookie/role isolation, web CSRF, expiry, reset, per-device revocation and concurrent refresh replay against PostgreSQL.


## Separate staff app

`/staff-mobile-auth/login` accepts `{email,password,deviceName}` and returns the same token envelope with `user` (the existing staff account serializer) instead of guest `account/profile`. `/refresh`, `/logout`, `/sessions` and `/sessions/:id` use the same methods as their guest equivalents. Access expires after 15 minutes; the staff family expires after **12 hours** without extending its absolute lifetime. Web/native login share the existing PostgreSQL staff-attempt budget.

`ts_a_` / `ts_r_` credentials use separate StaffDevice/StaffRefreshToken records. A guest token cannot access these endpoints; staff credentials cannot be used for guest profile/authentication. Staff API permissions and resort scope remain in domain services. A staff Bearer does not sign into Django Admin or create a browser cookie. Password, role, resort assignment, superuser flag changes and deactivation invalidate the issued credential version. Concurrent refresh reuse commits family revocation. Per-device deletion checks ownership. `cleanup_mobile_sessions` removes expired families for both audiences.

Apply identity migration 0002 before serving staff-native traffic. Native app files and API transport are shared, but bundle IDs, routes, storage, audience and credentials are separate. Browser writes continue to require CSRF; the wrapper skips it only after successfully authenticating an explicit native token. The mobile client serializes refresh and never retries a consumed token following an uncertain result.
