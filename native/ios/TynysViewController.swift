import Capacitor
import Security
import UserNotifications

class TynysViewController: CAPBridgeViewController {
    override func capacitorDidLoad() {
        bridge?.registerPluginInstance(TynysKeychain())
    }
}

@objc(TynysKeychain)
public class TynysKeychain: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "TynysKeychain"
    public let jsName = "TynysKeychain"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "read", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "write", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "clear", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "openSettings", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "pushAvailable", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "localRequests", returnType: CAPPluginReturnPromise)
    ]
    private var wakeObservers: [NSObjectProtocol] = []
    public override func load() {
        guard Bundle.main.bundleIdentifier == "kz.tynys.staff" else { return }
        for name in [UIApplication.didBecomeActiveNotification, Notification.Name("TynysOpenRequests")] {
            wakeObservers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                self?.notifyListeners("requestsWake", data: [:])
            })
        }
    }
    deinit { wakeObservers.forEach(NotificationCenter.default.removeObserver) }
    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: (Bundle.main.bundleIdentifier ?? "kz.tynys.booking") + ".native-session",
         kSecAttrAccount as String: "current",
         kSecAttrSynchronizable as String: false]
    }
    @objc func read(_ call: CAPPluginCall) {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { call.resolve(["value": NSNull()]); return }
        guard status == errSecSuccess, let data = result as? Data,
              let value = String(data: data, encoding: .utf8) else {
            call.reject("Secure session storage is unavailable.", "keychain_read"); return
        }
        call.resolve(["value": value])
    }
    @objc func write(_ call: CAPPluginCall) {
        guard let value = call.getString("value"), let data = value.data(using: .utf8),
              data.count <= 16384 else { call.reject("Invalid session.", "keychain_input"); return }
        let attributes: [String: Any] = [kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var item = query
            item.merge(attributes) { _, new in new }
            status = SecItemAdd(item as CFDictionary, nil)
        }
        guard status == errSecSuccess else { call.reject("Could not save session securely.", "keychain_write"); return }
        call.resolve()
    }
    @objc func clear(_ call: CAPPluginCall) {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            call.reject("Could not remove secure session.", "keychain_clear"); return
        }
        call.resolve()
    }
    @objc func openSettings(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            if let url = URL(string: UIApplication.openSettingsURLString) {
                UIApplication.shared.open(url, options: [:]) { _ in call.resolve() }
            } else {
                call.resolve()
            }
        }
    }
    @objc func localRequests(_ call: CAPPluginCall) {
        Task { @MainActor in
            let service = RequestNotificationService.shared
            let result = await service.sync(
                account: call.getString("account") ?? "",
                items: call.getArray("items", JSObject.self) ?? [],
                askPermission: call.getBool("askPermission") ?? false)
            call.resolve(result)
        }
    }
    @objc func pushAvailable(_ call: CAPPluginCall) {
        call.resolve(["available": true])
    }
}

// Local-only delivery. No APNs registration, device token, or background fetch.
@MainActor
final class RequestNotificationService: NSObject, UNUserNotificationCenterDelegate {
    static let shared = RequestNotificationService()
    private let center = UNUserNotificationCenter.current()
    private var busy = false
    private var activeAccount = UserDefaults.standard.string(forKey: "local-request-account") ?? ""
    private var tappedAccount: String?

    func install() { center.delegate = self }

    func sync(account: String, items: [JSObject], askPermission: Bool) async -> JSObject {
        install()
        guard !busy else { return [:] }
        busy = true
        defer { busy = false }
        if activeAccount != account {
            center.removeAllPendingNotificationRequests()
            center.removeAllDeliveredNotifications()
            activeAccount = account
            UserDefaults.standard.set(account, forKey: "local-request-account")
        }
        var settings = await center.notificationSettings()
        if askPermission && !account.isEmpty && settings.authorizationStatus == .notDetermined {
            _ = try? await center.requestAuthorization(options: [.alert, .sound, .badge])
            settings = await center.notificationSettings()
        }
        let granted = settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
        let permission = settings.authorizationStatus == .denied ? "denied" : (granted ? "granted" : "prompt")
        let shouldOpen = !account.isEmpty && tappedAccount == account
        tappedAccount = nil
        guard !account.isEmpty else { return ["permission": permission] }
        let key = "local-request-ids." + account
        var seen = Set(UserDefaults.standard.stringArray(forKey: key) ?? [])
        for item in items {
            guard let id = item["id"] as? String, !id.isEmpty else { continue }
            let identifier = "request." + account + "." + id
            if item["readAt"] is String || item["read"] as? Bool == true {
                seen.insert(id)
                center.removeDeliveredNotifications(withIdentifiers: [identifier])
                center.removePendingNotificationRequests(withIdentifiers: [identifier])
                continue
            }
            guard granted, !seen.contains(id) else { continue }
            let content = UNMutableNotificationContent()
            content.title = "Новый запрос"
            content.body = String((item["body"] as? String ?? item["title"] as? String ?? "Откройте раздел запросов").prefix(180))
            content.sound = .default
            content.userInfo = ["account": account, "section": "notifications"]
            do {
                try await center.add(UNNotificationRequest(identifier: identifier, content: content, trigger: nil))
                seen.insert(id)
                // Persist after each accepted notification; relaunches must not repeat it.
                UserDefaults.standard.set(Array(seen), forKey: key)
            } catch { /* Keep unseen: a future foreground check can retry. */ }
        }
        UserDefaults.standard.set(Array(seen), forKey: key)
        return ["permission": permission, "openRequests": shouldOpen]
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list, .sound])
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void) {
        let account = response.notification.request.content.userInfo["account"] as? String
        Task { @MainActor in
            self.tappedAccount = account
            NotificationCenter.default.post(name: Notification.Name("TynysOpenRequests"), object: nil)
            completionHandler()
        }
    }
}
