package com.academy.message.service;

import com.academy.message.model.MailCredentials;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;

public class MailCredentialStore {
    private static final int PBKDF2_ITERATIONS = 210_000;
    private static final int KEY_LENGTH_BITS = 256;
    private static final int GCM_TAG_BITS = 128;
    private static final int SALT_LENGTH = 16;
    private static final int IV_LENGTH = 12;
    private static final String FILE_VERSION = "2";

    private final SecureRandom secureRandom;
    private final Path credentialPath;

    public MailCredentialStore() {
        this(defaultCredentialPath(), new SecureRandom());
    }

    public MailCredentialStore(Path credentialPath) {
        this(credentialPath, new SecureRandom());
    }

    MailCredentialStore(Path credentialPath, SecureRandom secureRandom) {
        this.credentialPath = credentialPath.toAbsolutePath().normalize();
        this.secureRandom = secureRandom;
    }

    public void save(MailCredentials credentials, char[] masterPassword)
            throws IOException, GeneralSecurityException {
        validateMasterPassword(masterPassword);
        byte[] salt = randomBytes(SALT_LENGTH);
        byte[] iv = randomBytes(IV_LENGTH);
        SecretKey key = deriveKey(masterPassword, salt);

        String plainText = encode(credentials.getUsername()) + "\n"
                + encode(credentials.getPassword());

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(GCM_TAG_BITS, iv));
        byte[] encrypted = cipher.doFinal(plainText.getBytes(StandardCharsets.UTF_8));

        Files.createDirectories(credentialPath.getParent());
        Files.write(credentialPath, List.of(
                FILE_VERSION,
                Base64.getEncoder().encodeToString(salt),
                Base64.getEncoder().encodeToString(iv),
                Base64.getEncoder().encodeToString(encrypted)), StandardCharsets.UTF_8);
    }

    public MailCredentials load(char[] masterPassword)
            throws IOException, GeneralSecurityException {
        validateMasterPassword(masterPassword);
        if (!Files.exists(credentialPath)) {
            throw new IOException("암호화된 메일 계정 설정이 없습니다.");
        }

        List<String> lines = Files.readAllLines(credentialPath, StandardCharsets.UTF_8);
        if (lines.size() != 4 || !FILE_VERSION.equals(lines.get(0))) {
            throw new IOException("메일 계정 암호화 파일 형식이 올바르지 않습니다.");
        }

        byte[] salt = Base64.getDecoder().decode(lines.get(1));
        byte[] iv = Base64.getDecoder().decode(lines.get(2));
        byte[] encrypted = Base64.getDecoder().decode(lines.get(3));
        SecretKey key = deriveKey(masterPassword, salt);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(GCM_TAG_BITS, iv));
        String plainText = new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        String[] values = plainText.split("\n", -1);
        if (values.length != 2) {
            throw new IOException("복호화된 메일 계정 형식이 올바르지 않습니다.");
        }
        return new MailCredentials(decode(values[0]), decode(values[1]));
    }

    public boolean exists() {
        return Files.exists(credentialPath);
    }

    public Path getCredentialPath() {
        return credentialPath;
    }

    private SecretKey deriveKey(char[] masterPassword, byte[] salt) throws GeneralSecurityException {
        PBEKeySpec spec = new PBEKeySpec(masterPassword, salt, PBKDF2_ITERATIONS, KEY_LENGTH_BITS);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256");
            return new SecretKeySpec(factory.generateSecret(spec).getEncoded(), "AES");
        } finally {
            spec.clearPassword();
        }
    }

    private byte[] randomBytes(int length) {
        byte[] bytes = new byte[length];
        secureRandom.nextBytes(bytes);
        return bytes;
    }

    private void validateMasterPassword(char[] masterPassword) {
        if (masterPassword == null || masterPassword.length < 8) {
            throw new IllegalArgumentException("마스터 암호는 8자 이상이어야 합니다.");
        }
    }

    private String encode(String value) {
        String safe = value == null ? "" : value;
        return Base64.getEncoder().encodeToString(safe.getBytes(StandardCharsets.UTF_8));
    }

    private String decode(String value) {
        return new String(Base64.getDecoder().decode(value), StandardCharsets.UTF_8);
    }

    private static Path defaultCredentialPath() {
        String configuredDirectory = System.getenv("ACADEMY_DATA_DIR");
        Path dataDirectory = configuredDirectory == null || configuredDirectory.isBlank()
                ? Path.of(System.getProperty("user.home"), ".academy-message-manager")
                : Path.of(configuredDirectory.trim());
        return dataDirectory.resolve("mail_credentials.enc");
    }
}
