"""
Workout-Upload nach Garmin Connect + Watchdog für die Eingangs-Inbox.

Watchdog beobachtet Garmin_Upload/eingang/ und löst den Upload sofort aus,
wenn Claude dort eine neue JSON-Datei ablegt — kein Warten bis zum nächsten
geplanten Sync-Lauf.

Garmin-Workout-Format:
  Jeder Step braucht "type": "ExecutableStepDTO" (normale Steps) oder
  "type": "RepeatGroupDTO" (Wiederholungsgruppen). Repeat-Gruppen enthalten
  ihre Kind-Steps in "workoutSteps" (verschachtelt, nicht flach).
"""

import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("garmin_sync")

# ------------------------------------------------------------------ #
# Format-Tabellen                                                      #
# ------------------------------------------------------------------ #

_SPORT_TYPES = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running"},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling"},
    "swimming": {"sportTypeId": 5, "sportTypeKey": "lap_swimming"},
}

_STEP_TYPES = {
    "warmup":   {"stepTypeId": 1, "stepTypeKey": "warmup"},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown"},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval"},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery"},
    "rest":     {"stepTypeId": 5, "stepTypeKey": "rest"},
    "other":    {"stepTypeId": 7, "stepTypeKey": "other"},
}


def _pace_to_ms(pace_str: str) -> float:
    """'6:35' min/km → m/s."""
    m, s = pace_str.strip().split(":")
    return 1000.0 / (int(m) * 60 + int(s))


def _build_target(target: dict) -> dict:
    """Übersetzt vereinfachtes Target-Dict in Garmin-Workout-Felder."""
    if "hr_bpm" in target:
        lo, hi = target["hr_bpm"]
        return {
            "targetType": {
                "workoutTargetTypeId": 4,
                "workoutTargetTypeKey": "heart.rate.zone",
            },
            "targetValueOne": float(lo),
            "targetValueTwo": float(hi),
        }
    if "pace_min_km" in target:
        speeds = sorted(_pace_to_ms(p) for p in target["pace_min_km"])
        return {
            "targetType": {
                "workoutTargetTypeId": 6,
                "workoutTargetTypeKey": "pace.zone",
            },
            "targetValueOne": speeds[0],
            "targetValueTwo": speeds[1],
        }
    return {
        "targetType": {
            "workoutTargetTypeId": 1,
            "workoutTargetTypeKey": "no.target",
        },
        "targetValueOne": None,
        "targetValueTwo": None,
    }


def _translate_steps(steps: list, order: int = 1) -> tuple[list, int]:
    """
    Übersetzt das vereinfachte Steps-Schema ins Garmin-Format.

    Gibt (garmin_steps, nächste_order) zurück.
    Repeat-Gruppen enthalten ihre Kind-Steps verschachtelt in "workoutSteps".
    Alle stepOrder-Werte sind global eindeutig (auch über Verschachtelung hinweg).
    """
    result = []
    for step in steps:
        stype = step.get("type", "other")

        if stype == "repeat":
            my_order = order
            order += 1
            children, order = _translate_steps(step.get("steps", []), order)
            result.append({
                "type": "RepeatGroupDTO",
                "stepOrder": my_order,
                "numberOfIterations": step.get("count", 1),
                "endCondition": {
                    "conditionTypeId": 7,
                    "conditionTypeKey": "iterations",
                },
                "endConditionValue": step.get("count", 1),
                "workoutSteps": children,        # verschachtelt, nicht flach
            })
        else:
            duration_s = int(step.get("duration_min", 5) * 60)
            result.append({
                "type": "ExecutableStepDTO",     # Pflicht-Discriminator
                "stepOrder": order,
                "stepType": _STEP_TYPES.get(stype, _STEP_TYPES["other"]),
                "endCondition": {
                    "conditionTypeId": 2,
                    "conditionTypeKey": "time",
                },
                "endConditionValue": duration_s,
                **_build_target(step.get("target", {})),
            })
            order += 1

    return result, order


def translate_to_garmin_workout(wjson: dict) -> dict:
    sport = wjson.get("sport", "running")
    sport_type = _SPORT_TYPES.get(sport, _SPORT_TYPES["running"])
    steps, _ = _translate_steps(wjson.get("steps", []))
    return {
        "workoutName": wjson["name"],
        "description": wjson.get("description", ""),
        "sportType": sport_type,
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": sport_type,
            "workoutSteps": steps,
        }],
    }


# ------------------------------------------------------------------ #
# Uploader                                                             #
# ------------------------------------------------------------------ #

class GarminUpload:
    def __init__(self, config, api):
        self.config = config
        self.api = api
        self.inbox: Path = config.upload_dir / "eingang"
        self.done_dir: Path = config.upload_dir / "erledigt"
        self.error_dir: Path = config.upload_dir / "fehler"
        for d in (self.inbox, self.done_dir, self.error_dir):
            d.mkdir(parents=True, exist_ok=True)

    def process(self) -> list[dict]:
        results = []
        for jf in sorted(self.inbox.glob("*.json")):
            results.append(self._process_file(jf))
            time.sleep(2)
        return results

    def _process_file(self, path: Path) -> dict:
        log.info("Upload: %s", path.name)
        try:
            with open(path, encoding="utf-8") as f:
                wjson = json.load(f)

            payload = translate_to_garmin_workout(wjson)
            existing_id = self._find_existing(wjson["name"])

            if existing_id:
                log.info("Aktualisiere '%s' (ID %s) …", wjson["name"], existing_id)
                # garminconnect 0.3.x: connectapi() kann nur GET — PUT direkt über garth
                self.api.garth.put(
                    "connectapi",
                    f"/workout-service/workout/{existing_id}",
                    json=payload,
                    api=True,
                )
                workout_id = existing_id
            else:
                log.info("Erstelle '%s' …", wjson["name"])
                resp = self.api.upload_workout(payload)  # offizielle 0.3.x-Methode
                if hasattr(resp, "json"):
                    resp = resp.json()
                workout_id = resp.get("workoutId") if isinstance(resp, dict) else None

            if workout_id and wjson.get("schedule_date"):
                log.info("Plane %s für %s …", workout_id, wjson["schedule_date"])
                self.api.schedule_workout(workout_id, wjson["schedule_date"])

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.move(str(path), str(self.done_dir / f"{ts}_{path.name}"))
            log.info("Upload OK: %s", path.name)
            return {"file": path.name, "status": "ok", "workout_id": workout_id}

        except Exception as exc:
            log.error("Upload fehlgeschlagen [%s]: %s", path.name, exc)
            shutil.move(str(path), str(self.error_dir / path.name))
            (self.error_dir / f"{path.stem}.error.txt").write_text(str(exc), encoding="utf-8")
            return {"file": path.name, "status": "error", "error": str(exc)}

    def _find_existing(self, name: str) -> Optional[int]:
        try:
            workouts = self.api.get_workouts()  # 0.3.x: offizielle Methode statt connectapi
            if isinstance(workouts, list):
                for w in workouts:
                    if w.get("workoutName") == name:
                        return w.get("workoutId")
        except Exception:
            pass
        return None


# ------------------------------------------------------------------ #
# Watchdog — beobachtet die Eingangs-Inbox                            #
# ------------------------------------------------------------------ #

def start_inbox_watcher(inbox_dir: Path, on_new_file: Callable[[Path], None]) -> object:
    """
    Startet einen Watchdog-Observer für inbox_dir.
    on_new_file(path) wird aufgerufen, sobald eine neue .json-Datei erscheint.
    Gibt den Observer zurück (observer.stop() zum Beenden).
    """
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory and event.src_path.lower().endswith(".json"):
                path = Path(event.src_path)
                log.info("Watchdog: %s erkannt → Upload wird gestartet.", path.name)
                time.sleep(0.5)          # kurz warten bis Datei vollständig geschrieben
                on_new_file(path)

    inbox_dir.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(_Handler(), str(inbox_dir), recursive=False)
    observer.start()
    log.info("Watchdog aktiv: %s", inbox_dir)
    return observer
