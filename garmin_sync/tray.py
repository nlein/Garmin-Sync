"""
System-Tray-App.

Drei Hintergrund-Threads:
  • Scheduler   — prüft minütlich; synct auch nach spätem PC-Start nach (B3)
  • Watchdog    — reagiert sofort auf neue JSONs in Garmin_Upload/eingang/
  • Single-Instance-Mutex — verhindert doppelten Tray via Windows-Mutex (🟡1)

Tkinter-Dialoge laufen als separater Subprozess um Thread-Safety-Probleme
mit pystray-Callbacks zu vermeiden (B4).
"""

import ctypes
import logging
import subprocess
import sys
import threading
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional

import pystray
from pystray import Icon, Menu, MenuItem

from .auth import get_client
from .config import Config
from .icons import icon_error, icon_idle, icon_ok, icon_syncing
from .state import SyncState

log = logging.getLogger("garmin_sync")

_MUTEX_NAME = "Global\\GarminSyncTrayApp"


def _acquire_single_instance_mutex() -> Optional[object]:
    """
    Erstellt einen benannten Windows-Mutex. Gibt None zurück wenn eine
    zweite Instanz läuft — dann soll die Tray-App nicht starten.
    """
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, _MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(mutex)
        return None
    return mutex


class TrayApp:
    def __init__(self, config: Config, state: SyncState):
        self.config = config
        self.state = state
        self._icon: Optional[Icon] = None
        self._stop = threading.Event()
        self._sync_lock = threading.Lock()
        self._is_syncing = False
        self._watchdog_observer = None
        self._mutex = None

    # ------------------------------------------------------------------ #
    # Startup                                                              #
    # ------------------------------------------------------------------ #

    def run(self):
        # Single-Instance-Schutz (🟡1)
        self._mutex = _acquire_single_instance_mutex()
        if self._mutex is None:
            log.warning("Zweite Instanz erkannt — beende.")
            return

        self.config.sync_autostart_registry()

        self._icon = Icon(
            "GarminSync",
            icon_idle(),
            title="Garmin Sync — bereit",
            menu=self._build_menu(),
        )

        threading.Thread(target=self._scheduler_loop, daemon=True, name="scheduler").start()
        self._start_watchdog()

        log.info("Tray-App gestartet.")
        self._icon.run()

        # Cleanup
        self._stop.set()
        if self._watchdog_observer:
            self._watchdog_observer.stop()
        if self._mutex:
            ctypes.windll.kernel32.CloseHandle(self._mutex)

    # ------------------------------------------------------------------ #
    # Menu                                                                 #
    # ------------------------------------------------------------------ #

    def _build_menu(self) -> Menu:
        return Menu(
            MenuItem("Garmin Sync", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(self._status_text, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(
                "Jetzt synchronisieren",
                self._on_sync_now,
                enabled=lambda _: not self._is_syncing,
            ),
            MenuItem("Backfill (Historie laden) …", self._on_backfill),
            MenuItem("Neu anmelden …", self._on_login),
            Menu.SEPARATOR,
            MenuItem(
                "Beim Anmelden starten",
                self._on_toggle_autostart,
                checked=lambda _: self.config.autostart,
            ),
            MenuItem("Einstellungen → Ordner ändern …", self._on_folders),
            MenuItem("Ausgabeordner öffnen", self._on_open_export),
            MenuItem("Log öffnen", self._on_open_log),
            Menu.SEPARATOR,
            MenuItem("Info", self._on_info),
            Menu.SEPARATOR,
            MenuItem("Beenden", self._on_quit),
        )

    def _status_text(self, _=None) -> str:
        if self._is_syncing:
            return "Sync läuft …"
        last = self.state.last_sync
        return f"Letzter Sync: {last.strftime('%d.%m. %H:%M')}" if last else "Noch kein Sync"

    # ------------------------------------------------------------------ #
    # Icon                                                                 #
    # ------------------------------------------------------------------ #

    def _set_status(self, status: str):
        if not self._icon:
            return
        if status == "ok":
            self._icon.icon = icon_ok()
            self._icon.title = f"Garmin Sync — OK ({datetime.now().strftime('%H:%M')})"
        elif status == "error":
            self._icon.icon = icon_error()
            self._icon.title = "Garmin Sync — Fehler (Rechtsklick für Details)"
        elif status == "syncing":
            self._icon.icon = icon_syncing()
            self._icon.title = "Garmin Sync — Synchronisierung läuft …"
        else:
            self._icon.icon = icon_idle()
            self._icon.title = "Garmin Sync — bereit"

    # ------------------------------------------------------------------ #
    # Core sync runner                                                     #
    # ------------------------------------------------------------------ #

    def _run_sync(self, backfill_days: Optional[int] = None, upload_only: bool = False):
        if not self._sync_lock.acquire(blocking=False):
            log.info("Sync läuft bereits — überspringe.")
            return

        self._is_syncing = True
        self._set_status("syncing")
        try:
            api = get_client()
            if not api:
                log.error("Nicht angemeldet — bitte 'Neu anmelden' wählen.")
                self._set_status("error")
                return

            from .report import ReportWriter
            from .state import SyncState
            from .sync import GarminSync
            from .upload import GarminUpload

            state = SyncState(self.config.export_dir / "sync_state.json")
            new_acts, errors, success = [], [], True

            if not upload_only:
                syncer = GarminSync(self.config, state, api)
                success = syncer.run(backfill_days=backfill_days)
                new_acts = syncer.new_activities
                errors = syncer.errors

            uploader = GarminUpload(self.config, api)
            upload_results = uploader.process()

            ReportWriter(self.config.export_dir).write(
                success, new_acts, errors, upload_results,
                upload_only=upload_only,
            )

            self.state = SyncState(self.config.export_dir / "sync_state.json")
            self._set_status("ok" if success else "error")

        except Exception as exc:
            log.error("Unerwarteter Sync-Fehler: %s", exc)
            self._set_status("error")
        finally:
            self._is_syncing = False
            self._sync_lock.release()

    # ------------------------------------------------------------------ #
    # Scheduler (täglicher Sync mit Catch-up, B3)                         #
    # ------------------------------------------------------------------ #

    def _scheduler_loop(self):
        while not self._stop.wait(60):
            now = datetime.now()
            h, m = map(int, self.config.sync_time.split(":"))
            sync_time = dt_time(h, m)

            # Catch-up: sync wenn heute noch nicht gelaufen UND Sync-Zeit bereits vorbei
            if (
                self.state.last_sync_date != now.date()
                and now.time() >= sync_time
                and not self._is_syncing
            ):
                log.info("Tagesync fällig (jetzt %s, Ziel %s) — starte.", now.strftime("%H:%M"), self.config.sync_time)
                threading.Thread(target=self._run_sync, daemon=True, name="scheduled-sync").start()

    # ------------------------------------------------------------------ #
    # Watchdog (file-based, inbox)                                         #
    # ------------------------------------------------------------------ #

    def _start_watchdog(self):
        from .upload import start_inbox_watcher

        def _on_new_file(path: Path):
            threading.Thread(
                target=self._run_sync,
                kwargs={"upload_only": True},
                daemon=True,
                name="watchdog-upload",
            ).start()

        try:
            self._watchdog_observer = start_inbox_watcher(
                self.config.upload_dir / "eingang", _on_new_file
            )
        except Exception as exc:
            log.warning("Watchdog konnte nicht gestartet werden: %s", exc)

    # ------------------------------------------------------------------ #
    # Subprocess-Helpers für tkinter-Dialoge (B4)                         #
    # tkinter ist nicht threadsicher; alle GUI-Dialoge laufen daher als   #
    # eigener Prozess mit eigener main()-Thread-Tkinter-Instanz.          #
    # ------------------------------------------------------------------ #

    def _get_exe_args(self) -> list[str]:
        """Basisargumente für Subprozess-Start (dev: python main.py / .exe: self)."""
        if getattr(sys, "frozen", False):
            return [sys.executable]
        return [sys.executable, str(Path(__file__).parent.parent / "main.py")]

    # ------------------------------------------------------------------ #
    # Menu-Aktionen                                                        #
    # ------------------------------------------------------------------ #

    def _on_sync_now(self, icon, item):
        threading.Thread(target=self._run_sync, daemon=True, name="manual-sync").start()

    def _on_backfill(self, icon, item):
        # Dialog in separatem Prozess → gibt Tage als Text auf stdout aus
        args = self._get_exe_args() + ["--dialog-backfill"]
        result = subprocess.run(args, capture_output=True, text=True)
        stdout = result.stdout.strip()
        if stdout.isdigit():
            days = int(stdout)
            threading.Thread(
                target=self._run_sync,
                kwargs={"backfill_days": days},
                daemon=True,
                name="backfill-sync",
            ).start()

    def _on_login(self, icon, item):
        # Login in separatem Prozess (tkinter braucht main-Thread)
        subprocess.Popen(self._get_exe_args() + ["login"])

    def _on_toggle_autostart(self, icon, item):
        self.config.autostart = not self.config.autostart
        log.info("Autostart %s.", "aktiviert" if self.config.autostart else "deaktiviert")

    def _on_folders(self, icon, item):
        import json
        args = self._get_exe_args() + ["--dialog-folders"]
        result = subprocess.run(args, capture_output=True, text=True)
        stdout = result.stdout.strip()
        if stdout:
            try:
                data = json.loads(stdout)
                self.config.export_dir = Path(data["export"])
                self.config.upload_dir = Path(data["upload"])
                log.info("Ordner geändert: Export=%s Upload=%s", data["export"], data["upload"])
                icon.notify(
                    f"Export: {data['export']}\nUpload: {data['upload']}\n\nWatchdog-Pfad wird nach Neustart aktualisiert.",
                    "Garmin Sync — Ordner gespeichert",
                )
            except Exception as exc:
                log.warning("Ordner-Dialog Fehler: %s", exc)

    def _on_open_export(self, icon, item):
        d = self.config.export_dir
        d.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(d)])

    def _on_open_log(self, icon, item):
        log_path = self.config.export_dir / "sync.log"
        if log_path.exists():
            subprocess.Popen(["notepad", str(log_path)])
        else:
            icon.notify("Noch keine Log-Datei vorhanden.", "Garmin Sync")

    def _on_info(self, icon, item):
        # Popup in separatem Prozess — Freeze-sicher (tkinter braucht main-Thread)
        subprocess.Popen(self._get_exe_args() + ["_about"])

    def _on_quit(self, icon, item):
        self._stop.set()
        icon.stop()
