# Rezepte

Bis zu drei Rezepte gleichzeitig an der Wand, jedes vollständig: Titel, Zutaten,
Zubereitung. Von der Wand zu kochen heißt, nie Mehl von einem Tablet zu wischen.

Die Rezepte kommen aus **[Paprika 3](https://www.paprikaapp.com/)** und liegen
in einem lokalen Cache. Beim Rendern wird nichts geholt — die Wand wartet nicht
auf jemandes Cloud.

## Das Konto verbinden

Panel → **Einstellungen → Paprika-Konto**: E-Mail-Adresse und Passwort des
Paprika-Kontos, dazu der Abgleichtakt (ab Werk 24 Stunden).

Der Abgleich ist inkrementell: eine Anfrage holt `{uid: hash}` über die ganze
Sammlung, und vollständig geholt werden nur die Rezepte, deren Hash sich
geändert hat.

!!! warning "Paprika sperrt nach IP"
    Eine Handvoll Fehlanmeldungen genügt. Das Passwort sorgfältig eintippen —
    schnelles Wiederholen gibt es hier nicht.

Rezepte im **Papierkorb** von Paprika werden herausgefiltert. Sie kommen aus der
API wie jedes andere Rezept — gleiche uid, voller Text, unterschieden allein
durch einen Merker — und ohne diesen Filter stünde ein gelöschter Entwurf in der
Suche neben dem echten Rezept.

## Auswählen, was gekocht wird

Panel → **Rezepte**. Gesucht wird über jedes Wort in Titel, Zutaten und
Zubereitung; die Suche ist akzent- und großschreibungsblind, `grießbrei`,
`GRIESSBREI` und `griessbrei` finden dasselbe.

Jeder Treffer sagt, was an der Wand mit ihm geschieht — für jede der drei
möglichen Aufteilungen:

```
1: 28 px · 2: 26 px · 3: gekürzt
```

Das ist keine Schätzung. Dasselbe Layoutmodell, mit dem der Renderer arbeitet,
liegt wortgleich in der Integration, damit das Panel versprechen kann, was die
Wand tun wird.

## Portionen umrechnen

Jedes ausgewählte Rezept trägt neben der hinterlegten Personenzahl ein Zielfeld.
Wer es ändert, bekommt umgerechnete Mengen.

Umgerechnet wird nur die **Zutatenliste**, und dort nur die Menge am *Anfang*
einer Zeile — eine Menge mitten im Zubereitungstext ist ein Datenfehler in
Paprika und nichts, was stillschweigend umgeschrieben werden sollte. Gerundet
wird nicht über eine Nachkommastelle hinaus: `187,5 g Butter` ist ehrlich,
`190 g` wäre erfunden. Zeilen, die mit einem Wort statt einer Zahl beginnen —
Salz, Pfeffer — bleiben unangetastet.

Etwa jedes vierte Rezept hat in Paprika gar keine Portionsangabe; dort gibt es
das Feld schlicht nicht.

## Wie drei Rezepte auf eine Wand passen

Das Panel ist 2560 px breit. **Ein** Rezept bekommt alles, **zwei** je die
Hälfte, **drei** je ein Drittel — die Wand bleibt nie zu einem Drittel weiß,
bloß weil nur zwei Gerichte geplant sind.

In seiner Spalte wird jedes Rezept für sich eingepasst, in Stufen: **28 px →
26 px → 24 px**, und wenn auch 24 px nicht reichen, wird die **Zubereitung
gekürzt** und sagt das an der Schnittstelle. Die Zutatenliste wird nie gekürzt,
der Titel nie.

Die Zutatenliste teilt sich außerdem auf zwei oder drei Spalten, wenn die
Einträge kurz genug dafür sind — daher kommt meist der Platz für die
Zubereitung.

Nichts davon ist geschätzt. Die Zeichenbreite ist aus genau der Schriftdatei
gemessen, mit der Chromium zeichnet, und das Zeilenmodell ist an zwanzig echten
Zubereitungen gegen Chromium geprüft: es trifft auf eine Zeile und ist nie so
optimistisch, dass etwas abgeschnitten würde.
