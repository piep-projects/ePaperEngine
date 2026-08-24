# Installation

Zwei Bausteine, auf zwei verschiedenen Wegen installiert, aus demselben
Repository.

## 1 · Die Integration über HACS

ePaperEngine steht (noch) nicht im HACS-Standardkatalog, also als Custom
Repository hinzufügen:

1. **HACS → ⋮ → Benutzerdefinierte Repositories**
2. URL `https://github.com/piep-projects/ePaperEngine`, Kategorie **Integration**
3. **ePaperEngine** in der Liste suchen, **Herunterladen**, danach **Home
   Assistant neu starten**

Nach dem Neustart unter **Einstellungen → Geräte & Dienste → Integration
hinzufügen → ePaperEngine** einrichten. Auszufüllen gibt es nichts — der
Config-Flow lässt genau eine Instanz zu und fragt nichts ab; alles Weitere wird
danach im Panel eingestellt.

Danach steht **ePaperEngine** in der Seitenleiste, und es gibt diese Entities:

| Entity | Was sie sagt |
|---|---|
| `sensor.epaperengine_status` | wie der letzte Lauf ausgegangen ist |
| `sensor.epaperengine_target_view` | welche Ansicht gerade dran ist |
| `sensor.epaperengine_recipe_cache` | wie viele Rezepte im Cache liegen |
| `binary_sensor.epaperengine_display_reachable` | ob das Display auf die letzte MDC-Abfrage geantwortet hat |
| `button.epaperengine_refresh` | jetzt rendern und senden |

## 2 · Das Add-on über den Supervisor

Dieselbe Repository-URL, an anderer Stelle eingetragen:

1. **Einstellungen → Add-ons → Add-on-Store → ⋮ → Repositories**
2. `https://github.com/piep-projects/ePaperEngine` hinzufügen
3. Der Store führt jetzt **ePaperEngine** — **Installieren**, dann **Starten**

Das Add-on baut seinen Container beim ersten Installieren selbst (Chromium, Node
und Pillow); das dauert ein paar Minuten. Optionen braucht es keine: Adresse und
PIN des Displays sind **absichtlich** keine Add-on-Optionen — sie stünden im
Klartext in einer Datei, die jeder aus der Supervisor-Oberfläche öffnen kann.
Die Integration reicht sie stattdessen auf Anfrage weiter.

!!! note "Warum das Add-on nicht in HACS liegt"
    HACS installiert Python-Pakete. Der Renderer braucht ein Headless-Chromium
    und eine Node-Laufzeit — das trägt nur ein Container.

## 3 · Die beiden voneinander wissen lassen

Das Panel in der Seitenleiste öffnen, auf **Einstellungen**, und unter
**Renderer (Add-on) · Adresse** eintragen:

```
http://homeassistant.local:8099
```

Wenn der Name nicht auflöst, die IP nehmen. Das ist die Adresse, unter der *Home
Assistant* das Add-on erreicht; die Adresse, von der das **Display** holt,
ermittelt das Add-on selbst aus der Route zum Panel.

Weiter mit [dem Display](display.md).

## Wo die Bilder liegen

ePaperEngine liest die Fotos aus einem Verzeichnis unter Home Assistants
`media`-Baum und schreibt seine Renderings dorthin zurück:

```
<Medienwurzel>/
  photos/        deine Fotos — die Auswahl trifft, wer Dateien hineinlegt
  backgrounds/   Hintergründe für den Gästegruß
  wall/          das zuletzt gesendete Bild in voller Größe
  preview/       die Vorschau des Panels
  processed/     zugeschnittene 16:9-Fassungen, automatisch gepflegt
```

`<Medienwurzel>` ist ohne Zutun `/media/epaperengine`, und das stimmt nur, wenn
das Medienverzeichnis lokal liegt. **Home Assistant hängt Netzwerkspeicher als
Unterverzeichnis von `/media` ein** — eine NAS-Freigabe erscheint als
`/media/<Mount-Name>/`, und `/media` selbst ist die eigene Platte der
HA-Maschine. Unter **Einstellungen → Quelle → Medienwurzel** also
`/media/<Mount-Name>/epaperengine` eintragen, wenn die Fotos auf dem NAS liegen —
sonst landen ein paar hundert Fotos samt ihren 2560 × 1440-Renderings auf der
Systemplatte der VM.
