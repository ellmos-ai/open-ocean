# Produkt- und Stackgrenzen

*[English](PRODUCT-STACK-BOUNDARIES.md)*

> **Status:** Durch den Nutzer ratifizierter Entscheid vom 2026-08-29. Dieses
> Dokument bestimmt die Produktzugehörigkeit; es erlaubt keine Runtime-Aktivierung,
> Veröffentlichung, Änderung der Repository-Sichtbarkeit oder Freigabe.

## Produktalgebra

```text
OPEN OCEAN = PUBLIC
PRIVATE OCEAN = PRIVATE_NON_PROPRIETARY
FULL OCEAN = OPEN OCEAN + PRIVATE OCEAN

SPEEDBOAT = PROPRIETARY
            + SELECTED_PUBLIC
            + SELECTED_PRIVATE_NON_PROPRIETARY
```

| Produkt | Enthält | Schließt aus | Verhältnis |
|---|---|---|---|
| **OPEN OCEAN** | Öffentliche OCEAN-Komponenten | Private und proprietäre Komponenten | Öffentliche OCEAN-Basis und das Produkt, das dieses Repository später veröffentlicht |
| **PRIVATE OCEAN** | Private, nicht proprietäre OCEAN-Komponenten | Proprietäre Komponenten | Private Schicht der OCEAN-Familie |
| **FULL OCEAN** | OPEN OCEAN + PRIVATE OCEAN | Proprietäre Komponenten | Vollständige lokale Entwicklungs- und Testkomposition für OCEAN |
| **SPEEDBOAT** | Proprietäre Komponenten plus ausdrücklich ausgewählte OPEN-/PRIVATE-OCEAN-Teile | Alle nicht ausgewählten OCEAN-Komponenten | Eigenständiger Geschwister-Stack; keine OCEAN-Edition und kein Overlay |

## Die Speedboat-Metapher ist eine Architekturregel

Speedboat befährt den Ozean. Es kann ausgewählte Gewässer nutzen oder zwischen
Inseln verkehren, ist aber nicht der Ozean und erbt nicht den gesamten Ozean.

Maschinenlesbar bedeutet das:

- SPEEDBOAT besitzt eigene Manifest-, Runtime-, Origin-, State-, Release- und
  Roadmap-Grenzen.
- `inherits_from` ist leer.
- Gemeinsame OCEAN-Bundles und -Module gelangen ausschließlich über explizite
  Allowlisten in SPEEDBOAT.
- Ein gemeinsamer Katalog dient der Entdeckung und erzeugt keine Produktvererbung.

## Kompatibilität und Migration

Das V4-Rezeptschema behält den technischen Klassenwert `hosted-private`, um eine
breite Hash- und Resolver-Migration zu vermeiden. An der Produktgrenze wird er als
`proprietary` und `SPEEDBOAT-only` interpretiert. Die beiden aktuellen Bundles
dieser Klasse sind `ellmos-multitenancy-bundle` und
`ellmos-saas-operations-bundle`.

Die technische Manifest-ID `ellmos-development-fullsystem` bleibt vorerst die
Kennung von FULL OCEAN. Produktnamen erzwingen keine sofortige physische Repo- oder
ID-Umbenennung.

Repository-Sichtbarkeit ist eine eigene Achse. Ein privates Repository kann
PRIVATE-OCEAN-Substanz oder proprietäre SPEEDBOAT-Substanz enthalten; nur der
Produktvertrag und ausdrückliche Manifeste/Allowlisten entscheiden die Zugehörigkeit.

## Aktuelle Folge für die Komposition

FULL OCEAN konsumiert jetzt die 28 OCEAN-fähigen Plattform-/Domänen-Bundles. Die
beiden proprietären Bundles zählen nicht mehr als FULL-OCEAN-Anforderungen und
dürfen keine OCEAN-Vollständigkeitslücken erzeugen. SPEEDBOAT deklariert diese zwei
Bundles eigenständig und wählt gegenwärtig kein gemeinsames OCEAN-Bundle oder
-Modul aus.

Die maschinenlesbare Quelle ist
`ellmos-development-system/contracts/product-stack-boundary-contract.v1.json`.
Bis der zugehörige Rezept-Branch kanonisch übernommen wurde, konsumiert dieses
Repository die gepushte Integrationsquelle ausdrücklich und behauptet keinen
Cutover auf `main`.

## Abnahmeregeln

- OPEN OCEAN enthält ausschließlich öffentliche OCEAN-Komponenten.
- PRIVATE OCEAN enthält ausschließlich private, nicht proprietäre OCEAN-Komponenten.
- FULL OCEAN ist exakt OPEN OCEAN + PRIVATE OCEAN.
- Proprietäre Komponenten blockieren die Fertigstellung von FULL OCEAN nicht.
- SPEEDBOAT erbt kein OCEAN-Produkt.
- Jede gemeinsam genutzte SPEEDBOAT-Komponente besitzt einen expliziten Auswahleintrag.
