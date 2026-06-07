import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Set


class SyncState:
    def __init__(self, state_file: Path):
        self._file = state_file
        self._data: dict = {
            "synced_activity_ids": [],
            "last_sync": None,
            "last_sync_date": None,
            "last_wellness_date": None,
        }
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                with open(self._file, encoding="utf-8") as f:
                    self._data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    # --- Activities ---

    @property
    def synced_ids(self) -> Set[int]:
        return set(self._data.get("synced_activity_ids", []))

    def mark_activity_synced(self, activity_id: int):
        ids = self._data.setdefault("synced_activity_ids", [])
        if activity_id not in ids:
            ids.append(activity_id)
        self.save()

    # --- Sync timestamps ---

    @property
    def last_sync(self) -> Optional[datetime]:
        val = self._data.get("last_sync")
        return datetime.fromisoformat(val) if val else None

    @last_sync.setter
    def last_sync(self, value: datetime):
        self._data["last_sync"] = value.isoformat()
        self._data["last_sync_date"] = value.date().isoformat()
        self.save()

    @property
    def last_sync_date(self) -> Optional[date]:
        val = self._data.get("last_sync_date")
        return date.fromisoformat(val) if val else None

    @property
    def last_wellness_date(self) -> Optional[date]:
        val = self._data.get("last_wellness_date")
        return date.fromisoformat(val) if val else None

    @last_wellness_date.setter
    def last_wellness_date(self, value: date):
        self._data["last_wellness_date"] = value.isoformat()
        self.save()

    # --- Generic extras (profile sync date, etc.) ---

    def get_extra(self, key: str, default=None):
        return self._data.get(key, default)

    def set_extra(self, key: str, value):
        self._data[key] = value
        self.save()
