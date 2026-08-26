/**
 * The user guide, as data.
 *
 * Kept separate from the page that renders it for two reasons. The prose is
 * the part that goes stale — it is written against what the UI does today, and
 * whoever changes a screen should be able to find and fix the paragraph about
 * it without reading a React component. And a flat, typed structure lets the
 * page build its own table of contents and anchors, so adding a section is one
 * object rather than an edit in three places.
 *
 * Everything here was checked against the running application, not against
 * memory of how it was built.
 */

export type DocBlock =
  | { kind: "p"; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "steps"; items: string[] }
  | { kind: "table"; head: string[]; rows: string[][] }
  | { kind: "code"; text: string }
  | { kind: "note"; tone: "info" | "warn" | "good"; title: string; text: string };

export interface DocSubsection {
  id: string;
  title: string;
  blocks: DocBlock[];
}

export interface DocSection {
  id: string;
  title: string;
  lede: string;
  subsections: DocSubsection[];
}

export const DOC_SECTIONS: DocSection[] = [
  // ----------------------------------------------------------------- //
  {
    id: "grundlagen",
    title: "Grundlagen",
    lede: "Was die Plattform misst und warum alles in R gerechnet wird.",
    subsections: [
      {
        id: "was-ist-das",
        title: "Wofür Hadrian³ da ist",
        blocks: [
          {
            kind: "p",
            text: "Hadrian³ führt Backtests aus mehreren Quellen in einem Speicher zusammen und bewertet jedes System auf derselben Grundlage: Erwartungswert in R, netto nach Kosten, getrennt nach In-Sample und Out-of-Sample. Dazu kommt ein eigener Backtesting-Motor, ein Strategie-Designer und ein Journal für real gehandelte Trades.",
          },
          {
            kind: "p",
            text: "Der Zweck ist Vergleichbarkeit. Ein System, das 1 % pro Trade riskiert, und eines, das 5 % riskiert, sind in Dollar nicht vergleichbar — in R schon.",
          },
        ],
      },
      {
        id: "r-einheit",
        title: "Die R-Einheit",
        blocks: [
          {
            kind: "p",
            text: "1R ist der Abstand zwischen Entry und Stop. Ein Trade, der am Stop schließt, ist −1R; einer, der das Doppelte des Stop-Abstands in die richtige Richtung läuft, ist +2R. Weil der Stop die Einheit definiert, hat jede Strategie hier zwingend einen Stop — ohne ihn gäbe es kein R und damit keine Kennzahl.",
          },
          {
            kind: "note",
            tone: "info",
            title: "Netto heißt netto",
            text: "Alle R-Werte in der Plattform sind nach Kosten. Entry- und Exit-Fee, Slippage und Funding werden pro Trade abgezogen und ebenfalls in R ausgedrückt — in der Trade-Tabelle des Designers stehen Gross R, Cost R und R nebeneinander, damit sichtbar bleibt, was die Kosten gefressen haben.",
          },
        ],
      },
      {
        id: "is-oos",
        title: "In-Sample und Out-of-Sample",
        blocks: [
          {
            kind: "p",
            text: "Jede Kennzahl wird dreimal gerechnet: über alle Trades, über die vor dem Stichtag (In-Sample) und über die ab dem Stichtag (Out-of-Sample). Der Stichtag ist eine Server-Einstellung (IS_OOS_SPLIT_DATE) und steht im Kopf der Systemliste.",
          },
          {
            kind: "p",
            text: "Die OOS-Spalte ist die, auf die es ankommt. In-Sample ist der Zeitraum, in dem die Regeln entstanden sind — dort gut auszusehen ist keine Leistung.",
          },
          {
            kind: "note",
            tone: "warn",
            title: "Leere IS-Spalte ist normal",
            text: "Liegen alle Trades eines Systems nach dem Stichtag, ist die In-Sample-Spalte komplett leer und alles steht unter OOS. Das ist kein Fehler, sondern die ehrliche Antwort — bei einem frisch gerechneten Engine-Backtest über die letzten Monate ist es der Regelfall.",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "erste-schritte",
    title: "Erste Schritte",
    lede: "Die Reihenfolge, in der die Plattform sinnvoll benutzt wird.",
    subsections: [
      {
        id: "reihenfolge",
        title: "Einmal einrichten, dann arbeiten",
        blocks: [
          {
            kind: "steps",
            items: [
              "Einstellungen: Venue anlegen, Fees und Lot-Größen je Asset prüfen, Kontostand setzen. Ohne das rechnet der Risk-Rechner mit Standardwerten, die nicht deine sind.",
              "Systeme befüllen: entweder bestehende Backtests importieren (xlsx / programmatisch / CSV) oder im Strategie-Designer eine Strategie bauen und backtesten.",
              "Bewerten: Kennzahlen und Quant-Analytik auf der Systemdetailseite lesen. Interessant ist OOS, nicht Gesamt.",
              "Stufe hochsetzen: ein System, das überzeugt, von „Backtest“ auf „Live Testing“ stellen — das ist die Stufe, ab der überhaupt real gehandelt wird.",
              "Live-Trades journalisieren: über den Risk-Rechner die Größe bestimmen und den Trade durch seine sechs Stufen führen.",
            ],
          },
        ],
      },
      {
        id: "navigation",
        title: "Wo was liegt",
        blocks: [
          {
            kind: "table",
            head: ["Seite", "Wofür"],
            rows: [
              ["Systems", "Alle Systeme, Filter, Sortierung, Import, Detailansicht"],
              ["Strategies", "Strategie-Designer: Blöcke, Python-Editor, Backtest, Versionen"],
              ["Live", "Journal der real gehandelten Trades, Kontostand, Ausführungsqualität"],
              ["Risk", "Positionsgrößen-Rechner, auch ohne Trade nutzbar"],
              ["Trades", "Trade-Explorer über alle Systeme, Backtest oder real"],
              ["Concepts", "Welche Systeme welche Marktkonzepte nutzen — Graph und Matrix"],
              ["Dashboard", "Aggregierte Kennzahlen und kombinierte Equity-Kurve"],
              ["Settings", "Venues, Fees je Asset, Kontostand"],
            ],
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "kennzahlen",
    title: "Kennzahlen lesen",
    lede: "Was in den Karten steht und woran man ein Problem erkennt.",
    subsections: [
      {
        id: "kernkennzahlen",
        title: "Die vier Kernkennzahlen",
        blocks: [
          {
            kind: "table",
            head: ["Kennzahl", "Bedeutung", "Woran man hängenbleibt"],
            rows: [
              ["EV", "Durchschnittliches R pro Trade", "Unter 0 verliert das System, egal wie hoch die Win-Rate ist"],
              ["ECE", "EV geteilt durch die Streuung der R-Werte", "Misst Verlässlichkeit: hohes EV bei wilder Streuung ist wenig wert"],
              ["EVol", "EV gewichtet mit der Handelsfrequenz (Trades pro Tag)", "Ein gutes System, das zweimal im Jahr feuert, trägt kaum etwas bei"],
              ["Composite", "0,4·EV + 0,4·ECE + 0,2·EVol", "Die Gesamtnote, aus der der Grade A–F kommt"],
            ],
          },
          {
            kind: "note",
            tone: "info",
            title: "Grades sind absolut, nicht relativ",
            text: "A–F kommen aus festen Schwellen, die aus dem ursprünglichen Forschungs-Workbook übernommen wurden — nicht aus einem Vergleich mit den anderen Systemen. Ein F bleibt ein F, auch wenn es das beste System im Bestand ist.",
          },
        ],
      },
      {
        id: "verteilung",
        title: "Risiko und Verteilung",
        blocks: [
          {
            kind: "table",
            head: ["Kennzahl", "Bedeutung"],
            rows: [
              ["Profit Factor", "Summe der Gewinne geteilt durch Summe der Verluste. Unter 1 verliert das System."],
              ["Max DD (R)", "Größter Rückgang der kumulierten R-Kurve von einem Hoch aus."],
              ["RoMaD", "Total R geteilt durch Max Drawdown — Ertrag je Einheit Schmerz."],
              ["Skew", "Schiefe der R-Verteilung. Positiv heißt: wenige große Gewinner tragen das Ergebnis."],
              ["Perzentile", "5./25./50./75./95. Perzentil der R-Werte. Zeigt, wie die Trades wirklich verteilt sind, nicht nur ihr Mittel."],
            ],
          },
          {
            kind: "p",
            text: "Die R-Verteilung als Histogramm und die Equity-Kurve stehen darunter. Bei einer Strategie mit festem Ziel und festem Stop hat das Histogramm typischerweise nur zwei Balken — das ist keine Anomalie, sondern die Folge der Regeln.",
          },
        ],
      },
      {
        id: "rolling-ev",
        title: "Rolling EV",
        blocks: [
          {
            kind: "p",
            text: "Der EV über ein gleitendes Fenster der letzten N Trades (umschaltbar zwischen 10, 20 und 50). Die Frage, die er beantwortet: war die Kante über die Zeit stabil oder stammt sie aus einer einzigen guten Phase?",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "systeme",
    title: "Systeme",
    lede: "Die Liste, die Herkunft eines Systems und sein Lebenszyklus.",
    subsections: [
      {
        id: "liste",
        title: "Liste und Filter",
        blocks: [
          {
            kind: "p",
            text: "Die Systemliste filtert nach Klasse, Status, Grade und Herkunft und sortiert über die Spaltenköpfe. Ein Klick auf die Zeile öffnet das System.",
          },
          {
            kind: "table",
            head: ["Herkunft", "Bedeutung"],
            rows: [
              ["manuell", "Aus dem Excel-Forschungs-Workbook oder per CSV importiert"],
              ["prog", "Aus dem Ergebnisverzeichnis eines der vorgelagerten Python-Backtesting-Motoren"],
              ["engine", "Von der eingebauten Backtesting-Engine erzeugt (Strategie-Designer)"],
              ["ui", "Zusatzmarke: in der Oberfläche angelegt und damit re-import-geschützt"],
            ],
          },
        ],
      },
      {
        id: "status",
        title: "Der Status ist eine Aussage über Vertrauen",
        blocks: [
          {
            kind: "p",
            text: "Backtest → Live Testing → Active → Retired. Umgeschaltet wird auf der Detailseite. Der Status ist keine Dekoration: er steuert, wie groß der Ausführungspfad eine Position machen darf.",
          },
          {
            kind: "table",
            head: ["Status", "Anteil des konfigurierten Risikos"],
            rows: [
              ["Backtest", "0 — handelt nicht live, die Größenrechnung verweigert die Ausgabe"],
              ["Live Testing", "25 %"],
              ["Active", "100 %"],
              ["Retired", "0 — handelt nicht mehr"],
            ],
          },
          {
            kind: "note",
            tone: "warn",
            title: "Warum ein Backtest-System nicht handeln darf",
            text: "Ein Backtest ist eine Simulation. Volle Größe darauf zu setzen heißt, Kapital hinter eine Kante zu stellen, die es nur in der Simulation je gegeben hat. Die Stufe muss bewusst hochgesetzt werden.",
          },
        ],
      },
      {
        id: "detail",
        title: "Die Detailseite",
        blocks: [
          {
            kind: "list",
            items: [
              "Regel-Briefing: Entry, Stop Loss, Take Profit als Text. Bei importierten Systemen von Hand geschrieben, bei Engine-Systemen aus der Strategie-Definition gerendert.",
              "Konzepte: welche Marktkonzepte das System nutzt, manuell oder heuristisch zugeordnet.",
              "Live (real): Live-Kennzahlen, sobald das System real gehandelt wurde — bewusst getrennt von den Backtest-Zahlen.",
              "Backtest-Daten: Kennzahlen in den drei Spalten, R-Verteilung, Equity-Kurve, Rolling EV, Quant-Analytik.",
              "Backtest-Trades: die Einzeltrades, editierbar; „Trade hinzufügen“ für Nachträge von Hand.",
            ],
          },
        ],
      },
      {
        id: "import",
        title: "Importieren",
        blocks: [
          {
            kind: "p",
            text: "„Import xlsx“ liest das konfigurierte Forschungs-Workbook, „Import programmatisch“ die Ergebnisverzeichnisse der vorgelagerten Motoren. Beide sind idempotent — mehrfaches Ausführen erzeugt keine Dubletten.",
          },
          {
            kind: "note",
            tone: "good",
            title: "Re-Import-Schutz",
            text: "Felder, die du in der Oberfläche geändert hast, werden von einem erneuten Import nicht überschrieben. Ebenso bleiben von Hand angelegte Trades erhalten. Was der Import mitbringt, ersetzt nur, was der Import zuvor gebracht hat.",
          },
          {
            kind: "p",
            text: "Nach dem Import meldet die Schaltfläche, wie viele Tabs vollständig, unvollständig oder übersprungen waren. Unvollständige sind kein Fehlschlag — halbfertige Tabs sind in echten Forschungs-Workbooks der Normalfall und werden als solche ausgewiesen.",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "quant",
    title: "Quant-Analytik",
    lede: "Drei Werkzeuge gegen drei verschiedene Arten, sich selbst zu täuschen.",
    subsections: [
      {
        id: "walkforward",
        title: "Walk-Forward",
        blocks: [
          {
            kind: "p",
            text: "Legt rollende Fenster über die Historie: je ein In-Sample-Block, gefolgt von einem Out-of-Sample-Block, dann um einen Schritt weiter. Gemeldet wird der Anteil der Fenster mit positivem OOS-EV und der Mittelwert dieser OOS-EVs.",
          },
          {
            kind: "p",
            text: "Die Frage dahinter: hätte das System zu jedem Zeitpunkt der Historie funktioniert, oder nur über den Gesamtzeitraum gemittelt?",
          },
          {
            kind: "note",
            tone: "warn",
            title: "Null Fenster ist eine Antwort",
            text: "Ist die Historie kürzer als IS- plus OOS-Fenster, meldet die Ansicht null Fenster statt etwas zu erfinden. Bei einem Engine-Backtest über wenige Monate ist das bei Standardeinstellungen zu erwarten — für Walk-Forward braucht es mehr Historie.",
          },
        ],
      },
      {
        id: "montecarlo",
        title: "Monte-Carlo",
        blocks: [
          {
            kind: "p",
            text: "Zieht die vorhandenen R-Werte mit Zurücklegen neu und rechnet daraus tausend alternative Verläufe. Ergebnis: EV-Perzentile, die Wahrscheinlichkeit eines positiven Ausgangs und ein Equity-Fächer.",
          },
          {
            kind: "p",
            text: "Die Frage dahinter: wie viel vom Ergebnis war die Reihenfolge? Ein System, dessen 5. Perzentil deutlich unter null liegt, hätte bei anderer Reihenfolge derselben Trades verloren.",
          },
          {
            kind: "p",
            text: "Der Lauf ist mit festem Seed versehen — gleiche Trades ergeben immer dasselbe Bild, sonst wäre die Zahl nicht zitierfähig.",
          },
        ],
      },
      {
        id: "topographie",
        title: "Topographie",
        blocks: [
          {
            kind: "p",
            text: "Eine Heatmap über zwei Parameter mit einer Kennzahl als Farbe, gefüttert aus einem Parameter-Sweep. Zu jeder Zelle werden die acht Nachbarn ausgewertet.",
          },
          {
            kind: "note",
            tone: "info",
            title: "Robust best statt best",
            text: "Interessant ist nicht die beste Zelle, sondern das flachste hohe Plateau — eine Spitze, deren Nachbarn einbrechen, ist meistens Zufall und überlebt den nächsten Monat nicht. Genau dafür steht „robust_best“: das Maximum von min(Zelle, schlechtester Nachbar).",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "designer",
    title: "Strategie-Designer",
    lede: "Strategien bauen — als Blöcke oder als Python. Beides ergibt dieselbe Definition.",
    subsections: [
      {
        id: "anlegen",
        title: "Anlegen und Aufbau",
        blocks: [
          {
            kind: "p",
            text: "Über „Neue Strategie“ Name, Asset, Timeframe, Richtung und den Regelträger wählen: „Deklarativ (Regel-Baum)“ oder Python. Die Detailseite hat fünf Reiter: Editor, Blöcke, Backtest, Versionen, Trades.",
          },
          {
            kind: "note",
            tone: "info",
            title: "Ein Objekt, zwei Fenster",
            text: "Blöcke und Editor bearbeiten dieselbe Definition. Was du in den Blöcken änderst, steht sofort im JSON und umgekehrt. Gespeichert wird über denselben Weg.",
          },
        ],
      },
      {
        id: "bloecke",
        title: "Der Baustein-Designer",
        blocks: [
          {
            kind: "table",
            head: ["Abschnitt", "Inhalt"],
            rows: [
              ["Metadaten", "Asset, Timeframe, Richtung, Beschreibung"],
              ["Parameter", "Benannte Zahlen mit optionalem Bereich (Min/Max/Schritt) — die Grundlage für Sweeps"],
              ["Indikatoren", "ID, Typ, Quelle, Periode. Die ID ist der Name, auf den Regeln sich beziehen"],
              ["Einstieg", "Regel-Baum für Long und, je nach Richtung, Short"],
              ["Ausstieg", "Optionale Ausstiegsregel — ohne sie leben Trades von Stop und Ziel"],
              ["Filter", "Bedingungen, die zusätzlich erfüllt sein müssen, damit ein Einstieg zählt"],
              ["Risiko", "Stop (definiert 1R), optionales Ziel, Break-even, Trailing, maximale Haltedauer"],
              ["Kosten", "Entry-Fee, Exit-Fee, Slippage, Funding"],
            ],
          },
          {
            kind: "p",
            text: "Bedingungen sind Vergleiche zwischen zwei Operanden: Preis, Indikator, Konstante oder — nur im Ausstieg — Positionszustand. Mit „Alle von“, „Eines von“ und „Nicht“ lassen sie sich schachteln.",
          },
          {
            kind: "note",
            tone: "good",
            title: "Die Oberfläche bietet nichts an, was abgelehnt würde",
            text: "Die Palette kommt aus dem Schema des Servers. Deshalb hat ATR kein Quelle-Feld (es liest High, Low und Close zusammen), verschwinden bei „kreuzt aufwärts/abwärts“ die Offset-Felder (ein Kreuzen vergleicht immer Bar und Vorgänger), und Positionszustand steht nur im Ausstieg zur Wahl.",
          },
          {
            kind: "note",
            tone: "warn",
            title: "Positionszustand gehört in den Ausstieg",
            text: "Einstiegsregeln und Filter werden nur ausgewertet, solange keine Position offen ist. „Bars gehalten“ in einer Einstiegsregel wäre dort dauerhaft leer — die Regel würde nie feuern und sähe aus wie ein Setup, das es nie gab. Deshalb wird sie abgelehnt.",
          },
        ],
      },
      {
        id: "python",
        title: "Der Python-Weg",
        blocks: [
          {
            kind: "p",
            text: "Statt eines Regel-Baums schreibst du eine Klasse gegen die Strategie-Schnittstelle. Die Metadaten — Indikatoren, Risiko, Parameter — bleiben dieselben Felder wie bei den Blöcken; nur die Logik liegt im Code.",
          },
          {
            kind: "code",
            text: `class Breakout(Strategy):
    name = "20-Bar Breakout"

    def on_bar(self, ctx):
        if not ctx.indicator_ready("hh"):
            return None
        if ctx.position is None and ctx.price("close") > ctx.indicator("hh", 1):
            return Signal.enter_long()
        return None`,
          },
          {
            kind: "list",
            items: [
              "ctx.price(feld, offset) — Preis, offset zählt rückwärts, 0 ist der aktuelle geschlossene Bar.",
              "ctx.indicator(id, offset) — Indikatorwert; None, solange er noch nicht warmgelaufen ist.",
              "ctx.indicator_ready(...) — die übliche erste Zeile einer on_bar.",
              "ctx.position — der offene Trade oder None.",
              "Signal.enter_long() / enter_short() / exit() — oder None für „nichts tun“.",
            ],
          },
          {
            kind: "note",
            tone: "warn",
            title: "Dein Code läuft in einer Sandbox",
            text: "Strategie-Code wird in einem eigenen Prozess ohne Dateisystem, ohne Netzwerk, mit Speicher- und Zeitlimit ausgeführt. Importierbar ist nur eine kleine Liste (math, statistics, random, datetime, collections, itertools, functools, decimal, re und ähnliche). numpy und pandas stehen dort nicht zur Verfügung — das ist Absicht.",
          },
          {
            kind: "p",
            text: "Ein Fehler im Strategie-Code kommt mit einer Rückverfolgung zurück, die nur deine eigenen Zeilen zeigt. Eine Endlosschleife wird nach Ablauf des Zeitlimits abgebrochen.",
          },
        ],
      },
      {
        id: "versionen",
        title: "Versionen",
        blocks: [
          {
            kind: "p",
            text: "Jedes Speichern legt eine neue Version an; bestehende Versionen werden nie verändert. Auch das Zurückholen einer alten Definition ist eine neue Version — die Historie wächst nur nach vorn.",
          },
          {
            kind: "p",
            text: "Jeder Backtest hält fest, gegen welche Version er lief. Ein Ergebnis lässt sich damit noch Monate später auf genau die Definition zurückführen, die es erzeugt hat.",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "backtest",
    title: "Backtesten",
    lede: "Aus einer Strategie Trades machen — und wissen, was das Ergebnis wert ist.",
    subsections: [
      {
        id: "lauf",
        title: "Einen Lauf starten",
        blocks: [
          {
            kind: "p",
            text: "Im Reiter „Backtest“ optional Start und Ende setzen (ohne Angabe: die letzten zwei Jahre), Parameter-Overrides eintragen und ausführen. Kerzendaten werden vom öffentlichen Marktdaten-Endpunkt geholt und lokal zwischengespeichert — ein zweiter Lauf über denselben Zeitraum braucht kein Netz mehr.",
          },
          {
            kind: "table",
            head: ["Feld", "Wirkung"],
            rows: [
              ["Start / Ende", "Zeitraum der Kerzen. Leer lassen für die Standardspanne."],
              ["Parameter-Overrides", "Setzt deklarierte Parameter nur für diesen Lauf. Leer heißt: die gespeicherten Werte."],
              ["Ergebnis speichern (persist)", "Schreibt das Ergebnis zusätzlich als System in die Systemliste."],
            ],
          },
          {
            kind: "note",
            tone: "info",
            title: "persist ist bewusst aus",
            text: "Beim Ausprobieren willst du keine Systeme hinterlassen — und jeder gespeicherte Lauf ersetzt die Trades des vorherigen. Setz den Haken, wenn ein Ergebnis es wert ist, neben den importierten Systemen zu stehen und von der Quant-Analytik gelesen zu werden.",
          },
        ],
      },
      {
        id: "ergebnis",
        title: "Das Ergebnis lesen",
        blocks: [
          {
            kind: "p",
            text: "Oben stehen Status, Version, Anzahl Bars und Zeitpunkt, darunter dieselben Kennzahlenkarten wie bei jedem anderen System, dann R-Verteilung und Equity-Kurve. Der Reiter „Trades“ zeigt jeden Einzeltrade mit Gross R, Cost R, R, Haltedauer und Ausstiegsgrund.",
          },
          {
            kind: "table",
            head: ["Ausstiegsgrund", "Bedeutung"],
            rows: [
              ["stop", "Der Stop wurde innerhalb des Bars erreicht"],
              ["stop_gap", "Der Bar eröffnete bereits jenseits des Stops — gefüllt wird zur Eröffnung, nicht zum Stop-Preis"],
              ["target", "Das Ziel wurde innerhalb des Bars erreicht"],
              ["target_gap", "Der Bar eröffnete jenseits des Ziels"],
              ["rule", "Die Ausstiegsregel hat ausgelöst"],
              ["max_bars", "Die maximale Haltedauer war erreicht"],
              ["end_of_data", "Die Position war am Ende der Daten noch offen und wurde zum letzten Kurs geschlossen"],
            ],
          },
          {
            kind: "note",
            tone: "warn",
            title: "Warnungen ernst nehmen",
            text: "Über dem Ergebnis stehen gegebenenfalls Warnungen: eine am Ende noch offene Position, übersprungene Einstiege, weil der Stop noch nicht berechenbar war. Sie ändern die Zahlen nicht, aber sie ändern, wie viel die Zahlen wert sind.",
          },
        ],
      },
      {
        id: "annahmen",
        title: "Was die Engine annimmt",
        blocks: [
          {
            kind: "list",
            items: [
              "Ein Signal auf Bar i wird zur Eröffnung von Bar i+1 gefüllt — nie zum Schlusskurs des Bars, aus dem die Entscheidung stammt.",
              "Berührt ein Bar Stop und Ziel, gilt der Stop. OHLC verrät die Reihenfolge nicht; die ungünstige Annahme ist die ehrliche.",
              "Eröffnet ein Bar jenseits von Stop oder Ziel, wird zur Eröffnung gefüllt — in beide Richtungen, nicht nur in der schmeichelhaften.",
              "Es ist immer höchstens eine Position offen.",
              "Stop-Anpassungen (Break-even, Trailing) werden aus Bar i berechnet und wirken ab Bar i+1.",
            ],
          },
        ],
      },
      {
        id: "sweeps",
        title: "Parameter-Sweeps",
        blocks: [
          {
            kind: "p",
            text: "Ein Sweep variiert zwei deklarierte Parameter über ihre deklarierten Bereiche und bewertet jede Kombination mit einer Kennzahl. Das Ergebnis ist ein Raster, das die Topographie-Ansicht des zugehörigen Systems zeichnet.",
          },
          {
            kind: "list",
            items: [
              "Nur Parameter mit Min, Max und Schritt taugen als Achse — ohne Bereich gibt es nichts zu variieren.",
              "Nur Kennzahlen, bei denen höher besser ist. Ein Drawdown-Maximum würde die Auswertung stillschweigend umdrehen.",
              "Das Raster ist auf 400 Zellen begrenzt und läuft synchron. Ein größeres wird mit der Rechnung abgelehnt statt halb ausgeführt.",
            ],
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "risk",
    title: "Risk-Rechner",
    lede: "Von Entry, Stop und Wunschrisiko zur handelbaren Positionsgröße.",
    subsections: [
      {
        id: "eingaben",
        title: "Eingaben",
        blocks: [
          {
            kind: "table",
            head: ["Feld", "Bedeutung"],
            rows: [
              ["Entry / Stop Loss", "Die Preise. Ihr Abstand ist 1R; die Richtung ergibt sich daraus."],
              ["Risiko-Modus", "USD oder Prozent des Kontostands."],
              ["Risk-Modifier", "Faktor auf das Wunschrisiko, z. B. 0,5 für ein halbes Risiko."],
              ["Venue / Asset", "Bestimmt Fees und vor allem die Lot-Größe — die kleinste handelbare Schrittweite."],
              ["Kontostand (Szenario)", "Leer lassen für den echten Kontostand. Ein Wert hier rechnet nur ein Szenario und ändert nichts."],
            ],
          },
          {
            kind: "note",
            tone: "warn",
            title: "Das Asset entscheidet über die Schrittweite",
            text: "BTC handelt in 0,00001er-Schritten, SOL in 0,01er, DOT in 0,1er. Mit der falschen Schrittweite entsteht eine Größe, die sich an der Börse nicht platzieren lässt. Die Werte stehen in den Einstellungen je Asset.",
          },
        ],
      },
      {
        id: "ergebnis-risk",
        title: "Das Ergebnis",
        blocks: [
          {
            kind: "p",
            text: "Der Rechner gibt die gerundete Positionsgröße, das Notional, die Fees und das tatsächlich eingegangene Risiko aus — Letzteres weicht durch die Rundung auf die Lot-Größe leicht vom Wunsch ab. Ein zulässiges Abweichungsband (Standard ±5 %) markiert, ob das noch in Ordnung ist.",
          },
          {
            kind: "list",
            items: [
              "Rundet die Position auf null, ist der Trade mit diesem Risiko auf diesem Asset nicht handelbar.",
              "Liegt das Notional unter der Mindest-Ordergröße der Börse, wird die Order abgelehnt.",
              "Übersteigt der nötige Hebel das Maximum des Assets, wird das ausgewiesen.",
              "Zusätzlich wird die nächstkleinere sichere Variante gezeigt: abgerundet statt gerundet.",
            ],
          },
          {
            kind: "p",
            text: "Aus dem Ergebnis heraus lässt sich direkt ein Live-Trade anlegen.",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "live",
    title: "Live-Trading",
    lede: "Das Journal für real gehandelte Trades.",
    subsections: [
      {
        id: "lebenszyklus",
        title: "Sechs Stufen",
        blocks: [
          {
            kind: "p",
            text: "Ein Ticket wandert durch feste Stufen. Jeder Übergang wird mit Zeitstempel festgehalten, damit hinterher nachvollziehbar ist, wie lange was gedauert hat.",
          },
          {
            kind: "table",
            head: ["Stufe", "Bedeutung"],
            rows: [
              ["Setup gesichtet", "Das Setup ist erkannt, noch nichts gerechnet"],
              ["Risk berechnet", "Positionsgröße steht, Fees und Lot-Größe sind eingefroren"],
              ["Order gesetzt", "Die Order liegt an der Börse"],
              ["Entry gefüllt", "Die Ausführung ist erfolgt — hier entsteht die Abweichung zum Plan"],
              ["Laufend", "Position offen"],
              ["Geschlossen", "Ergebnis in R und USD steht, der Kontostand wird fortgeschrieben"],
            ],
          },
          {
            kind: "p",
            text: "„Abgebrochen“ ist aus jeder aktiven Stufe erreichbar. Abgebrochene Tickets zählen weder in die Statistik noch auf den Kontostand.",
          },
        ],
      },
      {
        id: "qualitaet",
        title: "Ausführungsqualität",
        blocks: [
          {
            kind: "p",
            text: "Die Plattform vergleicht den geplanten mit dem tatsächlichen Entry und weist die Abweichung in Prozent aus. Über alle Trades hinweg steht sie als „Ø Deviation“ in der Live-Übersicht.",
          },
          {
            kind: "p",
            text: "Der Sinn: die Lücke zwischen Backtest und Realität sichtbar machen. Eine Strategie mit 0,2R Kante und durchgehend 0,15R Ausführungsverlust ist keine Strategie.",
          },
        ],
      },
      {
        id: "kontostand",
        title: "Kontostand",
        blocks: [
          {
            kind: "p",
            text: "Der Kontostand ist ein fortgeschriebenes Journal, keine einzelne Zahl: jede Änderung — Einzahlung, geschlossener Trade, Korrektur — ist eine eigene Zeile. Deshalb lässt sich ein falsch gebuchter Trade rückabwickeln, ohne die Historie zu verlieren.",
          },
          {
            kind: "note",
            tone: "info",
            title: "Freier Trade",
            text: "Ein Trade ohne System ist zulässig. Er taucht in keiner System-Live-Statistik auf, wirkt aber auf den Kontostand — für das, was man außerhalb der Systematik handelt.",
          },
        ],
      },
      {
        id: "fees-snapshot",
        title: "Fees werden eingefroren",
        blocks: [
          {
            kind: "p",
            text: "Beim Berechnen des Risikos werden die geltenden Fees und Größenregeln in das Ticket kopiert. Änderst du die Fees später in den Einstellungen, bleiben bestehende Trades bei den Werten, mit denen sie gerechnet wurden — sonst würde sich die Vergangenheit rückwirkend ändern.",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "ausfuehrung",
    title: "Automatische Ausführung",
    lede: "Was die Plattform selbst platzieren darf — und was ausdrücklich nicht.",
    subsections: [
      {
        id: "modi",
        title: "Zwei erlaubte Modi",
        blocks: [
          {
            kind: "table",
            head: ["Modus", "Verhalten"],
            rows: [
              ["DRY_RUN", "Standard. Order wird berechnet und protokolliert, es wird keine Verbindung geöffnet."],
              ["TESTNET", "Echte Orders gegen das Hyperliquid-Testnet, signiert mit einer eigens erzeugten Testnet-Wallet."],
            ],
          },
          {
            kind: "note",
            tone: "warn",
            title: "Kein Mainnet",
            text: "Dieser Stand handelt kein echtes Geld. Die Verweigerung ist nicht bloß eine Einstellung: es gibt keine Konfiguration, die Mainnet auswählt, keine Mainnet-Adresse im Code — und die Standardinstallation kann überhaupt nichts signieren, weil die Signier-Bibliotheken nicht mitinstalliert werden. Scharfschalten ist eine eigene, bewusste Änderung.",
          },
          {
            kind: "p",
            text: "Marktdaten sind davon nicht betroffen. Kerzen vom öffentlichen Info-Endpunkt zu lesen ist kein Handeln, und ohne echte Kurshistorie gäbe es nichts zu backtesten.",
          },
        ],
      },
      {
        id: "journal",
        title: "Order-Journal",
        blocks: [
          {
            kind: "p",
            text: "Jede erzeugte Order wird festgehalten — auch die simulierten, auch die abgelehnten, auch die, die an einem Fehler gescheitert sind. Der Modus steht in jeder Zeile.",
          },
          {
            kind: "p",
            text: "Simulierte Orders bekommen bewusst keine Börsen-Ordernummer. Eine erfundene Nummer wäre von einer echten nicht zu unterscheiden, und das Journal ist die eine Stelle, die darüber nie im Unklaren sein darf.",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "konzepte-settings",
    title: "Konzepte & Einstellungen",
    lede: "Systematik über den Bestand und die Grundwerte des Live-Trading.",
    subsections: [
      {
        id: "konzepte",
        title: "Konzepte",
        blocks: [
          {
            kind: "p",
            text: "Konzepte sind die Marktideen, auf denen Systeme beruhen — Volume Profile, Order Flow, Funding und so weiter. Die Zuordnung ist n:m und in zwei Ansichten bedienbar: als bipartiter Graph und als Matrix, in der ein Klick auf die Zelle zuordnet oder entfernt.",
          },
          {
            kind: "p",
            text: "Die Vorschau leitet Zuordnungen aus dem Präfix und den Regeltexten ab; bestätigt werden sie einzeln oder gesammelt. Automatisch zugeordnete Verbindungen bleiben als solche erkennbar.",
          },
        ],
      },
      {
        id: "settings",
        title: "Einstellungen",
        blocks: [
          {
            kind: "list",
            items: [
              "Venues: die Handelsplätze. Jeder trägt eigene Asset-Einstellungen.",
              "Asset-Settings: Entry- und Exit-Fee, Lot-Größe, Leverage-Buffer, erlaubte Abweichung nach oben und unten, maximaler Hebel, Mindest-Ordergröße.",
              "Kontostand: aktueller Stand und die vollständige Änderungshistorie.",
            ],
          },
          {
            kind: "note",
            tone: "info",
            title: "Fees sind versioniert",
            text: "„Fees ändern“ legt eine neue Version mit Gültigkeitsdatum an, statt die alte zu überschreiben. Bestehende Trades behalten ihren Snapshot; neue rechnen mit den neuen Werten.",
          },
        ],
      },
    ],
  },

  // ----------------------------------------------------------------- //
  {
    id: "grenzen",
    title: "Grenzen",
    lede: "Was die Plattform nicht tut. Bewusst an dieser Stelle und nicht im Kleingedruckten.",
    subsections: [
      {
        id: "grenzen-liste",
        title: "Bekannte Lücken",
        blocks: [
          {
            kind: "list",
            items: [
              "Kein Mainnet-Handel. Ausführung nur als Dry-Run oder gegen das Testnet.",
              "Die Testnet-Signatur ist noch nicht gegen die echte Börse ausprobiert worden — die erste reale Testnet-Order ist der Abnahmetest.",
              "Kein Alerting, keine Benachrichtigungen. Die Plattform meldet sich nicht von selbst.",
              "Risk-Regeln sind hinterlegbar und lesbar, werden aber nicht gegen laufende Trades geprüft.",
              "Der System-Report liefert JSON, kein PDF.",
              "Sweeps laufen synchron und sind auf 400 Zellen begrenzt.",
              "Der Kerzen-Zwischenspeicher kann „abgefragt und leer“ nicht von „nie abgefragt“ unterscheiden und holt solche Zeiträume erneut.",
            ],
          },
          {
            kind: "note",
            tone: "warn",
            title: "Ein Backtest ist kein Versprechen",
            text: "Die Engine rechnet mit den Kosten, die du hinterlegt hast, füllt zum nächsten Eröffnungskurs und nimmt bei Zweideutigkeit das schlechtere Ergebnis an. Sie kann trotzdem nicht wissen, ob deine Order im echten Buch diese Größe bekommen hätte. Die Live-Ausführungsqualität ist die Zahl, die diese Frage beantwortet.",
          },
        ],
      },
    ],
  },
];
