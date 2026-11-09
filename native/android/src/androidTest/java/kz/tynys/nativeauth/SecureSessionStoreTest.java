package kz.tynys.nativeauth;

import static org.junit.Assert.*;

import android.content.Context;
import android.util.AtomicFile;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.DataInputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import java.util.UUID;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

/** Runs against real AndroidKeyStore on an emulator/device, only in a unique test namespace. */
@RunWith(AndroidJUnit4.class)
public class SecureSessionStoreTest {
    private Context context;
    private String namespace;
    private SecureSessionStore store;
    private File ciphertext;

    @Before
    public void setUp() {
        context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        namespace = "test-" + UUID.randomUUID();
        store = new SecureSessionStore(context, namespace);
        ciphertext = new File(context.getNoBackupFilesDir(), "tynys-session-" + namespace + ".v1");
    }

    @After
    public void tearDown() throws Exception {
        store.clear();
    }

    @Test
    public void sessionSurvivesRecreationWithoutPlaintextOnDisk() throws Exception {
        String value = "{\"accessToken\":\"fictional-access-token\",\"refreshToken\":\"fictional-refresh\",\"label\":\"Тыныс\"}";
        assertNull(store.read());
        store.write(value);
        assertEquals(value, new SecureSessionStore(context, namespace).read());
        assertFalse(new String(readBytes(ciphertext), StandardCharsets.UTF_8).contains("fictional"));
        assertNull(keyStore().getKey(alias(), null).getEncoded());
        store.clear();
        store.clear();
        assertNull(store.read());
        assertFalse(ciphertext.exists());
        assertFalse(keyStore().containsAlias(alias()));
    }

    @Test
    public void everyReplacementUsesFreshIvAndOnlyLatestSessionIsRead() throws Exception {
        store.write("first-session");
        byte[] first = readBytes(ciphertext);
        store.write("first-session");
        byte[] second = readBytes(ciphertext);
        assertFalse(Arrays.equals(first, second));
        store.write("{\"pending\":true}");
        assertEquals("{\"pending\":true}", store.read());
    }

    @Test
    public void byteLimitRejectsMultibyteOverflowWithoutReplacingSession() throws Exception {
        store.write("previous-session");
        String overLimit = new String(new char[SecureSessionStore.MAX_BYTES / 2 + 1]).replace('\0', 'я');
        try {
            store.write(overLimit);
            fail("Oversized UTF-8 must be rejected");
        } catch (IllegalArgumentException expected) {
            assertEquals("previous-session", store.read());
        }
        String exactLimit = new String(new char[SecureSessionStore.MAX_BYTES / 2]).replace('\0', 'я');
        store.write(exactLimit);
        assertEquals(exactLimit, store.read());
    }

    @Test
    public void tamperingResetsLocalCredentialsAndAllowsFreshLogin() throws Exception {
        store.write("old-session");
        byte[] bytes = readBytes(ciphertext);
        bytes[bytes.length - 1] ^= 1;
        writeBytes(ciphertext, bytes);
        assertNull(store.read());
        assertFalse(ciphertext.exists());
        assertFalse(keyStore().containsAlias(alias()));
        store.write("new-login");
        assertEquals("new-login", store.read());
    }

    @Test
    public void lostKeyNeverReturnsCredentialsOrRetriesOldRefresh() throws Exception {
        store.write("lost-refresh-token");
        keyStore().deleteEntry(alias());
        assertNull(store.read());
        assertFalse(ciphertext.exists());
        store.write("new-login");
        assertEquals("new-login", store.read());
    }

    @Test
    public void truncatedEnvelopeFailsClosed() throws Exception {
        store.write("session");
        writeBytes(ciphertext, new byte[] {0x54, 0x59});
        assertNull(store.read());
        assertFalse(ciphertext.exists());
    }

    @Test
    public void failedAtomicWriteRetainsLastCompleteEnvelope() throws Exception {
        store.write("complete-session");
        AtomicFile atomic = new AtomicFile(ciphertext);
        FileOutputStream failed = atomic.startWrite();
        failed.write(new byte[] {1, 2, 3});
        atomic.failWrite(failed);
        assertEquals("complete-session", store.read());
    }

    @Test
    public void copiedCiphertextCannotCrossVaultNamespace() throws Exception {
        String otherNamespace = "test-" + UUID.randomUUID();
        SecureSessionStore other = new SecureSessionStore(context, otherNamespace);
        File otherFile = new File(context.getNoBackupFilesDir(), "tynys-session-" + otherNamespace + ".v1");
        try {
            store.write("session-one");
            other.write("session-two");
            writeBytes(otherFile, readBytes(ciphertext));
            assertNull(other.read());
            assertEquals("session-one", store.read());
        } finally {
            other.clear();
        }
    }

    private byte[] readBytes(File file) throws IOException {
        byte[] bytes = new byte[(int) file.length()];
        try (DataInputStream input = new DataInputStream(new FileInputStream(file))) {
            input.readFully(bytes);
        }
        return bytes;
    }

    private void writeBytes(File file, byte[] bytes) throws IOException {
        try (FileOutputStream output = new FileOutputStream(file)) {
            output.write(bytes);
        }
    }

    private String alias() {
        return context.getPackageName() + ".native-session.v1." + namespace;
    }

    private KeyStore keyStore() throws Exception {
        KeyStore keys = KeyStore.getInstance("AndroidKeyStore");
        keys.load(null);
        return keys;
    }
}
