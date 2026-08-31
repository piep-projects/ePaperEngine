# Fehlersuche

## Zuerst den Status lesen

`sensor.epaperengine_status` sagt, wie der letzte Lauf ausgegangen ist, und die
Übersichtsseite des Panels sagt dasselbe in Worten.

| Zustand | Was er heißt | Was zu tun ist |
|---|---|---|
| `unchanged` | gerendert, Bild ist gleich, nichts gesendet | nichts — das ist der Normalfall |
| `pushed` | gerendert und gesendet | nichts |
| `push_off` | gerendert, aber diese Instanz darf nicht senden | Einstellungen → Push-Sicherung, falls das nicht so gewollt ist |
| `push_failed` | das Bild steht, das Panel hat nicht geantwortet | siehe unten |
| `render_failed` | gar kein Bild | siehe unten |
| `idle` | seit der Installation kein Lauf | **Wand aktualisieren** drücken |

## An der Wand steht nichts Neues

**Zuerst prüfen, ob überhaupt etwas neu sein *soll*.** `unchanged` nach einem
Lauf heißt: das Bild ist wirklich dasselbe. Wer am Handy einen Termin geändert
hat, drückt auf der Kalenderseite **Jetzt abgleichen** — das zieht die Quellen
sofort, statt bis zu 15 Minuten zu warten.

Stimmt die **Vorschau** im Panel, aber die Wand nicht, hat das Display einen
Push verpasst: **Bild erneut senden** auf der Übersicht. Dieser Knopf übergeht
den Hash-Vergleich, und genau das ist der Unterschied zwischen den beiden.

## Ein Update ist eingespielt, die Wand sieht aus wie vorher

**Fast immer fehlt die zweite Hälfte.** ePaperEngine besteht aus Integration und
Add-on, sie werden getrennt aktualisiert — und **HACS meldet nur die
Integration**. Das Bild zeichnet aber das **Add-on**: Layout, Schrift, Farben und
Seitenaufbau stecken dort, nicht in der Integration.

**Add-on-Store → ⋮ → Nach Updates suchen**, dann bei ePaperEngine
**Aktualisieren**. Danach zeigen beide dieselbe Versionsnummer — im Panel unter
*Einstellungen* steht die des Add-ons, in HACS die der Integration.

**Faustregel: sieht die Wand anders aus, war es das Add-on.** Ändert sich etwas
an der Bedienung, war es die Integration. Ganze Beschreibung unter
[Installation](installation.md#aktualisieren-beide-halften).

## `push_failed` — das Panel antwortet nicht

1. **Einstellungen → Verbindung testen.** Der Test öffnet TLS:1515 und meldet
   sich an; die Fehlermeldung, die er ausgibt, ist die echte.
2. **Hat das Display die Adresse gewechselt?** Das ist der übliche Grund. Eine
   DHCP-Reservierung dafür setzen.
3. **Stimmt der PIN noch?** Ein Werksreset des Panels setzt ihn zurück.
4. **Schläft das Display, oder ist der Akku leer?** Der Ladestand steht auf
   derselben Einstellungsseite.

## `render_failed` — gar kein Bild

Die technische Zeile auf der Fehlerseite und `sensor.epaperengine_status` nennen
die Ansicht, die gescheitert ist. Das unterscheidet einen wiederholten Fehler
einer Ansicht von einem System, das an allem scheitert.

- **Läuft das Add-on?** Einstellungen → Add-ons → ePaperEngine. Sein Protokoll
  ist das, was zu lesen ist.
- **Stimmt die Renderer-Adresse?** Einstellungen → Renderer (Add-on) → Adresse.
  `http://homeassistant.local:8099`, oder die IP, wenn der Name nicht auflöst.
- **Ist das Medienverzeichnis erreichbar?** Ein abwesendes NAS nimmt Fotos und
  Gästehintergründe mit. Kalender und Rezepte brauchen es nicht.

## Das Panel bleibt weiß / der Seitenleisteneintrag tut nichts

Den Browser mit umgangenem Cache neu laden (Strg+Umschalt+R). Bleibt es weiß,
steht der Grund in der Browserkonsole — und wenn der Eintrag da ist, während die
Seite leer bleibt, ist das JavaScript nicht *gelaufen*, nicht etwa nicht
geladen.

## In Paprika wurde nichts gefunden

- Das Konto unter **Einstellungen → Paprika-Konto** prüfen und auf der
  Rezeptseite **Jetzt abgleichen** drücken; es meldet Zeitpunkt und Anzahl.
- **Vorsicht beim Wiederholen.** Paprika sperrt nach IP, schon nach einer
  Handvoll Fehlanmeldungen.
- Rezepte im Papierkorb von Paprika werden absichtlich herausgefiltert. Ist ein
  Rezept aus der Suche verschwunden, zuerst nachsehen, ob es am Handy gelöscht
  wurde.

## Ein Rezept wird gekürzt

Erwartet, und es sagt es auch. Bei drei Rezepten nebeneinander passt gut die
Hälfte einer üblichen Sammlung nicht vollständig. Bei zweien passt das meiste,
bei einem fast alles.

Zutatenliste und Titel werden nie gekürzt — nur die Zubereitung, und sie sagt,
wo geschnitten wurde.

## Die Wand aktualisiert sich viel zu oft

Jeder sichtbare Refresh kommt von einem Bild, das sich wirklich geändert hat.
Passiert es auf die Minute alle 15 Minuten, trägt etwas auf der Seite die
aktuelle Uhrzeit. Genau das galt für den Kalender, bis der Zeitstempel in seinem
Fuß entfernt wurde — deshalb trägt heute keine Ansicht mehr einen.

## Die Wand spricht die falsche Sprache

Sie folgt der Spracheinstellung von Home Assistant selbst
(**Einstellungen → System → Allgemein**). Einen eigenen Schalter gibt es nicht.
