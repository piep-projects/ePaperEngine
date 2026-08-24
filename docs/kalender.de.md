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

**Die Art trägt Gewicht.** Eine Geburtstagsquelle zeigt das aus dem Jahr
gerechnete Alter, zeigt nur die Anfangszeit — und ist, darauf kommt es an, vom
Filter „vergangene Termine des heutigen Tages ausblenden" **ausgenommen**. Ohne
diese Ausnahme würfe derselbe Schalter den Geburtstag um 09:16 an genau dem
Morgen von der Wand, an dem er gelesen werden soll.

## Wie die Seite aussieht

- **Keine Kopfzeile.** Das Datum steht einmal da, im ersten Tagestitel. Eine
  Kopfzeile, die es ein zweites Mal sagt, kostete 140 px von allen drei Spalten
  — 14 % der Termine, die die Seite fasst.
- **Legende, Fehlerhinweise und sonst nichts** stehen am Fuß der dritten Spalte,
  rechtsbündig. Spalte eins und zwei laufen über die volle Höhe.
- **Ein Farbbalken** in der Farbe der Quelle läuft an jedem Eintrag entlang — ab
  Werk 12 px, einstellbar. Auf einen Meter ist ein 6-px-Balken eine Marke
  *neben* der Zeile; 12 px sind die Farbe *der* Zeile.
- **Leere Tage werden gezeigt** („keine Termine"), damit das Auge Tage zählen
  kann statt sie zu lesen. Abschaltbar.
- **Ein Tag, der höher ist als eine ganze Spalte,** wird gekürzt und sagt das —
  statt übersprungen zu werden. Überspringen hieße, von diesem Tag *und allem
  danach* nichts zu zeigen.

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
