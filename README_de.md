# open-ocean

**Free the ocean.**

Das kostenlose Community-Vollsystem des ellmos-Ökosystems.

*[English](README.md)*

> **Privater Aufbau, und bewusst früh.** Dieses Repository existiert, bevor das System existiert —
> damit die Architektur einen Ort hat, während sie entschieden wird. Es öffnet sich, wenn das
> Wasser im Ozean ankommt; siehe *[Freigabebedingungen](#freigabebedingungen)*.

---

## Zuerst lesen: dieses Repository ist eine Baustelle

**Hier liegt noch kein System.** Kein Installer, keine eigene Laufzeit — und bewusst keine Kopien
der Rezepte. Was hier liegt, ist die Architektur dessen, was gebaut wird: welche Rezepte das
System konsumieren soll, wo sie leben und was der Installer werden muss.

Wer etwas heute Nutzbares sucht, findet es in der Rezept-Schicht — einem eigenen Repository mit
den Bundle-Manifesten, das Welle für Welle freigegeben wird. Die Rezepte sind Monate vor dem
System fertig, das sie konsumiert, und genau deshalb liegen sie nicht hier: Ein Repository, das
Rezepte unter dem Namen des Systems ausliefert, sähe fertig aus, während das System es nicht ist.

| Repository | Was es ist | Zustand |
|---|---|---|
| **bundles** | die Rezept-Schicht: Manifeste, Katalog, Export-Werkzeug | privat, Freigabe Welle für Welle |
| **open-ocean** (hier) | der Systembau: Architektur, Installer, das Konsumierende | privat, früh |

## Der Name und die Architektur, die er trägt

Das Ökosystem benennt seine Ebenen nach Wasser, weil das Bild die Architektur trägt statt sie zu
schmücken:

| Begriff | Was es ist |
|---|---|
| **stream / Wasser** | der Prozess selbst — Daten, Arbeit, Ergebnisse, die durch alles hindurchfließen |
| **Bach / Rinnsal** | die wilden, gewachsenen Läufe: die ursprüngliche persönliche Vollinstanz |
| **water pipes** | dasselbe Wasser, gezähmt und modularisiert — Module und Bundles |
| **waterfall** | die deklarative Quelle: Baukasten, Rezepte, Kataloge |
| **ocean** | das Vollsystem; Endpunkt der Linie Bach → Rinnsal → Ozean |
| **open-ocean** | der Teil, der allen gehört: das kostenlose Community-Vollsystem |

Die leitende Regel ist ein Erhaltungssatz: **Extraktion ändert das Bett, nie das Wasser.** Umbau
muss die Funktion erhalten — „gleiche Wassermenge" heißt Funktionsparität. Auch das ist keine
Zierde, sondern die Messlatte, die dieses Repository für seine Freigabe überspringen muss.

Das System wird nicht neben der ursprünglichen Instanz neu geschrieben, und die Ursprungsinstanz
wird nicht umgebaut. Es entsteht durch fortgesetzte **Extraktion**: Module fließen heraus, und die
Ursprungsinstanz baut sie anschließend selbst wieder ein und ersetzt damit ihre eigenen Innereien.
Sie wird kein Museumsstück. Sie lebt weiter als begradigter Fluss — nicht mehr ganz natürlich,
aber ans Wasser angeschlossen und weiter versorgt.

## Was tatsächlich hier liegt

```
architecture/
  open-ocean.skeleton.v1.json   welche Rezepte das System konsumieren soll, per Hash gepinnt
  INSTALLER-TARGET.md           was der Installer werden muss — und was er nicht tun darf
PRIVATE.txt                     das Publikations-Gate, bewusst committet
```

Das Gerüst referenziert 13 Bundles in zwei Ringen — den Funktionskern und die Breite darum herum.
Es **referenziert** sie: Kein Manifest wird hierher kopiert. Kopien würden in dem Moment
auseinanderlaufen, in dem das Rezept-Repository weitergeht, und ließen dieses Repository weiter
erscheinen, als es ist.

## Status

| | |
|---|---|
| Architektur-Gerüst | vorhanden, 13 Bundles referenziert |
| Installer | **nicht gebaut** — im Grundsatz entschieden, zurückgestellt, jetzt wieder fällig |
| Eigene Laufzeit | **nicht verfügbar** — jeder Kandidat ist privat oder nur deklariert |
| Rezepte | im Rezept-Repository gepflegt, nicht hier |

## Freigabebedingungen

Dieses Repository trägt ein bedingtes Publikations-Gate (`PRIVATE.txt`, bewusst committet, damit
das Gate dort sichtbar ist, wo Sichtbarkeit geschaltet wird). Es öffnet sich, wenn alle vier
Bedingungen nachweislich erfüllt sind:

1. **Grüne Bestandteile** — jedes referenzierte Bundle ist grün: jede seiner Komponenten
   öffentlich und geprüft.
2. **Schleusen-Test bestanden** — die Gesamtleitung trägt: eine frische Installation aus diesen
   Rezepten erreicht auf einer Maschine, die nicht der Entwicklungsrechner ist, einen
   arbeitsfähigen Zustand.
3. **Parität für den Release-Umfang** — das System leistet, was es zu decken beansprucht. Ein
   kleinerer installierbarer Kern ist eine Bau-Etappe, kein Release.
4. **Publikationsprüfung bestanden** — Recht, Privacy und Lizenz geprüft, keine Blocker.

Bedingung 2 ist die, nach der dieses Repository benannt ist. Die Schleusen zu öffnen und
zuzusehen, ob das Wasser wirklich ankommt, ist der Test, den keine Menge korrekter Manifeste
ersetzt.

## Lizenz

Noch nicht entschieden. Sie ist eine der vier Freigabebedingungen und wird geklärt, bevor dieses
Repository sich öffnet.
