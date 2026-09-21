# OCEAN-Inspektion

`ocean inspect` beantwortet eine begrenzte Frage: Für welche Funktionen einer quellengeprüften
System-Resolution liegt auf der erwarteten Instanz und dem erwarteten Host aktuelle native Evidenz
vor?

## Eigentum und Naht

OCEAN verantwortet CLI-Eingaben, die Prüfung des installierten Anbieters, die Ergebnishülle und
Exitcodes. System Explorer verantwortet Resolution-Import, Belegschemas, Ed25519-Prüfung,
Vertrauensregeln, Komponentenidentität und Coverage-Verdicts. OCEAN scannt den Host nicht und baut
diese Regeln nicht nach.

Das Full-Dev-Rezept nennt die Kompositionsrolle `module:software-endpoint-registry`. Das exakte
OCEAN-Binding löst diesen Alias auf `ellmos-ai/system-explorer` am Commit
`ec50c92319ba8fc262d695b86818fc85666feff7` auf: Anbieter-ID `system-explorer`, Paket
`system_explorer`, CLI `system-explorer`, Version `0.4.0`. Der Alias ist kein zweiter fachlicher
Eigentümer.

## Rein lesender Ablauf

Der Befehl benötigt einen installierten OCEAN-Workspace, eine System-Explorer-Resolution, null oder
mehr signierte Actual-Self-Belege, einen Trust Store mit unabhängigem SHA-256-Pin, die erwarteten
Instanz- und Host-IDs sowie optional einen ausdrücklichen Auswertungszeitpunkt. OCEAN prüft
Installationstransaktion, Binding, sauberen Anbieter-Checkout, Origin, Commit, Manifest, Paket, CLI
und Version. Danach ruft es die nativen Funktionen `import_resolution`,
`load_receipt_trust_store`, `import_actual_self_receipt` und `coverage_report` in einer neuen
temporären SQLite-Datenbank auf. Der temporäre Speicher wird anschließend entfernt. Ziel-Workspace
und Evidenzeingaben bleiben unverändert.

Alle Belege werden in einer gemeinsamen Transaktion importiert. Ein einziger ungültiger,
abgelaufener, gefälschter, hostfremder, anbieterfremder oder unbekannte Felder enthaltender Beleg
weist die gesamte Operation ab; es gibt keinen Teilerfolgsbericht.

## Ausgabevertrag

Die JSON-Hülle verwendet `ellmos.open-ocean-inspect.v1` und enthält Auswertungszeit, erwarteten
Scope, Belege zum Anbieter-Pin, SHA-256-Hashes aller öffentlichen Eingaben und das native
Coverage-Ergebnis. Exit `0` bedeutet gültig ohne Pflichtlücken, Exit `1` gültig mit Pflichtlücken
und Exit `2` abgewiesen.

Native Coverage-Datensätze des System Explorers enthalten Einfügezeitpunkte des Stores. Diese sind
flüchtige Buchhaltung und keine Evidenzzeit. Für eine deterministische Präsentation entfernt OCEAN
ausschließlich `created_at` an diesen Positionen:

- `functions[].function.created_at`
- `functions[].carriers[].created_at`
- `functions[].desired[].created_at`
- `functions[].actual[].created_at`

Die Hülle nennt diese Auslassungen und ihre Anzahl. OCEAN entfernt keine gleichnamigen
Metadatenfelder rekursiv. `observed_at`, `effective_at`, `expires_at`, signierte Belegfelder,
Evidenz-IDs und -Bezüge, Anbieteridentität, Scopes, Verdicts und Lückenklassen bleiben erhalten.

## Abnahmegrenze

Die Abnahme verwendet einen echten sauberen Checkout des gepinnten Anbieters und ein temporäres
Ed25519-Schlüsselpaar. Die Tests decken gültige Evidenz, Pflichtlücken, Ablauf, Signaturfehler,
falschen Host, falschen Anbieter, unbekannte Felder, einen falschen Trust-Pin,
Anbieterversion-Drift und eine gemischte gültige/ungültige Belegmenge ab. Zwei Läufe mit identischen
Eingaben und Auswertungszeitpunkt müssen nach der dokumentierten Präsentationsauslassung
byteidentisches kanonisches JSON liefern. BACH-Datenbank, Zielscanner, Plugins,
Credential-Aktualisierung, Netzwerkdienste und Live-Installation bleiben unberührt.
