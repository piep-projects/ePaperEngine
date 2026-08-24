# ePaperEngine

Ein **Samsung EM32DX** — 32 Zoll Spectra-6-Farb-E-Paper, 2560 × 1440 — an der
Wand, und darauf das, worauf der Haushalt wirklich schaut: der gemeinsame
Kalender, die Rezepte für heute Abend, Familienfotos, und ein Gruß, wenn Besuch
kommt.

Gesteuert vollständig aus **Home Assistant**. Keine Samsung-Cloud, kein
VXT-Abo, und das Display braucht nie einen Internetzugang. Das ist der Zweck des
Projekts, keine Nebenwirkung.

## Wie es arbeitet

Das Display hat keinen Browser und führt nichts Eigenes aus. Ihm wird über
Samsungs **MDC-Protokoll** auf TLS-Port 1515 gesagt, es solle ein Bild abholen —
und dieses Bild liefert das Add-on aus demselben Netz.

```
Zustand aus Home Assistant  →  Jinja-Vorlage  →  Chromium bei 2560×1440
                            →  Floyd-Steinberg auf sechs Farben
                            →  Hash-Vergleich  →  MDC-Push  →  die Wand
```

Ein Lauf dauert drei bis sechs Sekunden. Ist das Bild danach byte-gleich mit dem,
was schon hängt, wird **nicht gepusht** — ein E-Paper-Refresh ist sichtbar und
langsam, und einen, der nichts ändert, sollte niemand mit ansehen müssen.

## Zwei Bausteine, ein Repository

| | Aufgabe | Installiert über |
|---|---|---|
| **Integration** | Konfiguration, Sidebar-Panel, Lovelace-Karte, Rezept-Cache, die Entscheidung welche Ansicht dran ist | HACS |
| **Add-on** | Rendern, Dithern, das Bild ausliefern und an das Display schicken | den Add-on-Store des Supervisors |

Die Teilung ist erzwungen: eine HACS-Integration darf nur reine Python-Pakete
mitbringen, und das Rendern braucht Chromium und Node. Beide liegen in diesem
einen Repository — HACS und der Supervisor lesen verschiedene Dateien und kommen
sich nicht ins Gehege.

## Loslegen

1. [Beide Teile installieren](installation.md)
2. [Auf das Display zeigen](display.md)
3. [Die Karte auf ein Dashboard legen](dashboard.md)
4. [Festlegen, wann was an der Wand steht](ansichten.md)
