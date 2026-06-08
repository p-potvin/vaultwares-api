import { describe, it, expect } from 'vitest';

// Argon2id at t=3, m=64MiB takes ~3-6s per derivation on a typical machine.
// Each setup+unlock triggers two derivations. Bump per-test timeout accordingly.
const TEST_TIMEOUT_MS = 30000;
import {
  setupVault,
  unlockVault,
  encryptBlobWithUnlocked,
  decryptBlob,
  envelopeToBytes,
  envelopeFromBytes,
} from './crypto-vault';

const PIN = '1234';
const SAMPLE = new TextEncoder().encode('hello vault — encrypted blob payload, post-quantum.');

describe('crypto-vault', { timeout: TEST_TIMEOUT_MS }, () => {
  it('roundtrips ML-KEM-1024 via setupVault → unlock → encrypt → decrypt', async () => {
    const material = await setupVault(PIN, 'ml-kem-1024');
    expect(material.algorithm).toBe('ml-kem-1024');
    expect(material.publicKey).toBeDefined();
    expect(material.publicKey!.length).toBe(1568); // ML-KEM-1024 public key size
    expect(material.wrappedPrivateKey).toBeDefined();

    const vault = await unlockVault(PIN, material);
    expect(vault).not.toBeNull();
    expect(vault!.privateKey).toBeDefined();
    expect(vault!.privateKey!.length).toBe(3168); // ML-KEM-1024 private key size

    const env = await encryptBlobWithUnlocked(SAMPLE, vault!);
    expect(env.kemCiphertext).toBeDefined();

    const plain = await decryptBlob(env, vault!);
    expect(new TextDecoder().decode(plain)).toBe(new TextDecoder().decode(SAMPLE));
  });

  it('rejects wrong PIN on unlock', async () => {
    const material = await setupVault(PIN, 'ml-kem-1024');
    const wrongVault = await unlockVault('9999', material);
    expect(wrongVault).toBeNull();
  });

  it('roundtrips ML-KEM-512', async () => {
    const material = await setupVault(PIN, 'ml-kem-512');
    expect(material.publicKey!.length).toBe(800); // ML-KEM-512 public key size
    const vault = await unlockVault(PIN, material);
    const env = await encryptBlobWithUnlocked(SAMPLE, vault!);
    const plain = await decryptBlob(env, vault!);
    expect(Array.from(plain)).toEqual(Array.from(SAMPLE));
  });

  it('roundtrips AES-only fallback', async () => {
    const material = await setupVault(PIN, 'aes-only');
    const vault = await unlockVault(PIN, material);
    expect(vault!.privateKey).toBeUndefined();
    const env = await encryptBlobWithUnlocked(SAMPLE, vault!);
    expect(env.kemCiphertext).toBeUndefined();
    const plain = await decryptBlob(env, vault!);
    expect(Array.from(plain)).toEqual(Array.from(SAMPLE));
  });

  it('serializes and deserializes envelope to bytes losslessly', async () => {
    const material = await setupVault(PIN, 'ml-kem-1024');
    const vault = await unlockVault(PIN, material);
    const env = await encryptBlobWithUnlocked(SAMPLE, vault!);

    const bytes = envelopeToBytes(env);
    const round = envelopeFromBytes(bytes);

    expect(round.algorithm).toBe(env.algorithm);
    expect(Array.from(round.kemCiphertext!)).toEqual(Array.from(env.kemCiphertext!));
    expect(Array.from(round.wrappedDek)).toEqual(Array.from(env.wrappedDek));
    expect(Array.from(round.wrappedDekIv)).toEqual(Array.from(env.wrappedDekIv));
    expect(Array.from(round.payload)).toEqual(Array.from(env.payload));
    expect(Array.from(round.payloadIv)).toEqual(Array.from(env.payloadIv));

    const plain = await decryptBlob(round, vault!);
    expect(Array.from(plain)).toEqual(Array.from(SAMPLE));
  });

  it('two PINs of different lengths produce different KEKs', async () => {
    const m1 = await setupVault('1234', 'aes-only');
    const m2 = await setupVault('1234567890', 'aes-only');
    // different salt + same PIN derives different KEK; but pinVerifier comparison
    // should still reject swap-loaded material.
    const cross = await unlockVault('1234', m2);
    expect(cross).toBeNull();
  });
});
