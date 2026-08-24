# Das Display

ePaperEngine spricht mit einem **Samsung EM32DX** über Samsungs
**MDC**-Protokoll — TLS auf TCP-Port **1515**, angemeldet mit dem sechsstelligen
PIN des Panels. Kein Cloud-Konto, kein Samsung-Zertifikat, keine Tizen-App auf
dem Gerät.

## Was einzutragen ist

Panel in der Seitenleiste → **Einstellungen → Verbindung zum Panel**:

| Feld | Was es ist |
|---|---|
| **Host** | die IP-Adresse des Panels im Netz |
| **MDC-PIN** | der sechsstellige PIN, der am Panel selbst eingestellt ist |
| **MAC** | die MAC-Adresse des Panels, für Wake-on-LAN |

Dann **Verbindung testen** drücken. Der Test pingt nicht und schaut auch nicht
nach, ob ein Port offen ist — er öffnet TLS:1515, meldet sich mit dem PIN an und
stellt dem Panel eine echte Frage. Eine grüne Antwort heißt: die ganze Kette
steht. Modell, Firmware, Seriennummer und Akkustand stehen weiter unten auf
derselben Seite.

!!! tip "Dem Panel eine feste Adresse geben"
    Im Router eine **DHCP-Reservierung** für das Display setzen. Holt es sich
    eine neue Adresse, scheitert jeder Push, bis es jemandem auffällt und das
    Feld ändert — und genau das ist schon passiert.

## Wie ein Bild dorthin kommt

Das Panel hat keinen Browser. Ihm wird *gesagt*, es solle holen:

1. Das Add-on schreibt das gerenderte PNG und ein kleines
   `content.json`-Manifest in seinen eigenen Speicher und liefert beides auf
   Port 8099 aus
2. Über MDC schickt es `set_content_download` mit der Manifest-Adresse
3. Das Panel holt das Manifest, dann das Bild, über einfaches HTTP im LAN
4. Das Panel aktualisiert sich

Die Adresse im Manifest ist die Adresse des Add-ons **aus Sicht des Panels**,
ermittelt aus der Netzroute dorthin — nicht die, die auf der
Einstellungsseite steht; die sagt nur, wie Home Assistant das Add-on erreicht.
Ausgeliefert wird aus dem Add-on-Speicher, nicht aus dem Medienbaum: ein NAS,
das mitten im Abholen neu startet, darf das Display nicht ins Leere greifen
lassen.

## Nur eine Instanz darf senden

Es gibt genau **ein** Display. Rendern und senden zwei Home-Assistant-Instanzen
— etwa eine Test- und eine Produktivinstanz — dann überschreiben sie einander
alle Viertelstunde, und die Wand flackert zwischen zwei Wahrheiten.

**Einstellungen → Push-Sicherung** trägt den Schalter:

- **an** — diese Instanz bedient die Wand (Vorgabe bei einer frischen
  Installation)
- **aus** — es wird weiterhin alles gerendert, Bild und Vorschau werden
  geschrieben, das Panel bleibt voll benutzbar, und der Lauf meldet
  **`push_off`**. Nur der MDC-Push entfällt.

Wiedereinschalten sendet nicht von selbst. Das tut der nächste Netzlauf — oder
**Wand aktualisieren** auf der Übersichtsseite.

## Anti-Ghosting

Farb-E-Paper behält eine blasse Erinnerung an das, was vorher darauf stand. Das
Panel hat dafür eine eigene **Bildschirmschutz**-Routine, die auf dem Gerät
eingeplant ist (ab Werk 03:00 Uhr). Wie gut sie über Monate eines meist
unveränderten Kalenders wirkt, ist hier **nicht gemessen** — wer Ghosting sieht,
schaut zuerst auf diese Einstellung.

## Akku und Wake-on-LAN

Das EM32DX läuft am Netz oder auf seinem eingebauten Akku. Das MAC-Feld gibt es,
damit ein schlafendes Panel vor einem Push mit einem Magic Packet geweckt werden
kann. **Ob Wake-on-LAN es über WiFi zuverlässig erreicht, ist ungeprüft** — am
Netzstrom stellt sich die Frage nicht.
