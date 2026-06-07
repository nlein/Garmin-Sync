"""
Export-Logik: Aktivitäten, Wellness, Status, Profil, Kalender.

Methodennamen gegen garminconnect-Demo verifiziert (Stand 0.2.22).
_safe() schluckt Exceptions — nach Änderungen immer prüfen ob die
jeweiligen JSON-Dateien wirklich befüllt werden!
"""

import io
import json
import logging
import re
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("garmin_sync")


def _sanitize(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", name)[:80].strip("-")


def _safe(fn, *args, label: str = "", **kwargs) -> Any:
    """Ruft fn(*args) auf; loggt Fehler und gibt None zurück — nie fatal."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        log.warning("API [%s]: %s", label or fn.__name__, exc)
        return None


def _write_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


class GarminSync:
    def __init__(self, config, state, api):
        self.config = config
        self.state = state
        self.api = api
        self.export_dir: Path = config.export_dir
        self.new_activities: list[dict] = []
        self.errors: list[str] = []

    def run(self, backfill_days: Optional[int] = None) -> bool:
        log.info("Sync gestartet%s.", f" (Backfill {backfill_days} Tage)" if backfill_days else "")
        core_ok = True

        try:
            self._sync_activities(backfill_days)
        except Exception as exc:
            log.error("Aktivitäten-Sync fehlgeschlagen: %s", exc)
            self.errors.append(f"Aktivitäten: {exc}")
            core_ok = False

        for name, fn in [
            ("Wellness",  lambda: self._sync_wellness(backfill_days)),
            ("Status",    self._sync_status),
            ("Profil",    self._sync_profile_if_due),
            ("Kalender",  self._sync_calendar),
        ]:
            try:
                fn()
            except Exception as exc:
                log.warning("%s-Sync fehlgeschlagen: %s", name, exc)
                self.errors.append(f"{name}: {exc}")

        if core_ok:
            self.state.last_sync = datetime.now()
        return core_ok

    # ------------------------------------------------------------------ #
    # Aktivitäten                                                          #
    # ------------------------------------------------------------------ #

    def _sync_activities(self, backfill_days: Optional[int]):
        if backfill_days:
            cutoff = date.today() - timedelta(days=backfill_days)
        elif self.state.last_sync:
            cutoff = self.state.last_sync.date() - timedelta(days=7)
        else:
            cutoff = date.today() - timedelta(days=14)

        log.info("Aktivitäten ab %s …", cutoff)
        synced_ids = self.state.synced_ids
        offset, page = 0, 50

        while True:
            batch = _safe(self.api.get_activities, offset, page, label="get_activities") or []
            if not batch:
                break
            reached_cutoff = False
            for act in batch:
                ts = act.get("startTimeLocal", "")
                act_date = date.fromisoformat(ts[:10]) if len(ts) >= 10 else date.today()
                if act_date < cutoff:
                    reached_cutoff = True
                    break
                if act.get("activityId") not in synced_ids:
                    self._save_activity(act)
                    time.sleep(1.5)
            if reached_cutoff or len(batch) < page:
                break
            offset += page
            time.sleep(2)

    def _save_activity(self, act: dict):
        act_id = act["activityId"]
        ts = act.get("startTimeLocal", "")
        date_str = ts[:10] if len(ts) >= 10 else "0000-00-00"
        name = _sanitize(act.get("activityName") or "Aktivitaet")
        act_dir = self.export_dir / "aktivitaeten" / f"{date_str}_{act_id}_{name}"
        act_dir.mkdir(parents=True, exist_ok=True)
        log.info("Speichere %s …", act_id)

        _write_json(act_dir / "summary.json", act)

        for label, fn, fname in [
            ("get_activity_details",         lambda: self.api.get_activity_details(act_id),         "details.json"),
            ("get_activity_splits",          lambda: self.api.get_activity_splits(act_id),          "splits.json"),
            ("get_activity_hr_in_timezones", lambda: self.api.get_activity_hr_in_timezones(act_id), "hf_zonen.json"),
            ("get_activity_weather",         lambda: self.api.get_activity_weather(act_id),         "wetter.json"),
        ]:
            data = _safe(fn, label=label)
            if data:
                _write_json(act_dir / fname, data)
            time.sleep(1)

        # FIT-Datei (als ZIP, .fit extrahieren)
        try:
            from garminconnect import Garmin
            raw = self.api.download_activity(act_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            if raw:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    for n in zf.namelist():
                        if n.lower().endswith(".fit"):
                            (act_dir / "original.fit").write_bytes(zf.read(n))
                            break
        except Exception as exc:
            log.warning("FIT-Download fehlgeschlagen [%s]: %s", act_id, exc)
        time.sleep(1.5)

        self.state.mark_activity_synced(act_id)
        self.new_activities.append(act)

    # ------------------------------------------------------------------ #
    # Wellness                                                             #
    # ------------------------------------------------------------------ #

    def _sync_wellness(self, backfill_days: Optional[int]):
        if backfill_days:
            start = date.today() - timedelta(days=backfill_days)
        elif self.state.last_wellness_date:
            start = self.state.last_wellness_date - timedelta(days=1)
        else:
            start = date.today() - timedelta(days=7)

        current = start
        while current <= date.today():
            cdate = current.isoformat()
            wellness: dict = {}

            # Korrekte Methodennamen laut garminconnect 0.2.x demo.py:
            for key, fn in [
                ("schlaf",             lambda d=cdate: self.api.get_sleep_data(d)),
                ("hrv",                lambda d=cdate: self.api.get_hrv_data(d)),
                ("herzfrequenz",       lambda d=cdate: self.api.get_heart_rates(d)),
                ("body_battery",       lambda d=cdate: self.api.get_body_battery(d, d)),
                ("stress",             lambda d=cdate: self.api.get_stress_data(d)),
                ("training_readiness", lambda d=cdate: self.api.get_training_readiness(d)),
                # get_steps_data(cdate) — nicht get_daily_step_count
                ("schritte",           lambda d=cdate: self.api.get_steps_data(d)),
            ]:
                data = _safe(fn, label=key)
                if data:
                    wellness[key] = data
                time.sleep(0.8)

            if wellness:
                _write_json(self.export_dir / "wellness" / f"{cdate}.json", wellness)

            self.state.last_wellness_date = current
            current += timedelta(days=1)
            time.sleep(1)

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    def _sync_status(self):
        status_dir = self.export_dir / "status"
        today = date.today().isoformat()

        # get_training_status(cdate) — braucht Datum-Argument
        data = _safe(self.api.get_training_status, today, label="get_training_status")
        if data:
            _write_json(status_dir / "training_status.json", data)
        time.sleep(1)

        # get_max_metrics(cdate) — VO2max-Verlauf
        data = _safe(self.api.get_max_metrics, today, label="get_max_metrics")
        if data:
            _write_json(status_dir / "vo2max_verlauf.json", data)
        time.sleep(1)

        # get_race_predictions() — laut garminconnect demo
        data = _safe(self.api.get_race_predictions, label="get_race_predictions")
        if data:
            _write_json(status_dir / "rennprognosen.json", data)
        time.sleep(1)

    # ------------------------------------------------------------------ #
    # Profil (1×/Woche)                                                   #
    # ------------------------------------------------------------------ #

    def _sync_profile_if_due(self):
        last = self.state.get_extra("last_profile_sync")
        if last and (date.today() - date.fromisoformat(last)).days < 7:
            return

        profile_dir = self.export_dir / "profil"

        profile = _safe(self.api.get_user_profile, label="get_user_profile")
        if profile:
            _write_json(profile_dir / "user_profile.json", profile)
        time.sleep(1)

        devices = _safe(self.api.get_devices, label="get_devices")
        if devices:
            _write_json(profile_dir / "geraete.json", devices)
        time.sleep(1)

        # get_gear(displayName) — erwartet userProfileNumber aus get_device_last_used()
        # nicht profile["userId"]. Erst userProfileNumber holen, dann Gear abrufen.
        profile_num = None
        dev_info = _safe(self.api.get_device_last_used, label="get_device_last_used")
        if dev_info and isinstance(dev_info, dict):
            profile_num = dev_info.get("userProfileNumber") or dev_info.get("deviceId")
        if profile_num is None and isinstance(profile, dict):
            profile_num = profile.get("displayName") or profile.get("userId")
        if profile_num:
            gear = _safe(self.api.get_gear, profile_num, label="get_gear")
            if gear:
                _write_json(profile_dir / "ausruestung.json", gear)
        time.sleep(1)

        self.state.set_extra("last_profile_sync", date.today().isoformat())

    # ------------------------------------------------------------------ #
    # Kalender (geplante Workouts, nächste 4 Wochen)                      #
    # ------------------------------------------------------------------ #

    def _sync_calendar(self):
        # get_workout_calendar existiert möglicherweise nicht — Fallback auf connectapi
        cal_dir = self.export_dir / "kalender"
        today = date.today()
        planned: list = []
        seen_weeks: set = set()

        for delta in range(0, 29, 7):
            target = today + timedelta(days=delta)
            iso = target.isocalendar()
            week_key = (iso[0], iso[1])
            if week_key in seen_weeks:
                continue
            seen_weeks.add(week_key)

            # get_workout_calendar existiert in 0.3.x nicht — direkt connectapi
            data = _safe(
                self.api.connectapi,
                f"/calendar-service/year/{iso[0]}/month/{target.month - 1}",
                label="calendar-service",
            )
            if data:
                planned.extend(data if isinstance(data, list) else [data])
            time.sleep(1)

        if planned:
            _write_json(cal_dir / "geplante_workouts.json", planned)
