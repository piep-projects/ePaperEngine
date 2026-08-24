# Dashboard

Auf dieser Seite geht es um die **Lovelace-Karte** — den täglichen Blick, neben
Wetter und Haustechnik. Eingerichtet wird im Panel in der Seitenleiste; die
Karte ist zum Hinsehen da und für die eine Entscheidung, die ein Haushalt
täglich trifft: *was soll gerade an der Wand stehen?*

## Hinzufügen

Die Karte registriert ihre Ressource selbst — unter **Einstellungen →
Dashboards → Ressourcen** ist **nichts** einzutragen.

1. Ein Dashboard öffnen, **Dashboard bearbeiten → Karte hinzufügen**
2. In der Auswahl nach **ePaperEngine** suchen

Oder in YAML:

```yaml
type: custom:epaperengine-card
```

## Konfiguration

Zwei Schlüssel, und einer davon ist der Typ. Einen grafischen Editor gibt es
nicht — es gibt nichts einzustellen, was einen rechtfertigen würde.

| Schlüssel | | |
|---|---|---|
| `type` | Pflicht | `custom:epaperengine-card` |
| `title` | optional | die Überschrift; ohne Angabe `ePaperEngine` |

```yaml
type: custom:epaperengine-card
title: Die Wand
```

Die Karte nimmt **keine** `entity`. Sie liest den ganzen Zustand über ihre
eigene WebSocket-Verbindung und fragt alle 15 Sekunden nach — derselbe Takt, den
auch das Panel benutzt.

## Was sie zeigt

Von oben nach unten, und das meiste davon nur, wenn es etwas zu sagen gibt:

**Ein roter Streifen — nur bei einer echten Störung.** `push_failed`,
`render_failed` oder ein nicht erreichbares Add-on. Er nennt die Störung, die
technische Zeile und — falls noch ein Bild hängt — welche Ansicht das ist.
**`unchanged` ist keine Störung** und bringt den Streifen nie hoch.

**Ein oranger Streifen, solange eine Ansicht von Hand angeheftet ist**, mit der
verbleibenden Zeit.

**Was an der Wand hängt**: die Ansicht, seit wann, **warum** sie gewählt wurde
(Zeitplan, manuell, Gästemodus, Rückfall), und wann zuletzt gesendet wurde.
Kam der letzte Lauf als `unchanged` zurück, steht es da — „Bild unverändert —
nichts gepusht" ist der Normalfall, keine Warnung.

**Nächster Wechsel**, wenn einer ansteht.

**Ein Gästestreifen**, wenn der Gästemodus an ist: seit wann, und der eine
Knopf, der ihn beendet — *Besuch ist wieder weg*.

**Die Vorschau**, eingeklappt. Die Karte bleibt klein und wächst auf Zuruf.

**Die Chips**: *Automatik*, dann Kalender, Rezepte, Fotos, Gäste. Ein Druck
übersteuert den Vorrang für `manual_timeout_h` Stunden; *Automatik* gibt ihn
sofort zurück. Die Fehleransicht hat keinen Chip — sie ist nichts, was jemand
wählt.

Das **Zahnrad** in der Kopfzeile öffnet das Panel in der Seitenleiste. Der
Knopf **Dashboard** in der Kopfzeile des Panels führt zurück — und zwar auf
genau das Dashboard, von dem aus das Zahnrad gedrückt wurde. Wurde das Panel
direkt über die Seitenleiste geöffnet, führt er auf das Dashboard, auf dem die
Karte zuletzt zu sehen war, sonst auf das Standard-Dashboard. Ohne ihn wäre das
Panel eine Sackgasse, sobald die Seitenleiste eingeklappt ist — auf einem Tablet
der Normalfall.

## Was absichtlich nicht darauf ist

Drei Auslassungen, und jede ist eine Regel statt eines Vergessens:

- **Kein Aktualisieren-Knopf.** Das zeitgesteuerte Netz läuft alle 15 Minuten
  und pusht nur bei wirklich geändertem Bild — der Knopf stieße also nur an, was
  ohnehin gleich passiert. Die Regel, die daraus folgt: *kein Bedienelement auf
  dieser Karte tut bloß das, was das System von selbst tut* — deshalb auch kein
  „nochmal versuchen" und kein „Verbindung prüfen". Die beiden Wand-Knöpfe für
  die Ausnahmefälle stehen auf der Übersichtsseite des Panels.
- **Keine „Display erreichbar"-Lampe im Normalfall.** Eine Lampe, die immer grün
  ist, trägt keine Information. Nur die Störung meldet sich.
- **Die Vorschau ist eingeklappt.** Eine Dashboard-Karte, die überwiegend Bild
  ist, schiebt alles andere vom Schirm.

Das eine Bedienelement, das wie eine Ausnahme aussieht, ist *Besuch ist wieder
weg* — und ist keine: der Gästemodus ist vom automatischen Rückfall ausgenommen,
**nichts beendet ihn von selbst**, und der Gäste-Chip schaltet ihn für jeden im
Haus ein. Ohne das Gegenstück wäre er etwas, das der Haushalt starten und nur
ein Administrator beenden kann.

## Karte oder Panel?

| | |
|---|---|
| **Karte** | was an der Wand hängt, und es ändern — für alle, jeden Tag |
| **Panel** (Seitenleiste) | Kalender, Rezeptauswahl, Fotos, Gästegruß und jede Einstellung — überwiegend Administratorsache |

Die Entities und Dienste hinter beidem stehen in
[Automationen & Dienste](automationen.md).
