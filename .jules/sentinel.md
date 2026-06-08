## 2024-05-24 - Rate Limiting DOS & Localization

**Vulnerability:** A DOS memory leak in API Server rate limiter (`gate_requests`) due to unchecked size of `_rate_state` dictionary.
**Learning:** Limiting dictionary size in memory rate limiting controls by clearing the dictionary entirely opens a rate-limiting bypass. You should use a cache TTL mechanism or pop oldest items manually.
**Prevention:** Always pop oldest elements from unbounded dictionaries instead of clearing them when adding a maximum size limit to rate-limit states.
## 2026-04-18 - API Key Bcrypt Hashing Migration
**Vulnerability:** API Keys were hashed using simple SHA-256 with a pepper, and verified using direct database lookups.
**Learning:** Bcrypt hashing relies on generating a unique random salt per hash. Thus, standard direct DB queries `hash == db.hash` do not work anymore. You must loop over active keys in the database and verify each one sequentially.
**Prevention:** When upgrading hash algorithms from un-salted fast hashes to salted slow hashes, always remember to rewrite the lookup logic to iterate over candidates and use the verifying function (e.g., `pwd_context.verify()`) rather than doing an exact database string match.

## 2026-04-18 - Subprocess Command Injection Prevention
**Vulnerability:** Subprocesses generating Git commits used string formatting to construct commit messages and passed them to `git commit -m`.
**Learning:** While `shell=False` protects against basic command injection (e.g. `&& rm -rf /`), parameter injection or argument confusion is still possible if untrusted input slips in.
**Prevention:** Use standard input streams for passing untrusted strings as data rather than command arguments. In the context of `git commit`, this means using `-F -` and passing the message via `subprocess.run(..., input=message_string)`.
## 2026-04-22 - [Sentinel] DoS Prevention in Rate Limiting\n**Vulnerability:** Memory Exhaustion DoS in gate_requests middleware\n**Learning:** In api_server.py, the rate limiting middleware used a defaultdict to store request times per IP. Without a maximum size limit and periodic eviction, an attacker could spoof thousands of IPs or generate unique origins to unbounded increase memory usage, leading to a server crash.\n**Prevention:** Always set an explicit size boundary (e.g. 10000 items) when tracking state per client in memory. Evict stale entries, and forcefully clear state if it exceeds safety limits, to guarantee stable memory footprints during abuse.

## 2026-04-22 - X-Forwarded-For IP Spoofing Prevention
**Vulnerability:** The `_get_client_ip` function parsed the leftmost IP from the `X-Forwarded-For` header. Because clients can easily spoof this header, an attacker could set it to a trusted internal IP (like `127.0.0.1`), effectively bypassing `_is_trusted_client_ip` authorization checks intended only for internal services.
**Learning:** In scenarios behind trusted reverse proxies (like Nginx), the proxy *appends* the actual client IP to the `X-Forwarded-For` chain. The leftmost IP is always untrusted user input and can be anything.
**Prevention:** Always extract the rightmost IP address from the `X-Forwarded-For` header (or iterate right-to-left stopping at the first untrusted proxy) to ensure you are validating the true connection IP, preventing IP spoofing vulnerabilities.

## 2026-05-01 - API Key Bcrypt DoS & Missing O(1) Lookup
**Vulnerability:** API keys were hashed using bcrypt before DB lookup, causing 100% DB misses due to random salt, breaking authentication. Furthermore, doing bcrypt on every request allows an unauthenticated attacker to cause a CPU exhaustion DoS.
**Learning:** When verifying passwords or API keys, never hash the incoming key with bcrypt and query the database for a match. You must look up the record first (e.g. by ID) and verify the password against the retrieved hash using the context manager.
**Prevention:** Switch to a deterministic hash (like SHA-256 with a pepper) for O(1) database lookups. Provide an O(1) ID lookup route first (e.g. embedding the ID in the token string itself ) and fall back to the deterministic hash if the ID lookup fails.

## 2026-05-01 - API Key Bcrypt DoS & Missing O(1) Lookup
**Vulnerability:** API keys were hashed using bcrypt before DB lookup, causing 100% DB misses due to random salt, breaking authentication. Furthermore, doing bcrypt on every request allows an unauthenticated attacker to cause a CPU exhaustion DoS.
**Learning:** When verifying passwords or API keys, never hash the incoming key with bcrypt and query the database for a match. You must look up the record first (e.g. by ID) and verify the password against the retrieved hash using the context manager.
**Prevention:** Switch to a deterministic hash (like SHA-256 with a pepper) for O(1) database lookups. Provide an O(1) ID lookup route first (e.g. embedding the ID in the token string itself) and fall back to the deterministic hash if the ID lookup fails.
## $(date +%Y-%m-%d) - Subprocess Command Injection Prevention

**Vulnerability:** Subprocesses generating Git commits used string formatting to construct commit messages and passed them to `git commit -m`.
**Learning:** While `shell=False` protects against basic command injection (e.g. `&& rm -rf /`), parameter injection or argument confusion is still possible if untrusted input slips in.
**Prevention:** Use standard input streams for passing untrusted strings as data rather than command arguments. In the context of `git commit`, this means using `-F -` and passing the message via `subprocess.run(..., input=message_string)`.

## 2026-05-05 - Admin Authorization Bypass in Global Config Endpoints
**Vulnerability:** The `/config` and `/config/models-dir` POST endpoints allowed any authenticated user to change global system configurations, including `modelsDir` and `localBridgeUrl`, potentially leading to Path Traversal or Server-Side Request Forgery (SSRF).
**Learning:** Endpoints that modify global or system-level state must enforce authorization checks (e.g., verifying `user.is_admin`) in addition to general authentication checks, to prevent privilege escalation.
**Prevention:** Always verify that the authenticated principal has the appropriate role (`is_admin`) before allowing them to mutate global state or sensitive system settings.

## 2026-05-05 - Timing Attack in Login Endpoint
**Vulnerability:** The `/auth/login` endpoint returned immediately with a 401 error if a username was not found in the database, allowing an attacker to determine if a user exists based on the response time (timing attack).
**Learning:** During authentication flows, cryptographic operations (like password hashing) take a significant and measurable amount of time. If these are skipped when a user doesn't exist, the discrepancy leaks information about valid usernames.
**Prevention:** Always use a dummy verification method (e.g., `pwd_context.dummy_verify()`) when a user is not found to simulate the time taken by a real password verification, ensuring consistent response times regardless of whether the user exists or not.

## $(date +%Y-%m-%d) - Exception Information Leakage Prevention
**Vulnerability:** Subprocesses generating errors (like `ffmpeg`) raised a `RuntimeError` that directly included the command's full `stderr` output.
**Learning:** Returning raw command errors or stack traces to callers (especially web API endpoints) can leak sensitive internal paths, library versions, or environment details to an attacker, facilitating further exploitation.
**Prevention:** To prevent information leakage, log the full error output internally (e.g., using Python's `logging` module) and return a generic, sanitized error message to the caller.
## 2026-05-06 - Admin Authorization Bypass in Global Config Endpoints
**Vulnerability:** The `/config` and `/config/models-dir` POST endpoints allowed any authenticated non-user principal (like API keys) to change global system configurations, including `modelsDir` and `localBridgeUrl`, potentially leading to Path Traversal or Server-Side Request Forgery (SSRF). The flawed logic was `if principal.get("kind") == "user" and not principal["user"].is_admin:`, which returned False and bypassed the check when `kind` was not "user".
**Learning:** Endpoints that modify global or system-level state must enforce authorization checks securely. Checking `kind == "user"` with an `and` statement incorrectly allowed bypassing for other principal kinds.
**Prevention:** Always verify that the authenticated principal is specifically a user and has the appropriate role (`is_admin`) using `if principal.get("kind") != "user" or not principal["user"].is_admin:` before allowing them to mutate global state or sensitive system settings.

## 2026-05-06- Subprocess Command Injection in Git Commits
**Vulnerability:** Subprocesses generating Git commits used string formatting to construct commit messages and passed them to `git commit -m` in `vaultwares_agentciation/omx_integration/omx_worker.py` and `vaultwares_agentciation/omx_integration/demo/run_demo.py`.
**Learning:** While `shell=False` protects against basic command injection (e.g. `&& rm -rf /`), parameter injection or argument confusion is still possible if untrusted input slips in.
**Prevention:** Use standard input streams for passing untrusted strings as data rather than command arguments. In the context of `git commit`, this means using `-F -` and passing the message via `subprocess.run(..., input=commit_msg)`.

## 2026-05-06 - Hardcoded Database Credentials
**Vulnerability:** A fallback database connection URL in `api_server.py` included hardcoded default PostgreSQL credentials (`postgres:postgres`).
**Learning:** Even fallback or local development URLs pose a risk if they leak expected credential structures or accidentally get exposed/deployed to environments where they might be active. Furthermore, when fixing these issues by substituting a safer default (like `localhost`), the original database engine format must be preserved (e.g., `postgres://` rather than `sqlite://`) to avoid breaking ORM models that depend on engine-specific types (like `JSONField`).
**Prevention:** Remove hardcoded credentials from configuration defaults, requiring the user to explicitly define them via environment variables, or use safe, credential-less localhost defaults while strictly preserving the expected database engine type to maintain application compatibility.
