package kz.tynys.nativeauth;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONObject;

/** Retains the existing JS vault contract; Android credentials live behind AndroidKeyStore. */
@CapacitorPlugin(name = "TynysKeychain")
public final class TynysKeychain extends Plugin {
    private SecureSessionStore store;

    @Override
    public void load() {
        store = new SecureSessionStore(getContext());
    }

    @PluginMethod
    public void read(PluginCall call) {
        try {
            String value = store.read();
            JSObject result = new JSObject();
            result.put("value", value == null ? JSONObject.NULL : value);
            call.resolve(result);
        } catch (Exception exception) {
            call.reject("Secure session storage is unavailable.", "keychain_read");
        }
    }

    @PluginMethod
    public void write(PluginCall call) {
        try {
            store.write(call.getString("value"));
            call.resolve();
        } catch (IllegalArgumentException exception) {
            call.reject("Invalid session.", "keychain_input");
        } catch (Exception exception) {
            call.reject("Could not save session securely.", "keychain_write");
        }
    }

    @PluginMethod
    public void clear(PluginCall call) {
        try {
            store.clear();
            call.resolve();
        } catch (Exception exception) {
            call.reject("Could not remove secure session.", "keychain_clear");
        }
    }
}
