"""
garmin-sync  —  Einstiegspunkt

Ohne Argumente: startet die System-Tray-App.
Mit Argumenten:  CLI-Modus (login, sync, upload, status, config).
--dialog-backfill: interner Subprocess-Aufruf für Backfill-Tage-Dialog.
--dialog-folders:  interner Subprocess-Aufruf für Ordner-Auswahl-Dialog.
"""

import sys
from pathlib import Path
from garmin_sync.config import Config
from garmin_sync.logger_setup import setup_logger

config = Config()
log = setup_logger(config.export_dir / "sync.log")

# Interner Subprocess-Aufruf: Backfill-Dialog anzeigen, Tage auf stdout schreiben
if sys.argv[1:] == ["--dialog-backfill"]:
    import tkinter as tk
    from tkinter import simpledialog
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    days = simpledialog.askinteger(
        "Backfill",
        "Wie viele Tage zurück laden?\n(z. B. 365 für ein Jahr Historie)",
        minvalue=1,
        maxvalue=1000,
        parent=root,
    )
    root.destroy()
    if days:
        print(days)
    sys.exit(0)

# Interner Subprocess-Aufruf: Ordner-Dialog, Pfade als JSON auf stdout schreiben
elif sys.argv[1:] == ["--dialog-folders"]:
    import json
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    messagebox.showinfo(
        "Garmin Sync — Ordner wählen",
        "Bitte wähle den Export-Ordner (lokale Datensicherung).",
        parent=root,
    )
    export_dir = filedialog.askdirectory(
        title="Export-Ordner wählen",
        initialdir=str(config.export_dir.parent),
        parent=root,
    )
    upload_dir = None
    if export_dir:
        messagebox.showinfo(
            "Garmin Sync — Ordner wählen",
            "Jetzt den Upload-Ordner (Workout-JSON-Eingang).",
            parent=root,
        )
        upload_dir = filedialog.askdirectory(
            title="Upload-Ordner wählen",
            initialdir=str(config.upload_dir.parent),
            parent=root,
        )
    root.destroy()
    if export_dir and upload_dir:
        print(json.dumps({"export": export_dir, "upload": upload_dir}))
    sys.exit(0)

elif len(sys.argv) > 1:
    from garmin_sync.cli import run_cli
    run_cli()

else:
    from garmin_sync.state import SyncState
    from garmin_sync.tray import TrayApp

    # Erststart: Ordner-Dialog im Hauptthread (tkinter ist main-thread-only)
    if config.first_run:
        import tkinter as tk
        from tkinter import filedialog, messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(
            "Garmin Sync — Erststart",
            f"Willkommen!\n\nBitte wähle einen Export-Ordner für die lokale Datensicherung.\n\nStandard: {config.export_dir}",
        )
        chosen_export = filedialog.askdirectory(
            title="Export-Ordner wählen",
            initialdir=str(config.export_dir.parent),
        )
        if chosen_export:
            config.export_dir = Path(chosen_export)

        messagebox.showinfo(
            "Garmin Sync — Erststart",
            f"Jetzt den Upload-Ordner für Workout-JSONs wählen.\n\nStandard: {config.upload_dir}",
        )
        chosen_upload = filedialog.askdirectory(
            title="Upload-Ordner wählen",
            initialdir=str(config.upload_dir.parent),
        )
        if chosen_upload:
            config.upload_dir = Path(chosen_upload)

        config.save()  # Schreibt settings.json → first_run bei nächstem Start false
        root.destroy()

    state = SyncState(config.export_dir / "sync_state.json")
    TrayApp(config, state).run()
