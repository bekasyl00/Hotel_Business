# Shared Android session bridge

`src/main/java/kz/tynys/nativeauth` is compiled into **each** Android application. It keeps the existing `TynysKeychain.read/write/clear` JavaScript contract; the name is a compatibility identifier, not an iOS implementation on Android.

Register `TynysKeychain.class` in each `BridgeActivity.onCreate` **before** `super.onCreate(savedInstanceState)`. Add this shared source folder to both app Gradle `sourceSets.main.java` and `src/androidTest/java` to each `sourceSets.androidTest.java`. The app namespaces/bundle IDs remain distinct. Do not expose the plugin to remote WebView content or enable a remote Capacitor `server.url`.

## Storage and recovery

- A non-exportable AES-256 key lives in AndroidKeyStore under a package-specific alias. AES-GCM uses a new provider-generated IV for every write, a 128-bit tag and authenticated package/namespace metadata.
- Only the bounded encrypted envelope is persisted in `getNoBackupFilesDir()`. No preferences, browser storage, logs, URL, backup or plaintext file receives credentials. `AtomicFile` plus a process lock serializes read/write/clear; a write is acknowledged only after sync and read-back verification. Keep the application single-process.
- The vault checks that the device is unlocked. On Android15/API35+ the key also requires an unlocked device. Earlier Android versions rely on the application lock check and normal credential-protected app storage: the extra Keystore flag is deliberately avoided because Android documents key-loss/lock-screen bugs before API35. This is not biometric authentication or device attestation.
- A missing/permanently invalidated key, bad authentication tag or invalid envelope destroys the local key/envelope and returns an empty vault. It never restores an old token or retries a consumed refresh credential. A fresh server login is then required. This does not remotely revoke a token whose server-side session still exists; remote revocation/expiry remains in Django.
- Transient I/O or Keystore errors reject with a generic message and preserve existing storage. `clear` invalidates the key before deleting ciphertext; failures are not reported as success. Explicit login already clears any previous local session before requesting new credentials.
- The 16,384-byte maximum is measured in UTF-8 bytes. Error messages never include data or exception details.

## Tests

`src/androidTest/java/kz/tynys/nativeauth/SecureSessionStoreTest.java` runs with AndroidJUnit4 against real AndroidKeyStore. It uses unique test namespaces and never touches the `current` production session. It checks round-trip/recreation, non-exportable key, ciphertext at rest, randomized replacement, Unicode byte bounds, tag tampering, missing key, malformed envelope, failed atomic-write recovery and namespace separation. Run on an unlocked Android emulator or test device with `./gradlew :app:connectedDebugAndroidTest` after wiring the shared test source set. Compilation alone is not evidence that these device tests passed.

Primary references: [Android Keystore](https://developer.android.com/privacy-and-security/keystore), [unlocked-device key behavior](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder#setUnlockedDeviceRequired(boolean)), [AtomicFile](https://developer.android.com/reference/android/util/AtomicFile), [backup exclusions](https://developer.android.com/identity/data/autobackup#Files), [Capacitor Android plugins](https://capacitorjs.com/docs/plugins/android).
