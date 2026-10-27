import Capacitor
import Security

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
        CAPPluginMethod(name: "clear", returnType: CAPPluginReturnPromise)
    ]
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
}
