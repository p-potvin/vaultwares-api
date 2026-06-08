/**
 * Zero-knowledge envelope encryption per VaultWares Tier 1 standard:
 *   vaultwares-docs/security/zero-knowledge-encryption-standard.mdx
 *
 * Layout:
 *   PIN ──Argon2id──► master KEK (AES-256, derived per-vault from a stored salt)
 *   Long-term ML-KEM-1024 keypair: public stored plaintext; private wrapped with KEK
 *   Per-blob: random DEK (32 B), AES-256-GCM encrypts blob, KEM encapsulates to
 *   public key, AES-256-GCM-wraps DEK with the resulting shared secret.
 *
 * Falls back to ML-KEM-512 if the runtime asks for it, AES-only if neither is
 * available (caller must add NOTE.encryption.md per the standard).
 */
import { ml_kem1024, ml_kem512 } from '@noble/post-quantum/ml-kem.js';
import { argon2id } from '@noble/hashes/argon2.js';
import { sha256 } from '@noble/hashes/sha2.js';
const ARGON2_OPTS = { t: 3, m: 64 * 1024, p: 1, dkLen: 32 }; // m in KiB → 64 MiB
function getRandomBytes(n) {
    const out = new Uint8Array(n);
    crypto.getRandomValues(out);
    return out;
}
function pickKem(algorithm) {
    switch (algorithm) {
        case 'ml-kem-1024': return ml_kem1024;
        case 'ml-kem-512': return ml_kem512;
        case 'aes-only': return null;
    }
}
/** Derive the master KEK from the user's PIN and the per-vault salt. */
async function deriveKek(pin, salt) {
    // argon2id is sync in @noble/hashes; we wrap in a microtask to keep the API
    // async-shaped so callers don't accidentally block the event loop with a
    // direct sync call.
    return Promise.resolve(argon2id(pin, salt, ARGON2_OPTS));
}
async function aesGcmEncrypt(key, iv, plaintext) {
    const cryptoKey = await crypto.subtle.importKey('raw', key, { name: 'AES-GCM' }, false, ['encrypt']);
    const cipher = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, cryptoKey, plaintext);
    return new Uint8Array(cipher);
}
async function aesGcmDecrypt(key, iv, ciphertext) {
    const cryptoKey = await crypto.subtle.importKey('raw', key, { name: 'AES-GCM' }, false, ['decrypt']);
    const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: iv }, cryptoKey, ciphertext);
    return new Uint8Array(plain);
}
/**
 * Provision a new vault from a PIN. Generates the salt, derives the KEK, mints
 * an ML-KEM keypair, and wraps the private key for at-rest storage.
 */
export async function setupVault(pin, algorithm = 'ml-kem-1024') {
    const argonSalt = getRandomBytes(16);
    const kek = await deriveKek(pin, argonSalt);
    const verifyTag = new TextEncoder().encode('verify');
    const pinVerifier = sha256(new Uint8Array([...kek, ...verifyTag]));
    if (algorithm === 'aes-only') {
        return { algorithm, argonSalt, pinVerifier };
    }
    const kem = pickKem(algorithm);
    const seed = getRandomBytes(64); // ML-KEM keygen requires 64 bytes
    const { publicKey, secretKey } = kem.keygen(seed);
    const wrappedPrivateKeyIv = getRandomBytes(12);
    const wrappedPrivateKey = await aesGcmEncrypt(kek, wrappedPrivateKeyIv, secretKey);
    return {
        algorithm,
        argonSalt,
        pinVerifier,
        publicKey,
        wrappedPrivateKey,
        wrappedPrivateKeyIv,
    };
}
/**
 * Verify the PIN against stored material and return the unlocked vault state.
 * Returns null if the PIN is wrong (constant-ish time via SHA-256 comparison).
 */
export async function unlockVault(pin, material) {
    const kek = await deriveKek(pin, material.argonSalt);
    const verifyTag = new TextEncoder().encode('verify');
    const candidate = sha256(new Uint8Array([...kek, ...verifyTag]));
    if (!constantTimeEqual(candidate, material.pinVerifier))
        return null;
    if (material.algorithm === 'aes-only') {
        return { algorithm: material.algorithm, kek };
    }
    if (!material.wrappedPrivateKey || !material.wrappedPrivateKeyIv) {
        return null;
    }
    const privateKey = await aesGcmDecrypt(kek, material.wrappedPrivateKeyIv, material.wrappedPrivateKey);
    return { algorithm: material.algorithm, kek, publicKey: material.publicKey, privateKey };
}
function constantTimeEqual(a, b) {
    if (a.length !== b.length)
        return false;
    let diff = 0;
    for (let i = 0; i < a.length; i++)
        diff |= a[i] ^ b[i];
    return diff === 0;
}
/** Encrypt a blob under the vault's public key (zero-knowledge envelope). */
export async function encryptBlob(blob, material) {
    const dek = getRandomBytes(32);
    const payloadIv = getRandomBytes(12);
    const payload = await aesGcmEncrypt(dek, payloadIv, blob);
    if (material.algorithm === 'aes-only') {
        // Without ML-KEM, we have no asymmetric primitive — fall back to wrapping
        // the DEK directly with the KEK. This is symmetric envelope encryption,
        // documented in zero-knowledge-encryption-standard.mdx as the fallback.
        if (!material.publicKey) {
            throw new Error('aes-only fallback requires unlock to wrap DEK; use encryptBlobWithUnlocked instead');
        }
        throw new Error('aes-only fallback requires the unlocked KEK; call encryptBlobWithUnlocked');
    }
    if (!material.publicKey)
        throw new Error('Vault material is missing public key');
    const kem = pickKem(material.algorithm);
    const { cipherText, sharedSecret } = kem.encapsulate(material.publicKey);
    const wrappedDekIv = getRandomBytes(12);
    const wrappedDek = await aesGcmEncrypt(sharedSecret, wrappedDekIv, dek);
    return {
        algorithm: material.algorithm,
        kemCiphertext: cipherText,
        wrappedDek,
        wrappedDekIv,
        payload,
        payloadIv,
    };
}
/**
 * Encrypt a blob using an already-unlocked vault. Required when the algorithm
 * is 'aes-only' (the KEK is the wrapping key for the DEK).
 */
export async function encryptBlobWithUnlocked(blob, vault) {
    const dek = getRandomBytes(32);
    const payloadIv = getRandomBytes(12);
    const payload = await aesGcmEncrypt(dek, payloadIv, blob);
    const wrappedDekIv = getRandomBytes(12);
    if (vault.algorithm === 'aes-only') {
        const wrappedDek = await aesGcmEncrypt(vault.kek, wrappedDekIv, dek);
        return { algorithm: 'aes-only', wrappedDek, wrappedDekIv, payload, payloadIv };
    }
    if (!vault.publicKey)
        throw new Error('Unlocked vault is missing public key');
    const kem = pickKem(vault.algorithm);
    const { cipherText, sharedSecret } = kem.encapsulate(vault.publicKey);
    const wrappedDek = await aesGcmEncrypt(sharedSecret, wrappedDekIv, dek);
    return {
        algorithm: vault.algorithm,
        kemCiphertext: cipherText,
        wrappedDek,
        wrappedDekIv,
        payload,
        payloadIv,
    };
}
/** Decrypt an envelope back to plaintext. Requires an unlocked vault. */
export async function decryptBlob(env, vault) {
    let dek;
    if (env.algorithm === 'aes-only') {
        dek = await aesGcmDecrypt(vault.kek, env.wrappedDekIv, env.wrappedDek);
    }
    else {
        if (!vault.privateKey)
            throw new Error('Vault must be unlocked to decrypt');
        if (!env.kemCiphertext)
            throw new Error('Envelope is missing KEM ciphertext');
        const kem = pickKem(env.algorithm);
        const sharedSecret = kem.decapsulate(env.kemCiphertext, vault.privateKey);
        dek = await aesGcmDecrypt(sharedSecret, env.wrappedDekIv, env.wrappedDek);
    }
    return aesGcmDecrypt(dek, env.payloadIv, env.payload);
}
/** Serialize an envelope to a single Uint8Array for storage. */
export function envelopeToBytes(env) {
    // Tag-length-value layout. Versioned at byte 0 so we can evolve later.
    const algoCode = env.algorithm === 'ml-kem-1024' ? 1 : env.algorithm === 'ml-kem-512' ? 2 : 3;
    const parts = [
        new Uint8Array([2, algoCode]), // version, algorithm
        encodeChunk(env.kemCiphertext ?? new Uint8Array()),
        encodeChunk(env.wrappedDek),
        encodeChunk(env.wrappedDekIv),
        encodeChunk(env.payload),
        encodeChunk(env.payloadIv),
    ];
    let total = 0;
    for (const p of parts)
        total += p.length;
    const out = new Uint8Array(total);
    let off = 0;
    for (const p of parts) {
        out.set(p, off);
        off += p.length;
    }
    return out;
}
export function envelopeFromBytes(bytes) {
    if (bytes[0] !== 2)
        throw new Error(`Unsupported envelope version: ${bytes[0]}`);
    const algoCode = bytes[1];
    const algorithm = algoCode === 1 ? 'ml-kem-1024' : algoCode === 2 ? 'ml-kem-512' : 'aes-only';
    let off = 2;
    const next = () => {
        const len = (bytes[off] << 24) | (bytes[off + 1] << 16) | (bytes[off + 2] << 8) | bytes[off + 3];
        off += 4;
        const out = bytes.slice(off, off + len);
        off += len;
        return out;
    };
    const kemCiphertext = next();
    const wrappedDek = next();
    const wrappedDekIv = next();
    const payload = next();
    const payloadIv = next();
    return {
        algorithm,
        kemCiphertext: kemCiphertext.length > 0 ? kemCiphertext : undefined,
        wrappedDek,
        wrappedDekIv,
        payload,
        payloadIv,
    };
}
function encodeChunk(data) {
    const out = new Uint8Array(4 + data.length);
    const len = data.length;
    out[0] = (len >>> 24) & 0xff;
    out[1] = (len >>> 16) & 0xff;
    out[2] = (len >>> 8) & 0xff;
    out[3] = len & 0xff;
    out.set(data, 4);
    return out;
}
