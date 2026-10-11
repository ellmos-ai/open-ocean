# Plugin activation contract

`architecture/plugin-activation.v1.json` fixes the states and mandatory evidence of the plugin
"plug" (on/off) per consumer, host, plugin and scope. It is a contract and a fixture-checked schema.
It performs no write, owns no writer and does not claim that any host or consumer supports
activation today.

## Why

A display flag (such as a `plugin_sockets` row) was treated as truth, never read back from the native
configuration, and a plugin without any entry counted as plugged. This contract makes that
impossible to express: missing evidence means `unknown`.

## Key and states

A record is keyed by `consumer`, `host`, `plugin_id`, `scope` (`user`, `project`, `local`, `none`);
the key is unique per document. `consumer` is an identifier (`^[a-z][a-z0-9_-]{1,40}$`), not a closed
enum: `claude`, `codex`, `gemini`, `bach_core` are documented examples, a new consumer needs no new
contract version. Whether a consumer has a writer is a property of its evidence.

| State | Meaning | Mandatory evidence |
|---|---|---|
| `plugged` | native config says enabled, read back, no restart open | source, observed_at, config_revision (SHA-256), readback_ref, readback_value |
| `unplugged` | native config says disabled, read back | same |
| `pending_restart` | written and read back, effect in the running consumer unproven | same plus requested_at, runtime_active (null) |
| `unknown` | no native source, unreadable, or no entry | reason_code, observed_at |
| `error` | write or read-back failed, or read-back contradicts the request | request_id, error_code, last_evidence |

## Rules and error codes

- `E_NO_READBACK`: plugged/unplugged need `config_revision` and `readback_ref`. A wish is no read-back.
- `E_FLAG_ONLY`: a flag or table of the display system (`plugin_sockets`) is no source.
- `E_DEFAULT_TRUE`: no default state. A missing source, a source of `default`/`absence`, or
  `default_applied: true` must lead to `unknown`, never to plugged or unplugged.
- `E_FOREIGN_HOST_WRITE`: `write.writer_host` must equal the record `host`. Other hosts are display only.
- Toggle sequence in `write.steps`: `plan`, `lock_host_check`, `backup`, `native_write`, `readback`
  (complete for a non-error state, an ordered prefix for `error`): `E_TOGGLE_ORDER`. `native_write`
  needs `backup_ref`: `E_NO_BACKUP`.
- `E_MISMATCH_NO_ERROR`: requested value differs from the read-back, or the read-back contradicts the
  state, but the state is not `error`.
- `E_PENDING_RUNTIME`: `pending_restart` keeps `runtime_active` null. `E_RUNTIME_NO_REF`: a boolean
  `runtime_active` needs `runtime_ref`.
- `E_ERROR_NO_ROLLBACK`: `error` after a native write needs `backup_ref`, `rollback_outcome`
  (`restored`, `not_needed`, `failed`) and `last_evidence`.
- `E_UNKNOWN_NEEDS_REASON`, `E_KEY`, `E_ENUM`, `E_TYPE`, `E_STATE`, `E_HASH`, `E_TIME`,
  `E_MISSING_EVIDENCE`, `E_SCHEMA`: shape and type errors; see the contract for each text.

The checker rejects a contract that removes mandatory evidence, a forbidden source or the step order
("weakens"), and one that freezes hosts, paths or URLs ("freezes").

```
python tools/check_plugin_activation_contract.py            # contract + fixtures
python tools/check_plugin_activation_contract.py --document record.json
```

Configuration (which consumer has a writer, backup location, lock mechanism) belongs to the consuming
system. Next gates: adapter with native writer, lock and backup in the consuming system (P3), consumer
display and switch (P4).
