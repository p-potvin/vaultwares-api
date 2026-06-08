# Consumer Update Roadmap

This cleanup intentionally updates only compatibility pointers in consumer repos.
A full style/token migration should happen later as its own pass.

## Future Full Update

For each consumer repo:

1. Update the `vault-themes` submodule.
2. Replace local duplicated style guidance with managed pointers.
3. Replace hardcoded VaultWares colors/spacing/fonts with tokens from
   `vault-themes/brand/tokens/`.
4. Replace external logo URLs with local `vault-themes/assets/` references where
   deployment shape allows it.
5. Review bilingual copy for EN/QC parity.
6. Run the consumer repo's own lint/typecheck/build/test flow.

## Known Consumers To Revisit

- `automation-suite`
- `no-more-groceries`
- `usd-playground`
- `vault-central`
- `vault-explorer`
- `vault-flows`
- `vault-player`
- `vault-video-enhancer`
- `vaultwares-cli`
- `vaultwares-pipelines`
- `vaultwares-website`

Also check repos that have `.gitmodules` entries but may not have initialized
`vault-themes` locally:

- `cultural-rhythm`
- `deconstructed-website-a-la-mode`
- `dispatch-wares`
- `realtime-stt`
- `traffic-pulse`
- `vaultwares-identity-manager`
- `windows-customizer`

## Not In This Cleanup

- No broad component rewrites in consumers.
- No consumer-specific visual redesigns.
- No package dependency updates unless needed for instruction pointer
  compatibility.
