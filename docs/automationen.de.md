# Automationen & Dienste

## Die Lovelace-Karte

`custom:epaperengine-card` zeigt, was an der Wand hängt, warum diese Ansicht
gewählt wurde und wann zuletzt gesendet wurde, und trägt die Chips zum Wechseln
— Hinzufügen und Konfigurieren steht unter **[Dashboard](dashboard.md)**.

## Entities

| Entity | |
|---|---|
| `sensor.epaperengine_status` | `idle` · `pushed` · `unchanged` · `push_failed` · `push_off` · `render_failed` |
| `sensor.epaperengine_target_view` | `calendar` · `recipes` · `photos` · `guests` · `error` |
| `sensor.epaperengine_recipe_cache` | Anzahl der zwischengespeicherten Rezepte |
| `binary_sensor.epaperengine_display_reachable` | die letzte MDC-Abfrage |
| `button.epaperengine_refresh` | jetzt rendern und senden |

!!! note "`unchanged` ist kein Fehler"
    Es ist der häufigste Ausgang und der gewünschte. Es heißt: an der Wand
    hängt bereits das richtige Bild.

`binary_sensor.epaperengine_display_reachable` ist kein Ping und keine
Portprüfung — dahinter steht ein echtes MDC-Gespräch mit dem Panel, samt PIN.

## Dienste

### `epaperengine.render`

Rendern und, falls sich das Bild geändert hat, senden.

```yaml
action: epaperengine.render
data:
  force: false   # true sendet auch bei unverändertem Bild
```

`force: true` ist der Fall „nochmal schicken" — ein Display, das nach einem
Stromausfall einen Push verpasst hat und auf einem alten Bild hängt.

### `epaperengine.set_view`

```yaml
action: epaperengine.set_view
data:
  view: recipes   # calendar · recipes · photos · guests · error
```

Übersteuert den Vorrang von Hand, für `manual_timeout_h` Stunden.

### `epaperengine.set_guests`

```yaml
action: epaperengine.set_guests
data:
  active: true
```

Schaltet den Gästemodus ein oder aus. Ausschalten räumt eine manuelle
Anheftung auf `guests` gleich mit weg.

### `epaperengine.sync_recipes`

Holt die Paprika-Sammlung sofort, außer der Reihe.

### `epaperengine.sync_anniversaries`

```yaml
action: epaperengine.sync_anniversaries
data:
  dry_run: false
```

Schreibt die Jahreszahl in den Jahrestagskalender selbst, damit am Handy
dasselbe steht wie an der Wand: aus `Erika Müller (1946)` wird
`Erika Müller (1946) — 80 Jahre`.

Angefasst werden nur Quellen der Art **Jahrestage**, und beschreibbar sind nur
**CalDAV**-Kalender — ein Local Calendar lässt sich von außen nicht ändern und
wird namentlich übersprungen. Die Wand rechnet weiterhin selbst; der
zurückgeschriebene Zusatz ist Bequemlichkeit fürs Handy, nicht die Quelle der
Wahrheit. Fällt der Dienst aus oder wird er nie eingerichtet, stimmt die Wand
trotzdem.

**`dry_run` ist standardmäßig `true`** — der Lauf meldet dann, was er ändern
würde, und ändert nichts. Zum wirklichen Schreiben ausschalten. `limit: 1`
schreibt höchstens einen Eintrag, gut für den ersten Versuch.

Ein täglicher Lauf ist harmlos: Einträge, deren Titel schon stimmt, kosten keine
einzige Anfrage.

```yaml
automation:
  - alias: Jahrestage nachtragen
    triggers:
      - trigger: time
        at: "04:30:00"
    actions:
      - action: epaperengine.sync_anniversaries
        data:
          dry_run: false
```

## Beispiele

**Ein Gruß, wenn während einer Feier geklingelt wird**

```yaml
automation:
  - alias: Besuch ist da
    triggers:
      - trigger: state
        entity_id: input_boolean.party_mode
        to: "on"
    actions:
      - action: epaperengine.set_guests
        data:
          active: true
```

**Rezepte an die Wand, solange gekocht wird**

```yaml
automation:
  - alias: Kochzeit
    triggers:
      - trigger: time
        at: "17:30:00"
    actions:
      - action: epaperengine.set_view
        data:
          view: recipes
```

Besser noch: der Ansicht `recipes` auf der Panel-Seite **Ansichten** einen
Zeitplan-Helfer geben. Dann ist es ein Fenster statt eines Augenblicks, es
taucht im Zeitplan-Editor auf, und hinterher muss nichts zurückgesetzt werden.

**Melden, wenn die Wand eine Stunde lang stumm ist**

```yaml
automation:
  - alias: Die Wand antwortet nicht
    triggers:
      - trigger: state
        entity_id: binary_sensor.epaperengine_display_reachable
        to: "off"
        for: "01:00:00"
    actions:
      - action: notify.persistent_notification
        data:
          message: Das E-Paper-Panel hat seit einer Stunde nicht geantwortet.
```

## Berechtigungen

Das meiste an ePaperEngine steht jedem offen, der an Home Assistant angemeldet
ist: eine Ansicht wählen, den Gästemodus schalten, rendern, senden. Das sind die
alltäglichen Dinge, und wer ändern darf, was an der gemeinsamen Wand hängt, darf
sie auch neu zeichnen lassen.

**Konfiguration ist Administratorsache** — die ganze Einstellungsseite, die
Kalenderquellen, die Rezeptauswahl. Der MDC-PIN und das Paprika-Passwort gehen
an Nicht-Administratoren überhaupt nicht heraus: sie kommen als schlichtes „ein
Wert ist hinterlegt" zurück.
