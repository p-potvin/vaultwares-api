# Security primitives

Zero-knowledge encryption module shared across all VaultWares projects.

## What's here

- **`crypto-vault.ts`** — ML-KEM + AES-256-GCM envelope encryption, Argon2id PIN derivation. Implements the [zero-knowledge encryption standard](https://github.com/p-potvin/vaultwares-docs/blob/main/security/zero-knowledge-encryption-standard.mdx) (Tier 1 SoT).
- **`crypto-vault.test.ts`** — vitest unit suite covering ML-KEM-1024, ML-KEM-512, AES-only fallback, wrong-PIN rejection, lossless envelope (de)serialization.

## Why this lives in vault-themes

Per VaultWares philosophy, vault-themes is the cross-cutting submodule for company-wide primitives. Encryption primitives are normative across every project (per the Tier 1 standard) and benefit from a single vetted implementation. Importing projects pull this submodule and import the source file directly.

## Consumer requirements

The module imports from `@noble/post-quantum` and `@noble/hashes`. Consumer projects must declare these as their own dependencies — vault-themes does not ship a `package.json` since it is consumed as source, not as an npm package.

```json
"dependencies": {
  "@noble/post-quantum": "^0.6.1",
  "@noble/hashes": "^2.2.0"
}
```

## Importing

From a consumer project (e.g. vault-central) where vault-themes is a git submodule at the repo root:

```ts
import { setupVault, unlockVault, encryptBlobWithUnlocked, decryptBlob } from '../vault-themes/security/crypto-vault';
```

Adjust the relative path to your project layout. Module is plain ESM TypeScript with no framework dependencies.

## Default parameters

- ML-KEM-1024 (NIST level 5) — default for new vaults
- ML-KEM-512 (NIST level 1) — only when decapsulation latency degrades user-perceived performance
- AES-256-GCM only — fallback when ML-KEM cannot be implemented in the runtime; consumer project MUST add `NOTE.encryption.md` per the standard

Argon2id parameters: `t=3, m=64 MiB, p=1, dkLen=32`.

## Updating

When the standard changes, this module is updated, then consumers fast-forward their submodule pointer. Migration paths are the consumer's responsibility — the module maintains an `algorithm` discriminator on every envelope so consumers can detect and migrate older payloads.
