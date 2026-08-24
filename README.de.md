# ePaperEngine

Home-Assistant-Integration, die ein **Samsung EM32DX Farb-E-Paper-Panel**
(2560×1440, Spectra 6) als Wanddisplay im Haushalt betreibt: Familienkalender,
Rezepte beim Kochen, Fotos und ein Gruß, wenn Besuch kommt.

> 🇬🇧 [English version of this page](README.md)

## Wie das zusammenspielt

ePaperEngine besteht aus zwei Teilen, die denselben Namen tragen:

| | Aufgabe |
|---|---|
| **Integration** (dieses Repository, über HACS) | hält die Konfiguration, löst auf, welche Ansicht an die Wand gehört, führt den Rezept-Cache, meldet den Zustand — Panel und Lovelace-Karte |
| **Add-on** (auch dieses Repository, über den Add-on-Store des Supervisors) | rendert die Ansicht als HTML/CSS, fotografiert sie mit Chromium, dithert auf die Spectra-6-Palette und pusht sie per MDC ans Panel |

Die Aufteilung ist keine Geschmacksfrage: eine Custom Integration darf nur
reine Python-Pakete mitbringen, das Rendern braucht Chromium und Node. Ein
Add-on ist ein eigener Container und darf beides.

**Ein Repository bedient beide Stores.** HACS liest `hacs.json` und
`custom_components/`, der Supervisor liest `repository.yaml` und
`addon-epaperengine/`. Die beiden überschneiden sich nicht, dieselbe URL wird
also an zwei Stellen eingetragen.

📖 **[Dokumentation](https://piep-projects.github.io/ePaperEngine/de/)** —
Installation, die Ansichten, Automationen und Fehlersuche.

Alles läuft lokal — MDC über TLS auf Port 1515 mit PIN. Keine Cloud, kein
Herstellerkonto, und das Display braucht keinen Internetzugang.

## Voraussetzungen

- Home Assistant 2024.7 oder neuer
- ein Samsung EM32DX („Samsung EMDX 306P“) im LAN erreichbar, Content Source
  auf *Mobile*
- das ePaperEngine-Add-on fürs Rendern und Pushen

## Installation

**Die Integration**

1. In HACS dieses Repository als benutzerdefiniertes Repository vom Typ
   *Integration* hinzufügen.
2. **ePaperEngine** installieren und Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → ePaperEngine.**

**Das Add-on**

4. **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**, dieselbe URL
   eintragen.
5. **ePaperEngine** aus dem Store installieren und starten.

Danach Display, Ansichten und Zeitpläne im **ePaperEngine**-Panel in der
Seitenleiste einrichten. Der ausführliche Weg steht in der
[Dokumentation](https://piep-projects.github.io/ePaperEngine/de/installation/).

## Sprache

Die Oberfläche folgt der Home-Assistant-Sprache. Englisch ist die Basissprache,
Deutsch eine vollständig gepflegte Übersetzung. Eine weitere Sprache sind zwei
JSON-Dateien — `custom_components/epaperengine/translations/` für die
Home-Assistant-Texte und `custom_components/epaperengine/frontend_i18n/` für
Panel und Karte — und keine Zeile Code.

## Stand

Läuft, und hängt an einer Wand. Alle fünf Ansichten werden gerendert und
gesendet — Kalender, Rezepte, Fotos, Gästegruß und die Fehlerseite — samt
Seitenleisten-Panel, Lovelace-Karte, Entities und Diensten drumherum.

Betrieben wurde es bisher von einem Haushalt an einem Panel; was zwischen
Installationen verschieden ist — andere Kalender-Backends von Home Assistant,
andere Medien-Mounts, andere Panels derselben Familie — hat also genau je einen
Test gesehen. Fehlerberichte sind willkommen.

## Lizenz

MIT — siehe [LICENSE](LICENSE).
