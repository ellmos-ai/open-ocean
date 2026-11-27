# Verbindliche Terminologie: Ressourcen, Modelle & Agenten (`open-ocean` / `bach` / `ellmos-system-gui`)

> **Status:** Verbindlicher Begriffs- und Kongruenzvertrag (`architecture/terminology-congruence.v1.json`, Entscheid `2026-11-27`, Ticket `T-20261127-020900001`, BACH `#4447`).
> **Zweck:** Konzepte prägen die Weiterentwicklung. Historisch überlagerte Begriffe (`Fackel`, `Slot` / `Steckplatz`, dreifach belegter `Sockel`) begünstigen ungewollte Rollbacks auf aufgegebene Konzepte (starre Modell-Slots, alte PC-zu-PC-Bridge-Fackel). Dieses Glossar ordnet **jedem Konzept genau einen verbindlichen Begriff** zu — identisch über Architektur, Dokumentation und GUI.

---

## 1. Kernprinzip: Zweistufiges Claiming ohne starre Modell-Slots

Seit dem Architekturentscheid `2026-10-24` gibt es **keine starren Modell-Slots mehr**. Agenten tragen ihre **Modellbindung** direkt (`model` + `model_fallbacks`). Zur Laufzeit greift ein streng zweistufiges Verfahren:

1. **Stufe 1 — RAM-Zuteilung** *(Physischer Speicher-Claim)*: Großverbraucher (lokale Modelle, Compute-Pipelines, Media-Jobs) konkurrieren um physischen RAM/VRAM.
2. **Stufe 2 — Modellzeit-Zuteilung** *(Nutzungszeit-Claim / Inferenz-Turns)*: Sobald ein Modell im RAM liegt, konkurrieren Nutzer, Rollen und Agenten um Rechenzeit (einzelne **Inferenz-Turns**) auf diesem Modell — geordnet nach **Nutzernähe-Klassen 1–4** (`1 Interaktiv → 2 Auftrag → 3 Termin → 4 Hintergrund`) mit `3:1`-Vordergrund-Fairness.

---

## 2. Verbindliche Begriffs-Tabelle (1 Begriff = 1 Konzept)

| Ebene | Verbindlicher Zielbegriff (GUI & Doku) | Bedeutung | Technischer Kern (rückwärtskompatibel) | Historische / mehrdeutige Altbegriffe (im sichtbaren UI & neuer Doku verboten) |
|---|---|---|---|---|
| **Stufe 1** | **RAM-Zuteilung** *(Status: **RAM-Belegung**, Schalter: **Compute-Vorrang**)* | Physischer RAM-/VRAM-Claim für geladene Modelle und Compute-Verbraucher | `RAMDistributor`, `ConsumerCapability`, `ResourceSocket`, `RunCooldownGate` (`ocean-resources`), `local_resource_reserve` (`bach`) | `Fackel`, `Hauptfackel`, `Fackelhalter`, `Fackelspeicher`, `Fackelbesitz`, `Hardware-Fackel`, `Primary Torch` |
| **Stufe 2** | **Modellzeit-Zuteilung** *(Einzelschritt: **Inferenz-Turn**, Priorität: **Nutzernähe-Klassen 1–4**)* | Zuteilung von Rechenzeit / einzelnen Modellaufrufen auf einem geladenen Modell an Nutzer, Rollen und Agenten | `HostInferenceGate`, `UserProximity`, `inference_queue_policy`, `SlotRequest` | `Model Torch`, `Modell-Fackel`, `Slots` |
| **Modell** | **Lokales Modell** *(mit **Hardware-Default-Profil** je RAM-Größe)* | Lokal installiertes Modell inkl. RAM-sicherer Standard-Parameter (`num_ctx`, `kv_cache_type`, `max_tool_rounds`) | `local_model_catalog`, `model-tuning-catalog.v1` *(geplant in `#4445`)* | `Modell-Sockel`, `Modellsteckplatz`, `Slot` |
| **Zuordnung** | **Modellbindung** | Direkte Bindung eines Agenten an Primärmodell und Fallbacks (`model` + `model_fallbacks`) | `model` + `model_fallbacks` *(kompatibles Schema `bach.model-sockets.v1`)* | `Steckplatzkonfiguration`, `Anbieter-Sockel`, `Modell-Sockel` |
| **Agent** | **Agent** *(eingebaut: **System-Agent**, aktiv: **Living-Agent**)* | Konfiguriertes Agentenprofil (Assistent, Dauerläufer, Connector, Schnittstelle) | Agentenprofil *(kompatible Datei `slots_config.json`)* | `Steckplatz`, `Slot` (*„Steckplatz einrichten“*), `Systemplatz` |
| **Bibliothek** | **Rollenvorlage** & **Modell-Profil** | Wiederverwendbare Rollenbeschreibung und ihr zugeordnetes Leistungs-/Modell-Profil | `role_socket_catalog` *(internes Schema)* | `Agenten-Fabrik`, `Rollen-Sockel`, `Modell-Sockel` |

---

## 3. Rückwärtskompatibilitäts-Regel (keine harten Brüche)

- **Sichtbare Oberfläche, Doku & neue Konzepte** verwenden ausschließlich die verbindlichen Zielbegriffe aus Abschnitt 2.
- **Bestehende API-Routen, Dateinamen, JSON-Schemas und DOM-IDs** (`/api/fackel`, `/api/system/fackel`, `/api/slots`, `slots_config.json`, `bach.model-sockets.v1`, `ResourceSocket`, `#fackel-*`) bleiben aus Kompatibilitätsgründen unverändert, bis ein eigenständiger Migrationsvertrag sie ablöst.
- **Kein Rückbau:** Historische Key-Namen wie `"slots"` in `slots_config.json` oder `fackel` im API-Pfad sind **kein** Auftrag, starre Modell-Slots oder die alte PC-zu-PC-Bridge-Fackel wieder einzuführen.

---

## 4. Verifikation

Die maschinenlesbare Norm liegt unter `architecture/terminology-congruence.v1.json` und wird durch `tests/test_terminology_congruence.py` auf Vollständigkeit, Eindeutigkeit und Trennung von Zielbegriffen und verbotenen Altbegriffen geprüft.
