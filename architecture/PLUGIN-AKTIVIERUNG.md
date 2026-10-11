# Plugin-Aktivierungsvertrag

`architecture/plugin-activation.v1.json` legt Zustände und Pflichtbelege des Plugin-Zustands
(ein/aus) je Verbraucher, Host, Plugin und Scope fest. Es ist ein Vertrag mit fixturegeprüftem
Schema. Er schreibt nichts, besitzt keinen Writer und behauptet nicht, dass ein Host oder Verbraucher
Aktivierung heute unterstützt.

## Warum

Ein Anzeige-Flag (etwa eine `plugin_sockets`-Zeile) galt als Wahrheit, wurde nie aus der nativen
Konfiguration zurückgelesen, und ein Plugin ohne Eintrag zählte als eingesteckt. Der Vertrag macht
das unausdrückbar: fehlender Beleg heißt `unknown`.

## Aufbau eines Eintrags

Ein Dokument ist `{"schema": "ellmos.open-ocean-plugin-activation-record.v1", "records": [...]}`. Ein
Eintrag hat `consumer`, `host`, `plugin_id`, `scope` (`user`, `project`, `local`, `none`), `state`,
`evidence`, optional `write` und `extensions` (ein Objekt, das der Prüfer nie auswertet). Unbekannte
Felder werden abgelehnt. Der Schlüssel (consumer, host, plugin_id, scope) ist je Dokument eindeutig.

- `consumer` ist ein ASCII-Bezeichner (`^[a-z][a-z0-9_-]{1,40}$`), kein geschlossenes Enum: `claude`,
  `codex`, `gemini`, `bach_core` sind dokumentierte Beispiele, ein neuer Verbraucher braucht keine
  neue Vertragsversion. Ob ein Verbraucher einen Writer hat, ist Eigenschaft seines Belegs.
- `host` ist der kleingeschriebene ASCII-Hostbezeichner (`^[a-z0-9][a-z0-9._-]{0,62}$`); Verbraucher
  schreiben einen Hostnamen klein, bevor sie vergleichen oder speichern. `plugin_id` ist
  `^[A-Za-z0-9][A-Za-z0-9._@/-]{0,120}$`. Unicode-Lookalikes werden abgelehnt.
- Textfelder (Referenzen, Kennungen, Codes) sind nichtleere Zeichenketten ohne umgebenden Leerraum
  und ohne Steuerzeichen; Flags sind genau `true` oder `false`.

| Zustand | Bedeutung | Pflichtbelege |
|---|---|---|
| `plugged` | native Config sagt aktiv, nach jedem Schreiben rückgelesen, kein Neustart offen | source, observed_at, config_revision, readback_ref, readback_at, readback_sha256, readback_value |
| `unplugged` | native Config sagt inaktiv, rückgelesen | wie oben |
| `pending_restart` | geschrieben (vollständiger `write`-Block) und rückgelesen, Wirkung im laufenden Verbraucher unbelegt | wie oben plus requested_at, runtime_active (null) |
| `unknown` | keine native Quelle, nicht lesbar, kein Eintrag oder Rücklesen nicht an das Schreiben gebunden | reason_code, observed_at |
| `error` | Schreiben/Rücklesen fehlgeschlagen oder Rücklesen widerspricht dem Wunsch | request_id, error_code, last_evidence, phase (`read` oder `write`) |

## Regeln und Fehlercodes

Jeder Code hat genau ein Fixture `tests/fixtures/plugin_activation/neg_<code>.json`, das genau ihn auslöst.

- `E_NO_READBACK`, `E_REVISION_MISMATCH`, `E_STALE_READBACK`: `config_revision` muss `readback_sha256`
  entsprechen, dem Hash des Inhalts, auf den `readback_ref` zeigt, und `readback_at` darf nicht vor
  `requested_at` oder `write.native_write_at` liegen. Ein veraltetes oder ungebundenes Rücklesen ist
  kein Beleg; der Verbraucher zeigt `unknown`.
- `E_FLAG_ONLY`: ein Flag oder eine Tabelle des Anzeigesystems (`plugin_sockets`) ist keine Quelle.
- `E_DEFAULT_TRUE`: kein Defaultzustand. Fehlende Quelle, Quelle `default`/`absence` oder
  `default_applied: true` müssen zu `unknown` führen, nie zu plugged oder unplugged.
- `E_FOREIGN_HOST_WRITE`: `write.writer_host` muss dem `host` des Eintrags entsprechen; andere Hosts nur Anzeige.
- `write`-Block: `requested_value`, `writer_host`, `steps`, `reached_step`, nach `native_write` zusätzlich
  `backup_ref` und `native_write_at`; `rollback_outcome` nur bei `error`. `steps` ist die geordnete Folge
  `plan`, `lock_host_check`, `backup`, `native_write`, `readback` (vollständig, außer bei `error`: dann
  ein nichtleeres Präfix): `E_TOGGLE_ORDER`. `reached_step` ist der letzte Eintrag: `E_REACHED_STEP`.
  `E_NO_BACKUP` ohne `backup_ref`. `pending_restart` und ein `error` in Phase `write` brauchen den
  Block: `E_WRITE_REQUIRED`.
- `E_MISMATCH_NO_ERROR`: Wunschwert weicht vom Rücklesen ab oder das Rücklesen widerspricht dem
  Zustand, der Zustand ist aber nicht `error`.
- `E_PENDING_RUNTIME`: `pending_restart` hält `runtime_active` null. `E_RUNTIME_NO_REF`: ein
  boolesches `runtime_active` braucht `runtime_ref`.
- `E_ERROR_NO_ROLLBACK`: `error` nach nativem Schreiben braucht `rollback_outcome` (`restored`,
  `not_needed`, `failed`).
- `E_UNKNOWN_NEEDS_REASON`, `E_KEY`, `E_ENUM`, `E_TYPE`, `E_STATE`, `E_UNKNOWN_FIELD`, `E_HASH`,
  `E_TIME`, `E_MISSING_EVIDENCE`, `E_SCHEMA`: Form- und Typfehler; Texte im Vertrag.

Die normativen Vertragsabschnitte (Zustände, Enums, Muster, Feldlisten, Regeln, Fehlercodes) sind im
Prüfer per SHA-256 festgeschrieben: Entfernen, Umkehren, Lockern oder Umformulieren wird als
"weakens" gemeldet und ist eine neue Vertragsversion. Ein Host, Pfad oder eine URL irgendwo im Vertrag
wird als "freezes" gemeldet.

```
python tools/check_plugin_activation_contract.py            # Vertrag + Fixtures
python tools/check_plugin_activation_contract.py --document record.json
```

Konfiguration (welcher Verbraucher einen Writer hat, Backup-Ort, Lock-Mechanismus, wie alt ein
Rücklesen sein darf) gehört dem nutzenden System. Nächste Schritte: Adapter mit nativem Writer, Lock
und Backup im nutzenden System (P3), Anzeige und Schalter im Verbraucher (P4).
