# vaultwares-api Tasks

## Completed

- [x] PostgreSQL Migration to OVH (2026-06-11): Started migration from Clopeux-Desktop local PG18 to vps-ovhcloud 100.67.25.118. Dumped local vaultwares/promking databases, restored PG16-compatible SQL snapshots into remote apidb cluster on port 5433. Verified /healthz db=up. Promking row counts matched. Note: local API continued writing during migration, so final cutover needs write pause and final snapshot.
- [x] VaultWares API Cutover to OVH (2026-06-11): Cut over local VaultWares input tracker to OVH VPS API over Tailscale. Updated OVH API env with telemetry key, bound on 0.0.0.0:9001, restricted direct 9001 ingress to workstation over tailscale0. Restarted vaultwares-api service. Updated Greencloud dnsmasq exact-host record for api.vaultwares.ca to 100.67.25.118. Paused/restarted VaultWares-InputTracker with new VW_API_URL=http://100.67.25.118:9001. Verified telemetry batches reached OVH Postgres.
- [x] WebAuthn Passkey Admin Auth (2026-06-12): Added `webauthn` dependency, created `WebAuthnCredential` DB model in `db.py`, and implemented `/auth/register` and `/auth/login` options/verify endpoints in `api_server.py`. Added corresponding UI controls to the PKT/FXV admin portals in `shared-tube`.

## In Progress

(none)

## Backlog

- [ ] Final PostgreSQL migration cutover with write pause and final snapshot
- [ ] Verify all dependent services pointing to OVH API
- [ ] Implement write/update operations for taxonomies (bulk move/rename/gender-update) in the FastAPI router and admin portals.

