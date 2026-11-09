package kz.tynys.nativeauth;

import android.app.KeyguardManager;
import android.content.Context;
import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyPermanentlyInvalidatedException;
import android.security.keystore.KeyProperties;
import android.util.AtomicFile;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.UnrecoverableKeyException;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** One encrypted session per app UID. Never restores credentials from a backup. */
public final class SecureSessionStore {
    public static final int MAX_BYTES = 16_384;
    private static final int MAGIC = 0x54595331; // TYS1, envelope version 1
    private static final int IV_BYTES = 12;
    private static final int TAG_BYTES = 16;
    private static final int HEADER_BYTES = Integer.BYTES + IV_BYTES;
    private static final Object LOCK = new Object();
    private final Context context;
    private final AtomicFile file;
    private final String alias;
    private final byte[] associatedData;

    public SecureSessionStore(Context context) {
        this(context, "current");
    }

    // Tests use their own namespace; the bridge always uses the public constructor.
    SecureSessionStore(Context context, String namespace) {
        if (!namespace.matches("[a-z0-9-]{1,80}")) throw new IllegalArgumentException("Invalid namespace");
        this.context = context.getApplicationContext();
        this.alias = this.context.getPackageName() + ".native-session.v1." + namespace;
        this.associatedData = alias.getBytes(StandardCharsets.UTF_8);
        this.file = new AtomicFile(new File(this.context.getNoBackupFilesDir(), "tynys-session-" + namespace + ".v1"));
    }

    public String read() throws IOException, GeneralSecurityException {
        synchronized (LOCK) {
            requireUnlocked();
            try {
                byte[] envelope = readEnvelope();
                if (envelope == null) return null;
                ByteBuffer buffer = ByteBuffer.wrap(envelope);
                if (buffer.getInt() != MAGIC) throw new CorruptSessionException();
                byte[] iv = new byte[IV_BYTES];
                buffer.get(iv);
                byte[] ciphertext = new byte[buffer.remaining()];
                buffer.get(ciphertext);
                SecretKey key = existingKey();
                if (key == null) throw new CorruptSessionException();
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BYTES * 8, iv));
                cipher.updateAAD(associatedData);
                byte[] plaintext = cipher.doFinal(ciphertext);
                try {
                    if (plaintext.length > MAX_BYTES) throw new CorruptSessionException();
                    return StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(plaintext)).toString();
                } catch (CharacterCodingException exception) {
                    throw new CorruptSessionException();
                } finally {
                    Arrays.fill(plaintext, (byte) 0);
                }
            } catch (CorruptSessionException | AEADBadTagException |
                     KeyPermanentlyInvalidatedException | UnrecoverableKeyException exception) {
                // Unusable credentials cannot authorize a request or retry an old refresh.
                // A clean login can create a new key; transient I/O/Keystore failures are NOT reset.
                clearLocked();
                return null;
            }
        }
    }

    public void write(String value) throws IOException, GeneralSecurityException {
        if (value == null) throw new IllegalArgumentException("Invalid session");
        byte[] plaintext = value.getBytes(StandardCharsets.UTF_8);
        try {
            if (plaintext.length > MAX_BYTES) throw new IllegalArgumentException("Invalid session");
            synchronized (LOCK) {
                requireUnlocked();
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
                cipher.updateAAD(associatedData);
                byte[] iv = cipher.getIV(); // Keystore generates a fresh random IV for every write.
                if (iv.length != IV_BYTES) throw new GeneralSecurityException("Invalid cipher parameters");
                byte[] ciphertext = cipher.doFinal(plaintext);
                byte[] envelope = ByteBuffer.allocate(HEADER_BYTES + ciphertext.length)
                    .putInt(MAGIC).put(iv).put(ciphertext).array();
                FileOutputStream stream = null;
                try {
                    stream = file.startWrite();
                    stream.write(envelope);
                    stream.flush();
                    stream.getFD().sync();
                    file.finishWrite(stream);
                    stream = null;
                    // AtomicFile's finishWrite returns void; do not acknowledge a failed replacement.
                    if (!Arrays.equals(envelope, readEnvelope())) throw new IOException("Session write failed");
                } catch (IOException | RuntimeException exception) {
                    if (stream != null) file.failWrite(stream);
                    throw exception;
                }
            }
        } finally {
            Arrays.fill(plaintext, (byte) 0);
        }
    }

    public void clear() throws IOException, GeneralSecurityException {
        synchronized (LOCK) {
            clearLocked();
        }
    }

    private byte[] readEnvelope() throws IOException, CorruptSessionException {
        try (FileInputStream stream = file.openRead()) {
            long size = stream.getChannel().size();
            if (size < HEADER_BYTES + TAG_BYTES || size > HEADER_BYTES + MAX_BYTES + TAG_BYTES)
                throw new CorruptSessionException();
            byte[] envelope = new byte[(int) size];
            int offset = 0;
            while (offset < envelope.length) {
                int count = stream.read(envelope, offset, envelope.length - offset);
                if (count < 0) throw new CorruptSessionException();
                offset += count;
            }
            if (stream.read() != -1) throw new CorruptSessionException();
            return envelope;
        } catch (FileNotFoundException exception) {
            // Only a genuinely absent file is an empty vault; permissions/storage errors fail closed.
            if (file.getBaseFile().exists() || sibling(".bak").exists()) throw exception;
            return null;
        }
    }

    private SecretKey existingKey() throws GeneralSecurityException, IOException {
        KeyStore store = keyStore();
        return (SecretKey) store.getKey(alias, null);
    }

    private SecretKey getOrCreateKey() throws GeneralSecurityException, IOException {
        SecretKey key = existingKey();
        if (key != null) return key;
        KeyGenParameterSpec.Builder spec = new KeyGenParameterSpec.Builder(alias,
            KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setRandomizedEncryptionRequired(true);
        // Android documents lock-screen/key-loss bugs before API35 for this extra restriction.
        // Older versions still use credential-protected storage and the explicit lock check above.
        if (Build.VERSION.SDK_INT >= 35) spec.setUnlockedDeviceRequired(true);
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        generator.init(spec.build());
        return generator.generateKey();
    }

    private KeyStore keyStore() throws GeneralSecurityException, IOException {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        return store;
    }

    private void clearLocked() throws GeneralSecurityException, IOException {
        keyStore().deleteEntry(alias); // Invalidate ciphertext first, even if file removal fails.
        file.delete();
        if (file.getBaseFile().exists() || sibling(".bak").exists() || sibling(".new").exists())
            throw new IOException("Session removal failed");
    }

    private File sibling(String suffix) {
        return new File(file.getBaseFile().getPath() + suffix);
    }

    private void requireUnlocked() throws GeneralSecurityException {
        KeyguardManager keyguard = context.getSystemService(KeyguardManager.class);
        if (keyguard == null || keyguard.isDeviceLocked())
            throw new GeneralSecurityException("Secure session requires an unlocked device");
    }

    private static final class CorruptSessionException extends GeneralSecurityException {}
}
