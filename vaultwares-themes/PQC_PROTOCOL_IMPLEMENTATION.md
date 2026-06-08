# PQC Protocol Implementation Guide

## 1. Overview

The internal VaultWares media container format (.vault) represents a post-quantum secured envelope meant to wrap standard media files (such as MP4, MKV, WebM) with end-to-end encryption. This document standardizes the internal PQC implementation methodologies used across VaultWares projects, specifically targeting media and file container streaming.

## 2. Cryptographic Primitives

We rely on the following algorithms provided through standardized NIST post-quantum parameters and robust authenticated encryption standard pipelines:

- **Asymmetric Key Encapsulation Mechanism (KEM):** ML-KEM-768 (Kyber768). Used strictly for securing the symmetric session keys between the sender and the recipient.
- **Digital Signatures:** ML-DSA-65 (Dilithium3). Used optionally by the sender to sign the encapsulated payload and the container header, ensuring authorship and authenticity.
- **Symmetric Authenticated Encryption with Associated Data (AEAD):** ChaCha20-Poly1305. Chosen for high-throughput streaming capabilities over media chunks without hardware-bound bottlenecks (such as AES-NI dependencies), ensuring strong performance for clients buffering video chunks.

## 3. Container Structure (.vault)

The internal .vault streaming structure replaces massive full-file in-memory block encryption. The structure sequentially embeds data over a defined block map. All dynamically sized fields are prepended with a 4-byte big-endian unsigned integer (length prefix).

### Layout

1. **Magic Bytes (8 bytes):** "VAULTV1\0". Validates parsing compatibility.
2. **KEM Ciphertext:** Used to securely derive the symmetric ChaCha20-Poly1305 key (\_pack_field(kem_ciphertext)).
3. **Sender Signature Public Key:** The ML-DSA-65 public key belonging to the original creator (optional, empty if unsigned).
4. **Signature Payload:** The signature verifying the concatenated kem_ciphertext + manifest_payload.
5. **Manifest Payload:** Contains the .vault file JSON structure, describing original content format, trickplay maps (thumbnails for scrubbing), and original video duration, encrypted via ChaCha20-Poly1305. Stored alongside its generated authentication tag and dynamic nonce.
6. **Data Chunks:** The actual encrypted media blocks. To support HTTP range streaming and local server buffering, files chunk typically at **4MB limits**. Each block has its own dedicated ChaCha20-Poly1305 tag and nonce appended before ciphertext to guarantee block integrity.

## 4. How To Implement in New VaultWares Repos

When you are extracting or utilizing the container format inside other VaultWares client applications, strictly enforce the following protocol pipeline:

### A. Wrapping the Data (Writing)

1. Initialize the PQCEncryptor mapping via PQCEncryptor.from_kem_public_key(recipient_pk).
2. Generate the container Header using "VAULTV1\0".
3. Wrap your custom JSON manifest using PQCEncryptor.encrypt(). Ensure you store dynamically sized components using a consistent struct packer (e.g., struct.pack(">I", length)).
4. For media streaming, read the inbound standard format file in 4 _1024_ (4MB) loops. For each chunk:
    - Call encrypt(chunk).
    - Pack the result once, tag, and ciphertext directly into the .vault file handle.

### B. Reading the Data (Streaming)

1. Read the initial 8 bytes to verify VAULTV1\0.
2. Read the kem_ciphertext mapping. Initialize PQCEncryptor.from_kem_private_key().
3. Read the sig_public_key and signature blocks. Verify if needed utilizing PQCSigner.verify().
4. Parse the JSON manifest to define headers for the internal target output (Mimetype format resolving).
5. Expose an iterable or generator function iter_chunks() to progressively parse length-prefixed
   once, ag, and ciphertext loops calling decrypt(). The resulting yielded output should feed directly into local media proxies handling byte-ranges for video tag consumption.

## 5. Critical Guidelines

- **Always yield chunks.** Never
  ead() more than 4MB into memory at any given time. Encrypted video buffers require high efficiency.
- Re-use the existing primitives interface whenever possible. Avoid directly hitting raw cryptography interfaces without wrapper classes providing sanity checking padding and nonces constraints.
- When generating keys dynamically for anonymous sender loops, drop KEM public structures securely and aggressively destroy associated memory.
