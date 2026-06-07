import json
import sys
import winreg
from pathlib import Path

APPDATA = Path.home() / "AppData" / "Roaming" / "GarminSync"
SETTINGS_FILE = APPDATA / "settings.json"
APP_NAME = "GarminSync"
_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

_DEFAULTS = {
    "autostart": False,
    "sync_time": "07:00",
    "export_dir": str(Path.home() / "GarminSync" / "Export"),
    "upload_dir": str(Path.home() / "GarminSync" / "Upload"),
}


class Config:
    def __init__(self):
        self._data = {**_DEFAULTS}
        self._first_run = not SETTINGS_FILE.exists()
        self._load()

    def _load(self):
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    self._data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        APPDATA.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    @property
    def first_run(self) -> bool:
        """True wenn noch keine settings.json existiert (erster Start)."""
        return self._first_run

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    @property
    def autostart(self) -> bool:
        return self._data.get("autostart", False)

    @autostart.setter
    def autostart(self, value: bool):
        self._data["autostart"] = value
        self.save()
        self._apply_autostart(value)

    @property
    def sync_time(self) -> str:
        return self._data.get("sync_time", "07:00")

    @property
    def export_dir(self) -> Path:
        return Path(self._data["export_dir"])

    @export_dir.setter
    def export_dir(self, value: Path):
        self._data["export_dir"] = str(value)
        self.save()

    @property
    def upload_dir(self) -> Path:
        return Path(self._data["upload_dir"])

    @upload_dir.setter
    def upload_dir(self, value: Path):
        self._data["upload_dir"] = str(value)
        self.save()

    def _apply_autostart(self, enable: bool):
        if sys.platform != "win32":
            return
        if getattr(sys, "frozen", False):
            exe_cmd = f'"{sys.executable}"'
        else:
            exe_cmd = f'"{sys.executable}" "{Path(__file__).parent.parent / "main.py"}"'
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enable:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_cmd)
                else:
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError:
                        pass
        except Exception:
            pass

    def sync_autostart_registry(self):
        self._apply_autostart(self.autostart)
