# Plugin-Aktivierungsvertrag

`architecture/plugin-activation.v1.json` legt Zustände und Pflichtbelege des Plugin-Kabels
(ein/aus) je Verbraucher, Host, Plugin und Scope fest. Es ist ein Vertrag mit fixturegeprüftem
Schema. Er schreibt nichts, besitzt keinen Writer und behauptet nicht, dass ein Host oder Verbraucher
Aktivierung heute unterstützt.

## Warum

Ein Anzeige-Flag (etwa eine `plugin_sockets`-Zeile) galt als Wahrheit, wurde nie aus der nativen
Konfiguration zurückgelesen, und ein Plugin ohne Eintrag zählte als eingesteckt. Der Vertrag macht
das unausdrückbar: fehlender Beleg heißt `unknown`.

## Schlüssel und Zustände

Schlüssel: `consumer`, `host`, `plugin_id`, `scope` (`user`, `project`, `local`, `none`), je Dokument
eindeutig. `consumer` ist ein Bezeichner (`^[a-z][a-z0-9_-]{1,40}$`), kein geschlossenes Enum:
`claude`, `codex`, `gemini`, `bach_core` sind dokumentierte Beispiele, ein neuer Verbraucher braucht
keine neue Vertragsversion. Ob ein Verbraucher einen Writer hat, ist Eigenschaft seines Belegs.

| Zustand | Bedeutung | Pflichtbelege |
|---|---|---|
| `plugged` | native Config sagt aktiv, rückgelesen, kein Neustart offen | source, observed_at, config_revision (SHA-256), readback_ref, readback_value |
| `unplugged` | native Config sagt inaktiv, rückgelesen | wie oben |
| `pending_restart` | geschrieben und rückgelesen, Wirkung im laufenden Verbraucher unbelegt | wie oben plus requested_at, runtime_active (null) |
| `unknown` | keine native Quelle, nicht lesbar oder kein Eintrag | reason_code, observed_at |
| `error` | Schreiben/Rücklesen fehlgeschlagen oder Rücklesen widerspricht dem Wunsch | request_id, error_code, last_evidence |

## Regeln und Fehlercodes

- `E_NO_READBACK`: plugged/unplugged brauchen `config_revision` und `readback_ref`. Wunsch ist kein Rücklesen.
- `E_FLAG_ONLY`: ein Flag oder eine Tabelle des Anzeigesystems (`plugin_sockets`) ist keine Quelle.
- `E_DEFAULT_TRUE`: kein Defaultzustand. Fehlende Quelle, Quelle `default`/`absence` oder
  `default_applied: true` müssen zu `unknown` führen, nie zu plugged oder unplugged.
- `E_FOREIGN_HOST_WRITE`: `write.writer_host` muss dem `host` des Eintrags entsprechen; andere Hosts nur Anzeige.
- Schaltablauf in `write.steps`: `plan`, `lock_host_check`, `backup`, `native_write`, `readback`
  (vollständig bei Nicht-error, geordnetes Präfix bei `error`): `E_TOGGLE_ORDER`. `native_write`
  braucht `backup_ref`: `E_NO_BACKUP`.
- `E_MISMATCH_NO_ERROR`: Wunschwert weicht vom Rücklesen ab oder das Rücklesen widerspricht dem
  Zustand, der Zustand ist aber nicht `error`.
- `E_PENDING_RUNTIME`: `pending_restart` hält `runtime_active` null. `E_RUNTIME_NO_REF`: ein
  boolesches `runtime_active` braucht `runtime_ref`.
- `E_ERROR_NO_ROLLBACK`: `error` nach nativem Schreiben braucht `backup_ref`, `rollback_outcome`
  (`restored`, `not_needed`, `failed`) und `last_evidence`.
- `E_UNKNOWN_NEEDS_REASON`, `E_KEY`, `E_ENUM`, `E_TYPE`, `E_STATE`, `E_HASH`, `E_TIME`,
  `E_MISSING_EVIDENCE`, `E_SCHEMA`: Form- und Typfehler; Texte im Vertrag.

Der Prüfer lehnt einen Vertrag ab, der Pflichtbelege, eine verbotene Quelle oder die Schrittfolge
entfernt ("weakens"), und einen, der Hosts, Pfade oder URLs festschreibt ("freezes").

Konfiguration (welcher Verbraucher einen Writer hat, Backup-Ort, Lock-Mechanismus) gehört dem
nutzenden System. Nächste Schritte: Adapter mit nativem Writer, Lock und Backup im nutzenden System
(P3), Anzeige und Schalter im Verbraucher (P4).
