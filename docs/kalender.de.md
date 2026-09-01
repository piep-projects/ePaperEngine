# Kalender

Drei Spalten, die nächsten Tage hintereinander, gefüllt bis die Seite voll ist.
Was hinter einem Kalender steckt — Microsoft 365 als veröffentlichte ICS,
Google, CalDAV, der eingebaute Local Calendar — erreicht den Renderer nie.
ePaperEngine liest **`calendar`-Entities** von Home Assistant, und mehr weiß es
darüber nicht.

## Eine Quelle eintragen

Panel → **Kalender**. Jede Quelle ist vier Dinge:

| | |
|---|---|
| **Entity** | eine beliebige `calendar.*`-Entity |
| **Person** | der Name in der Legende |
| **Farbe** | eine der sechs Primärfarben des Panels |
| **Art** | *Termine* oder *Geburtstage* |

**Die Art trägt Gewicht.** Eine Geburtstagsquelle zeigt die gerechnete
Jahreszahl, zeigt nur die Anfangszeit — und ist, darauf kommt es an, vom Filter
„vergangene Termine des heutigen Tages ausblenden" **ausgenommen**. Ohne diese
Ausnahme würfe derselbe Schalter den Geburtstag um 09:16 an genau dem Morgen von
der Wand, an dem er gelesen werden soll.

### Nicht nur Geburtstage

Die Art heißt *Geburtstage*, meint aber **jeden Jahrestag** — Hochzeitstag,
Namenstag, Jubiläum. Deshalb ist der Zusatz neutral:

```
09:00   Erika Müller (1946) — 80 Jahre
09:00   Hochzeit Ulla & Christian (2006) — 20 Jahre
09:00   Namenstag Christian
```

**Was gefeiert wird, schreiben Sie in den Titel** — die Wand steuert nur die
Zahl bei. Ein „wird 80" wäre bei einer Hochzeit falsch, und der Kalender liefert
kein Feld, aus dem sich die Art ablesen ließe.

**Das Jahr steht in Klammern im Titel:** `Erika Müller (1946)`. Dann zeigt es
auch die Kalender-App am Telefon, und an der Wand steht dasselbe plus der Zahl.
Alternativ trägt es die **Beschreibung** — dann nur die vier Ziffern und sonst
nichts. Eines von beidem genügt; **beides zugleich** lässt die Klammer zusätzlich
im Bild stehen.

**Fehlt die Jahreszahl, kostet das die Zahl, nicht den Eintrag.** Ein Namenstag
hat keine, und das ist kein Fehler.

## Wie die Seite aussieht

- **Der Tag steht in einer Schiene links**, nicht in einer Zeile darüber: ein
  gefülltes Feld mit der Tageszahl groß und dem Wochentag klein darunter. Es ist
  so hoch wie der Tag und wächst mit, wenn ein Titel zwei Zeilen braucht — die
  Schrift wird nie kleiner. Das spart die Kopfzeile, die jeder Tag vorher hatte,
  und bringt rund ein Drittel mehr Tage auf die Seite.
- **Sonntage tragen ein rotes Feld** statt eines schwarzen. Eine Spalte wird über
  ihre Daten gelesen, und ein roter Block findet sich aus Entfernung.
- **Der Monat steht einmal oben**, über der ersten Spalte. Wechselt der Monat
  mitten im Zeitraum, trägt der Erste ihn in seinem Feld — die Angabe stimmt
  also auch über die Monatsgrenze hinweg.
- **Vor jedem Montag liegt ein gelbes Band** mit der Kalenderwoche und ihrem
  Zeitraum, über die volle Spaltenbreite. Gelb, weil ein Grau auf diesem Display
  überwiegend Weiß ist und deshalb blass wirkt; Gelb ist außerdem die einzige
  Farbe, die keine Kalenderquelle tragen kann.
- **Legende, Fehlerhinweise und sonst nichts** stehen am Fuß der dritten Spalte,
  rechtsbündig. Spalte eins und zwei laufen über die volle Höhe.
- **Ein Farbbalken** in der Farbe der Quelle läuft an jedem Eintrag entlang — ab
  Werk 12 px, einstellbar. Auf einen Meter ist ein 6-px-Balken eine Marke
  *neben* der Zeile; 12 px sind die Farbe *der* Zeile.
- **Leere Tage werden gezeigt**, damit das Auge Tage zählen kann statt sie zu
  lesen — sie tragen nur ihr Datumsfeld, der Platz daneben bleibt weiß.
  Abschaltbar.
- **Ein mehrtägiger Termin wird an beiden Enden benannt und dazwischen als
  durchgehender Farbstreifen gezeichnet** — auch wenn er nicht als ganztägig
  eingetragen ist. Der erste Tag sagt „ab 10:00", der letzte „bis 15:00", und
  zwischen beiden läuft am äußeren Rand eine ununterbrochene Linie in der Farbe
  der Quelle, durch die Tageslücken und über jedes Wochenband hinweg. Ein
  Termin, der am nächsten Morgen vor 6 Uhr endet, bleibt dagegen **ein** Eintrag
  an seinem Abend: ein Konzert von 23:00 bis 01:00 ist kein Termin am nächsten
  Tag.
- **Ein Tag, der höher ist als eine ganze Spalte,** wird gekürzt und sagt das —
  statt übersprungen zu werden. Überspringen hieße, von diesem Tag *und allem
  danach* nichts zu zeigen.

!!! note "Was der Durchlaufstreifen kostet"
    Die Tage zwischen Anfang und Ende **nennen den Termin nicht mehr**. Wer auf
    einen von ihnen sieht, sieht den Streifen und muss ihm nach oben folgen.
    Dafür füllt ein vierzehntägiger Urlaub nicht mehr vierzehn Tagesblöcke,
    sondern zwei — er kostet die Vorausschau also fast nichts mehr.

## Was sie nicht tut

**Es gibt keinen Zeitstempel.** Es gab einen — „aktualisiert 10:17" am Fuß —,
und er trug die Minute, machte damit jedes Kalenderbild einzigartig. Der
Hash-Vergleich konnte dann nie `unchanged` sagen, und aus allen vier Netzläufen
pro Stunde wurde ein echter Push mit sichtbarem Refresh der Wand.

Wie frisch die Seite ist, sagt jetzt die Seite selbst: die Termine von heute
fallen im Lauf des Tages heraus.

## Auf Zuruf abgleichen

**Jetzt abgleichen** auf der Kalenderseite tut drei Dinge auf einmal, weil sie
eine Absicht sind: es zieht jede Quelle (`homeassistant.update_entity`, was
ICS-Quellen brauchen), zählt neu und stößt einen Renderlauf an. Der Lauf wird
*angestoßen*, nicht abgewartet.

Daneben zieht **Neu zählen** ausdrücklich *nicht* — es meldet, was Home
Assistant ohnehin schon hält. Und die Quellen werden höchstens alle 30 Sekunden
gezogen, damit der Lauf, den „Jetzt abgleichen" anstößt, nicht gleich darauf
alles ein zweites Mal holt.

Der Knopf sagt außerdem, ob die Wand gerade überhaupt den Kalender zeigt. Ohne
das sähe er kaputt aus, wenn man ihn drückt, während dort ein Foto hängt.
