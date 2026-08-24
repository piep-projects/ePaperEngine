# Ansichten & Vorrang

Es gibt fünf Ansichten. Vier zeigen etwas; die fünfte erscheint nur, wenn etwas
schiefgeht.

| Ansicht | Was darauf steht |
|---|---|
| **Kalender** | die nächsten Tage aus beliebig vielen HA-Kalendern, in drei Spalten — siehe [Kalender](kalender.md) |
| **Rezepte** | bis zu drei Rezepte nebeneinander, vollständig — siehe [Rezepte](rezepte.md) |
| **Fotos** | ein Foto aus dem Ordner, im festen Takt gewechselt — siehe [Fotos & Gäste](fotos-gaeste.md) |
| **Gäste** | ein Gruß in Schreibschrift über einem Hintergrund — siehe [Fotos & Gäste](fotos-gaeste.md) |
| **Fehler** | ein Satz, wenn die Wand sonst lügen würde |

## Welche gerade dran ist

ePaperEngine geht eine **geordnete Kandidatenliste** von oben nach unten durch
und nimmt den ersten, der *aktiv* ist. Die Liste ist Konfiguration, kein Code —
sortiert wird sie auf der Panel-Seite **Ansichten**.

| Kandidat | aktiv, wenn … |
|---|---|
| `manual` | jemand eine Ansicht von Hand gesetzt hat und der Rückfall noch nicht fällig ist |
| `guests` | der Gästemodus eingeschaltet ist |
| `recipes` | mindestens ein Rezept ausgewählt ist |
| `schedule` | einer der Zeitplan-Helfer gerade `on` ist |
| `fallback` | immer — er steht am Listenende |

Die Ausgangsreihenfolge ist **manual → guests → recipes → schedule → fallback**.

Sortieren lassen sich nur diese fünf. `calendar`, `photos` und `error` haben
keine eigene Aktivitätsbedingung, könnten also nie „aktiv" werden — sie sind
das, worauf ein **Zeitplan** oder der **Rückfall** zeigt, keine Kandidaten für
sich.

### Zeitpläne

Eine Ansicht bekommt ihr Zeitfenster, indem man sie auf einen
**`schedule`-Helfer** von Home Assistant zeigen lässt (Einstellungen → Geräte &
Dienste → Helfer → Zeitplan). ePaperEngine baut keinen eigenen Zeitkalender —
den Helfer gibt es schon, er hat einen Editor und taucht in Automationen auf.

Jede Zuordnung trägt zusätzlich einen **Rang**. Überlappende Fenster sind kein
Fehler: innerhalb des Kandidaten `schedule` gewinnt der niedrigste Rang.

### Eine Ansicht von Hand setzen

Jeder im Haushalt darf eine Ansicht wählen — auf der Übersichtsseite des
Panels, über die Chips der [Lovelace-Karte](dashboard.md) oder mit dem Dienst
`set_view`. Diese
Übersteuerung hält **`manual_timeout_h`** Stunden (ab Werk 4; `0` heißt „bis
jemand zurückschaltet"), danach übernimmt wieder die Automatik.

**Der Gästemodus ist vom Rückfall ausgenommen.** Besuch bleibt übers Wochenende,
nicht vier Stunden. Er wird ausdrücklich beendet — die Karte trägt dafür eine
Zeile „Besuch ist wieder weg", und es gibt den Dienst `set_guests`.

Der Rückfall hängt an einem eigenen Timer statt am nächsten Netzlauf: „Rückfall
in 2 h 48 min" heißt genau das und nicht „bis zu 15 Minuten später".

## Wann die Wand neu gezeichnet wird

- alle **15 Minuten**, nach der Uhr
- wenn die aufgelöste Ansicht wechselt
- wenn der Fototakt weiterspringt
- wenn im Panel etwas gespeichert wird, das das Bild verändert
- wenn der Dienst `render` gerufen oder der Knopf gedrückt wird

Zwei Auslöser innerhalb von 20 Sekunden werden zu einem Lauf zusammengefasst.

**Ein Lauf ist noch kein Push.** Das gerenderte Bild wird gehasht und mit dem
zuletzt gesendeten verglichen; ist es gleich, wird nichts geschickt und der Lauf
meldet `unchanged`. Das ist der Normalfall, kein Fehler.

## Wenn etwas kaputtgeht

Der **erste** Fehllauf in Folge lässt das Bild hängen. Ein kurz abwesendes NAS
oder ein einzelnes verklemmtes Chromium ist es nicht wert, dafür das
Familienfoto abzunehmen. Ab dem **zweiten** in Folge zeigt die Wand den Fehler
selbst: ein Satz, der Zeitpunkt, an dem es losging, und eine technische Zeile.

Der Zeitstempel auf dieser Seite steht auf dem **Beginn der Fehlerserie**, nie
auf dem laufenden Lauf — nur dadurch ist die Seite von Lauf zu Lauf bildgleich,
und der Hash-Vergleich unterdrückt die Wiederholungen. Ein tagelanger Ausfall
kostet genau einen Refresh.

## Welche Sprache die Wand spricht

Die, die Home Assistant spricht. Einen eigenen Schalter gibt es nicht — eine
zweite Spracheinstellung neben der des Systems ist eine, an deren Änderung sich
niemand erinnert. Englisch und Deutsch sind beide vollständig.
