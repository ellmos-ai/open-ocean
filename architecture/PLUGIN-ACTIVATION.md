# Plugin activation contract

`architecture/plugin-activation.v1.json` fixes the states and mandatory evidence of the plugin state
(on/off) per consumer, host, plugin and scope. It is a contract and a fixture-checked schema. It
performs no write, owns no writer and does not claim that any host or consumer supports activation
today.

## Why

A display flag (such as a `plugin_sockets` row) was treated as truth, never read back from the native
configuration, and a plugin without any entry counted as plugged. This contract makes that
impossible to express: missing evidence means `unknown`.

## Record shape

A document is `{"schema": "ellmos.open-ocean-plugin-activation-record.v1", "records": [...]}`. A record
holds `consumer`, `host`, `plugin_id`, `scope` (`user`, `project`, `local`, `none`), `state`,
`evidence`, optionally `write` and `extensions` (an object the checker never interprets). Unknown
fields are rejected. The key (consumer, host, plugin_id, scope) is unique per document.

- `consumer` is an ASCII identifier (`^[a-z][a-z0-9_-]{1,40}$`), not a closed enum: `claude`, `codex`,
  `gemini`, `bach_core` are documented examples; a new consumer needs no new contract version. Whether
  a consumer has a writer is a property of its evidence.
- `host` is the lowercase ASCII host identifier (`^[a-z0-9][a-z0-9._-]{0,62}$`); consumers lowercase a
  host name before they compare or store it. `plugin_id` is `^[A-Za-z0-9][A-Za-z0-9._@/-]{0,120}$`.
  Unicode look-alikes are rejected.
- Text fields (references, ids, codes) are non-empty strings without surrounding whitespace or control
  characters; flags are exactly `true` or `false`.

| State | Meaning | Mandatory evidence |
|---|---|---|
| `plugged` | native config says enabled, read back after any write, no restart open | source, observed_at, config_revision, readback_ref, readback_at, readback_sha256, readback_value |
| `unplugged` | native config says disabled, read back | same |
| `pending_restart` | written (complete `write` block) and read back, effect in the running consumer unproven | same plus requested_at, runtime_active (null) |
| `unknown` | no native source, unreadable, no entry, or a read-back not bound to the write | reason_code, observed_at |
| `error` | write or read-back failed, or the read-back contradicts the request | request_id, error_code, last_evidence, phase (`read` or `write`) |

## Rules and error codes

Every code has exactly one fixture `tests/fixtures/plugin_activation/neg_<code>.json` that raises exactly it.

- `E_NO_READBACK`, `E_REVISION_MISMATCH`, `E_STALE_READBACK`: `config_revision` must equal
  `readback_sha256`, the hash of the content `readback_ref` points to, and `readback_at` must not lie
  before `requested_at` or `write.native_write_at`. A stale or unbound read-back is not evidence; the
  consumer shows `unknown`.
- `E_FLAG_ONLY`: a flag or table of the display system (`plugin_sockets`) is no source.
- `E_DEFAULT_TRUE`: no default state. A missing source, a source `default`/`absence`, or
  `default_applied: true` must lead to `unknown`, never to plugged or unplugged.
- `E_FOREIGN_HOST_WRITE`: `write.writer_host` must equal the record `host`; other hosts are display only.
- `write` block: `requested_value`, `writer_host`, `steps`, `reached_step`, and after `native_write`
  also `backup_ref` and `native_write_at`; `rollback_outcome` only on `error`. `steps` is the ordered
  sequence `plan`, `lock_host_check`, `backup`, `native_write`, `readback` (complete unless the state is
  `error`, then a non-empty prefix): `E_TOGGLE_ORDER`. `reached_step` is the last entry: `E_REACHED_STEP`.
  `E_NO_BACKUP` without `backup_ref`. `pending_restart` and an `error` in phase `write` need the block:
  `E_WRITE_REQUIRED`.
- `E_MISMATCH_NO_ERROR`: requested value differs from the read-back, or the read-back contradicts the
  state, but the state is not `error`.
- `E_PENDING_RUNTIME`: `pending_restart` keeps `runtime_active` null. `E_RUNTIME_NO_REF`: a boolean
  `runtime_active` needs `runtime_ref`.
- `E_ERROR_NO_ROLLBACK`: `error` after a native write needs `rollback_outcome` (`restored`,
  `not_needed`, `failed`).
- `E_UNKNOWN_NEEDS_REASON`, `E_KEY`, `E_ENUM`, `E_TYPE`, `E_STATE`, `E_UNKNOWN_FIELD`, `E_HASH`,
  `E_TIME`, `E_MISSING_EVIDENCE`, `E_SCHEMA`: shape and type errors; see the contract for each text.

The normative contract sections (states, enums, patterns, field lists, rules, error codes) are pinned
by SHA-256 in the checker: removing, reversing, loosening or rewording any of them is reported as
"weakens" and is a new contract version. A host, path or URL anywhere in the contract is reported as
"freezes".

```
python tools/check_plugin_activation_contract.py            # contract + fixtures
python tools/check_plugin_activation_contract.py --document record.json
```

Configuration (which consumer has a writer, backup location, lock mechanism, how old a read-back may
be) belongs to the consuming system. Next gates: adapter with native writer, lock and backup in the
consuming system (P3), consumer display and switch (P4).
