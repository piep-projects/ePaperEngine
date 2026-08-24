# Fotos & Gäste

Zwei Ansichten, die sich dieselbe Maschinerie teilen: ein Ordner voller Bilder,
auf 16:9 zugeschnitten, auf sechs Farben gedithert und zwischengespeichert,
damit kein Lauf je auf das NAS wartet.

## Fotos

Fotos nach `<Medienwurzel>/photos/` legen. Das ist die ganze Auswahl — es gibt
kein Album, keine Verschlagwortung, keinen Bildwähler. Was im Ordner liegt, kann
erscheinen.

Panel → **Fotos** stellt ein, wie oft gewechselt wird
(`rotation_interval_min`, ab Werk 60) und zeigt den Cache.

**Der Takt wird aus der Uhr abgeleitet**, nicht gewürfelt: welches Foto dran
ist, folgt aus der aktuellen Zeit geteilt durch das Intervall. Ein versehentlich
ausgelöster Renderlauf wechselt das Motiv deshalb nicht — bei zufälliger Wahl
verbrennte jeder Knopfdruck einen sichtbaren Refresh.

Neue Dateien fallen beim nächsten Cache-Durchgang auf. **Cache neu einlesen** auf
der Fotoseite liest den Ordner sofort noch einmal.

Fotos werden über den **Hash ihres Inhalts** geführt, nicht über den Dateinamen
— eine umbenannte Datei auf dem NAS ist deshalb kein neues Foto.

## Gäste

Ein Gruß in Schreibschrift über einem Hintergrund nach Wahl — für den Besuch
übers Wochenende, den Kindergeburtstag, die Nachbarn zum Essen.

Panel → **Gäste**:

| | |
|---|---|
| **Name** | die große Zeile, etwa „Familie Berger" |
| **Grußzeile** | die kleinere darunter |
| **Hintergrund** | aus `<Medienwurzel>/backgrounds/` |
| **Schrift** | Dancing Script, Caveat oder Great Vibes — alle drei reisen im Add-on mit |
| **Größen** | ein Wunsch, in Pixeln; ein langer Name schrumpft und wird nie gekürzt |
| **Farbe** | eine der sechs Primärfarben |
| **Neigung** | ±45° |
| **Kontur** | ab Werk aus; 2–32 px in einer Gegenfarbe |

**Die Farben sind sechs, und einen Farbwähler gibt es nicht.** Alles andere wird
aus den Primärfarben gedithert, und an einer Buchstabenkante ist das ein
gesprenkelter Umriss statt einer Tönung.

**Die Kontur ist das, was einen Gruß über jedem Untergrund tragen lässt.** Weiße
Schreibschrift über einem dunklen Foto trägt von selbst; über hellem Himmel
nicht, und 8 px weißer Saum richten das, ohne etwas zuzudecken. Sie ist so
gezeichnet, dass der Strich nach *außen* wächst — andersherum frisst er die
dünnen Verbindungsstriche der Buchstaben weg.

Die Größenanpassung hat zwei Stellschrauben, nicht eine, und beide sind einzeln
gescheitert: nur am Breitenbudget zu ziehen bricht mehr Zeilen um und macht den
Block *höher*; nur am Schriftgrad zu ziehen setzt einen 52-Zeichen-Namen bei 40°
als eine riesige Zeile, wo zwei bequeme gepasst hätten. Was trotzdem nicht
passt, heißt im Laufprotokoll `cramped`, statt von `overflow: hidden`
verschluckt zu werden.

### Den Gästemodus wieder ausschalten

Der Gästemodus ist vom automatischen Rückfall ausgenommen — Besuch bleibt übers
Wochenende, nicht vier Stunden. Also muss er ausdrücklich beendet werden, und
**wer ihn einschalten darf, darf ihn ausschalten**: die Lovelace-Karte trägt die
Zeile, und der Dienst `set_guests` erledigt es aus einer Automation.

Ein Hintergrund, dessen Datei verschwunden ist, kostet das Bild, nicht den Lauf.
Der Gruß geht trotzdem hoch — der Besuch steht schon im Flur.
