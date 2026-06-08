# garmin-sync

Lokales Windows-Tool, das täglich Trainings- und Gesundheitsdaten aus **Garmin Connect** exportiert und selbst erstellte Workouts dorthin hochlädt — inklusive Einplanung im Garmin-Kalender.

Läuft als **System-Tray-App** im Hintergrund — das lila Icon mit Pulszeichen wechselt die Farbe je nach Status: grün = OK, orange = läuft, rot = Fehler, grau = bereit.

> **Inoffizielle API** — dieses Tool verwendet die inoffizielle Garmin-Connect-API über [python-garminconnect](https://github.com/cyberjunky/python-garminconnect). Es besteht keine Verbindung zu Garmin Ltd. Nutzung auf eigene Gefahr.

---

## Voraussetzungen

- Windows 10 / 11
- Python 3.11 oder neuer → [python.org/downloads](https://www.python.org/downloads/)

---

## Einrichtung (einmalig)

### 1. Virtuelle Umgebung anlegen und Abhängigkeiten installieren

```powershell
cd "C:\Pfad\zu\garmin-sync"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Einmalig bei Garmin anmelden

```powershell
python main.py login
```

Es öffnen sich Dialoge für E-Mail, Passwort und (falls eingerichtet) den MFA-Code.  
Der Token wird lokal in `%USERPROFILE%\.garminconnect\` gespeichert — **niemals im Repo** und **nicht in der Cloud**.

### 3. App starten

```powershell
python main.py
```

Beim ersten Start erscheint ein Dialog zur Ordnerwahl (Export- und Upload-Ordner).  
Das Tray-Icon erscheint danach in der Windows-Taskleiste (ggf. im versteckten Bereich).  
Rechtsklick öffnet das Menü.

---

## Tray-Menü

| Eintrag | Funktion |
|---|---|
| **Jetzt synchronisieren** | Sofortiger Export aller neuen Daten |
| **Backfill (Historie laden) …** | Dialog: Anzahl Tage eingeben → lädt die komplette Historie |
| **Neu anmelden …** | Login-Dialoge, falls der Token abgelaufen ist |
| **Beim Anmelden starten** | Autostart ein/aus (Registry `HKCU\…\Run`) |
| **Einstellungen → Ordner ändern …** | Export- und Upload-Ordner neu wählen |
| **Ausgabeordner öffnen** | Öffnet den Export-Ordner im Explorer |
| **Log öffnen** | Öffnet `sync.log` in Notepad |
| **Info** | Öffnet ein Popup mit Version, Lizenz und klickbarem GitHub-Link |
| **Beenden** | App beenden |

---

## Erste Historiensicherung (Backfill)

Um vergangene Daten nachzuladen:

```powershell
python main.py sync --backfill 365
```

Oder über das Tray-Menü → **Backfill (Historie laden) …** → gewünschte Anzahl Tage eingeben.  
Dauert je nach Umfang **mehrere Stunden** (API-Rate-Limiting, ~7 Wellness-Endpunkte × Tage).  
Der PC darf dabei in den Schlafmodus — die App holt beim nächsten Start nahtlos weiter.

---

## Täglicher automatischer Sync

Der Standard-Sync läuft täglich um **07:00 Uhr**, wenn die App gestartet ist.  
Aktiviere **Beim Anmelden starten** im Tray-Menü, damit die App nach dem Windows-Login automatisch läuft.

Für einen harten Scheduler ohne laufende Tray-App:

```powershell
schtasks /Create /TN "GarminSync" /TR "\"C:\Pfad\.venv\Scripts\pythonw.exe\" \"C:\Pfad\main.py\" sync" /SC DAILY /ST 07:00 /F
```

---

## Workout-Upload (Schreib-Richtung)

Workout-JSONs in den `eingang\`-Ordner legen.  
Der **Watchdog** erkennt neue Dateien sofort und löst den Upload automatisch aus —  
kein Warten bis zum nächsten geplanten Sync.

Format einer Workout-Datei:

```json
{
  "name": "Qualität 3×8 min",
  "sport": "running",
  "schedule_date": "2026-06-15",
  "steps": [
    {"type": "warmup",   "duration_min": 10, "target": {"hr_bpm": [95, 120]}},
    {"type": "repeat", "count": 3, "steps": [
      {"type": "interval", "duration_min": 8,  "target": {"hr_bpm": [137, 146]}},
      {"type": "recovery", "duration_min": 2,  "target": {"hr_bpm": [0, 130]}}
    ]},
    {"type": "cooldown", "duration_min": 10, "target": {"hr_bpm": [95, 120]}}
  ]
}
```

Targets: `hr_bpm`, `pace_min_km` (z. B. `["6:35", "6:20"]`), oder weglassen für offen.

---

## CLI-Befehle

```powershell
python main.py login                          # Token speichern
python main.py sync [--backfill TAGE]         # Sync (optional: Historie nachladen)
python main.py upload                         # Workout-JSONs aus Eingang hochladen
python main.py status                         # Token-Status und Sync-Übersicht
python main.py config                         # Einstellungen anzeigen
python main.py config --export-dir PFAD       # Export-Ordner setzen
python main.py config --upload-dir PFAD       # Upload-Ordner setzen
python main.py config --sync-time HH:MM       # Tägliche Sync-Zeit setzen
```

---

## Als .exe bauen (optional)

```powershell
.venv\Scripts\activate
pyinstaller build.spec
```

Die fertige `dist\garmin-sync.exe` läuft ohne Python-Installation.

> **Hinweis:** CLI-Befehle (`garmin-sync.exe status` etc.) zeigen in der .exe keine Konsolenausgabe  
> (console=False). Für CLI-Nutzung: `python main.py login` etc. aus einem Terminal-Fenster.

---

## Verzeichnisstruktur (Output)

Standard-Pfade (beim Erststart wählbar, danach über Menü oder CLI änderbar):

```
%USERPROFILE%\GarminSync\Export\
├── LETZTER_SYNC.md          ← Sync-Bericht (von Claude lesbar)
├── sync_state.json          ← inkrementeller Zustand (gitignored)
├── sync.log
├── profil\
├── aktivitaeten\
│   └── 2026-06-07_12345_Langer-Lauf\
│       ├── summary.json
│       ├── details.json
│       ├── splits.json
│       ├── hf_zonen.json
│       ├── wetter.json
│       └── original.fit
├── wellness\
│   └── 2026-06-07.json
├── status\
└── kalender\

%USERPROFILE%\GarminSync\Upload\
├── eingang\     ← Workout-JSONs hier ablegen
├── erledigt\
└── fehler\
```

---

## Datenschutz / Sicherheit

- Kein Passwort wird gespeichert — nur der garth-OAuth-Token in `%USERPROFILE%\.garminconnect\` (lokal, ~1 Jahr gültig)
- Keine Cloud-Uploads, keine Telemetrie
- Das Tool **löscht keine** Workouts, Termine oder Aktivitäten in Garmin Connect — nur anlegen und aktualisieren
- `.gitignore` schließt Token, Logs, `sync_state.json` und `settings.json` aus

---

## Bekannte Einschränkungen

- **Windows only** — pystray und die Registry-Integration setzen Windows 10/11 voraus
- **Benutzeroberfläche auf Deutsch** — keine Mehrsprachigkeit
- **Inoffizielle Garmin-API** — Garmin kann Endpunkte jederzeit ändern oder sperren; dann funktionieren betroffene Sync-Bereiche nicht mehr
- **Rate-Limiting (429)** — Bei vielen Anfragen in kurzer Zeit kann Garmin die Verbindung temporär sperren; einfach später erneut versuchen
- **MFA erforderlich** — Falls für den Garmin-Account aktiviert, muss beim Login einmalig der Code eingegeben werden

---

## Haftungsausschluss

Dieses Projekt ist **nicht mit Garmin Ltd. verbunden** und wird weder von Garmin unterstützt noch offiziell anerkannt. Es nutzt eine inoffizielle, reverse-engineerte API. Nutzung auf eigenes Risiko. Zugangsdaten werden ausschließlich lokal gespeichert.

---

## Credits

- [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) von [cyberjunky](https://github.com/cyberjunky) — MIT-Lizenz
- [garth](https://github.com/matin/garth) von [matin](https://github.com/matin) — MIT-Lizenz

---

## Lizenz

[MIT](LICENSE)
