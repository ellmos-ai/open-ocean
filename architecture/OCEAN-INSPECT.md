# OCEAN inspect

`ocean inspect` answers one bounded question: which functions required by a source-verified system
resolution have current native evidence on the expected instance and host?

## Ownership and seam

OCEAN owns CLI input, installed-provider verification, the result envelope and exit codes. System
Explorer owns resolution import, receipt schemas, Ed25519 verification, trust policy, component
identity and coverage verdicts. OCEAN does not scan the host and does not reproduce those rules.

The Full Dev recipe calls the composition role `module:software-endpoint-registry`. Its exact OCEAN
binding resolves that alias to `ellmos-ai/system-explorer` at commit
`ec50c92319ba8fc262d695b86818fc85666feff7`: provider ID `system-explorer`, package
`system_explorer`, CLI `system-explorer`, version `0.4.0`. The alias is not a second provider owner.

## Read-only operation

The command requires an installed OCEAN workspace, a System Explorer resolution, zero or more
signed Actual-Self receipts, a trust store plus its independent SHA-256 pin, the expected instance
and host IDs, and optionally an explicit evaluation time. OCEAN verifies the install transaction,
binding, clean provider checkout, origin, commit, manifest, package, CLI and version. It then calls
the native `import_resolution`, `load_receipt_trust_store`, `import_actual_self_receipt` and
`coverage_report` functions in a new temporary SQLite store. The temporary store is deleted after
the call. The target workspace and input evidence remain unchanged.

Receipt imports share one transaction. A single invalid, expired, forged, wrong-host,
wrong-provider or unknown-field receipt rejects the whole operation; no partial success report is
returned.

## Output contract

The JSON envelope uses `ellmos.open-ocean-inspect.v1` and contains the evaluation time, expected
scope, provider pin evidence, SHA-256 hashes of all public inputs, and the native coverage result.
Exit `0` means valid without required gaps, exit `1` means valid with required gaps, and exit `2`
means rejected.

System Explorer's native coverage records include Store insertion timestamps. They are volatile
bookkeeping, not evidence time. For deterministic presentation OCEAN removes only `created_at` at:

- `functions[].function.created_at`
- `functions[].carriers[].created_at`
- `functions[].desired[].created_at`
- `functions[].actual[].created_at`

The envelope lists these omissions and their count. OCEAN does not recursively remove similarly
named metadata. It preserves `observed_at`, `effective_at`, `expires_at`, signed receipt content,
evidence IDs and links, provider identity, scopes, verdicts and gap classifications.

## Acceptance boundary

Acceptance uses a real clean checkout of the pinned provider and an ephemeral Ed25519 key pair.
Tests cover valid evidence, required gaps, expiry, signature failure, wrong host, wrong provider,
unknown fields, a wrong trust pin, provider-version mismatch and a mixed valid/invalid receipt set.
Two runs with identical inputs and evaluation time must produce byte-identical canonical JSON after
the documented presentation omission. No BACH database, target scanner, plugin, credential refresh,
network service or live installation is involved.
