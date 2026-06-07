import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("garmin_sync")


class ReportWriter:
    def __init__(self, export_dir: Path):
        self.export_dir = export_dir
        self.report_path = export_dir / "LETZTER_SYNC.md"

    def write(
        self,
        success: bool,
        new_activities: list,
        errors: list,
        upload_results: Optional[list] = None,
        upload_only: bool = False,
    ):
        """
        Schreibt LETZTER_SYNC.md.
        Bei upload_only=True wird nur der Upload-Abschnitt aktualisiert;
        der Aktivitäten-Abschnitt des letzten vollständigen Syncs bleibt erhalten.
        """
        if upload_only and self.report_path.exists():
            self._update_upload_section(upload_results or [])
            return

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "✅ Erfolgreich" if success else "❌ Mit Fehlern"
        lines = [
            "# Letzter Garmin-Sync",
            "",
            f"**Zeitstempel:** {ts}  ",
            f"**Status:** {status}",
            "",
        ]

        # ---- Neue Aktivitäten ----
        if new_activities:
            lines += [
                "## Neue Aktivitäten",
                "",
                "| Datum | Name | Distanz | Zeit | Ø Pace | Ø HF | Max HF | Zeit in Zonen | Ø Kadenz | Training Effect |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
            for act in new_activities:
                date_str = act.get("startTimeLocal", "")[:10]
                name = act.get("activityName", "–")
                dist_m = act.get("distance", 0) or 0
                dist = f"{dist_m / 1000:.2f} km" if dist_m else "–"
                dur_s = act.get("duration", 0) or 0
                dur = (
                    f"{int(dur_s // 3600)}:{int((dur_s % 3600) // 60):02d}:{int(dur_s % 60):02d}"
                    if dur_s else "–"
                )
                speed = act.get("averageSpeed", 0) or 0
                pace = self._pace(speed) if speed else "–"
                avg_hr = act.get("averageHR", "–")
                max_hr = act.get("maxHR", "–")
                zones = self._hr_zones_from_activity(act)
                kad = act.get("averageRunningCadenceInStepsPerMinute", "–")
                te = act.get("aerobicTrainingEffect") or act.get("trainingEffect") or "–"
                lines.append(
                    f"| {date_str} | {name} | {dist} | {dur} | {pace} | {avg_hr} | {max_hr} | {zones} | {kad} | {te} |"
                )
            lines.append("")
        else:
            lines += ["## Neue Aktivitäten", "", "_Keine neuen Aktivitäten._", ""]

        # ---- Trainings-Status ----
        lines += ["## Trainings-Status", ""]
        vo2 = self._read_vo2max()
        if vo2:
            lines.append(f"- **VO₂max:** {vo2}")
        ts_status = self._read_training_status()
        if ts_status:
            lines.append(f"- **Trainingszustand:** {ts_status}")
        shoe_km = self._read_shoe_km()
        if shoe_km:
            lines.append(f"- **Schuh km-Stand:** {shoe_km}")
        lines.append("")

        # ---- Upload-Ergebnisse ----
        lines += self._upload_section(upload_results or [])

        # ---- Fehler ----
        if errors:
            lines += ["## Aufgetretene Fehler", ""]
            for e in errors:
                lines.append(f"- {e}")
            lines.append("")

        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text("\n".join(lines), encoding="utf-8")
        log.info("LETZTER_SYNC.md geschrieben.")

    def _update_upload_section(self, upload_results: list):
        """Ersetzt nur den Upload-Abschnitt im bestehenden Report."""
        content = self.report_path.read_text(encoding="utf-8")
        marker_start = "## Workout-Uploads"
        marker_end = "\n## "

        new_section = "\n".join(self._upload_section(upload_results))
        idx = content.find(marker_start)
        if idx == -1:
            content += "\n" + new_section
        else:
            end = content.find(marker_end, idx + len(marker_start))
            if end == -1:
                content = content[:idx] + new_section
            else:
                content = content[:idx] + new_section + "\n" + content[end + 1:]

        self.report_path.write_text(content, encoding="utf-8")
        log.info("LETZTER_SYNC.md — Upload-Abschnitt aktualisiert.")

    def _upload_section(self, upload_results: list) -> list[str]:
        if not upload_results:
            return []
        lines = ["## Workout-Uploads", ""]
        for r in upload_results:
            icon = "✅" if r["status"] == "ok" else "❌"
            detail = str(r.get("workout_id") or r.get("error") or "")
            lines.append(f"- {icon} `{r['file']}` — {detail}")
        lines.append("")
        return lines

    # ---- Hilfsmethoden ----

    def _pace(self, speed_ms: float) -> str:
        if speed_ms <= 0:
            return "–"
        spk = 1000 / speed_ms
        return f"{int(spk // 60)}:{int(spk % 60):02d} min/km"

    def _hr_zones_from_activity(self, act: dict) -> str:
        """Liest Zeit in HF-Zonen aus summary.json (falls vorhanden)."""
        # Werte kommen aus hf_zonen.json, nicht direkt aus act — hier nur Platzhalter
        # aus dem summary-Objekt, falls die API Zonen direkt liefert
        zones = act.get("hrTimeInZones") or act.get("heartRateZones")
        if zones and isinstance(zones, list):
            parts = [f"Z{i+1}:{self._fmt_time(z.get('secsInZone', 0))}" for i, z in enumerate(zones[:5])]
            return " ".join(parts)
        return "–"

    def _fmt_time(self, seconds: int) -> str:
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"

    def _read_vo2max(self) -> Optional[str]:
        path = self.export_dir / "status" / "vo2max_verlauf.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                entry = data[-1] if isinstance(data, list) and data else data
                val = (
                    entry.get("generic", {}).get("vo2MaxPreciseValue")
                    or entry.get("vo2MaxPreciseValue")
                    or entry.get("vo2Max")
                )
                return str(round(float(val), 1)) if val else None
        except Exception:
            pass
        return None

    def _read_training_status(self) -> Optional[str]:
        path = self.export_dir / "status" / "training_status.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return (
                    data.get("trainingStatusDTO", {}).get("trainingStatusFeedback")
                    or data.get("trainingStatus")
                    or data.get("latestTrainingStatusData", {})
                       .get("trainingStatusDTO", {})
                       .get("trainingStatusFeedback")
                )
        except Exception:
            pass
        return None

    def _read_shoe_km(self) -> Optional[str]:
        """Liest km-Stände der Schuhe aus ausruestung.json."""
        path = self.export_dir / "profil" / "ausruestung.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else data.get("gearList", [])
                parts = []
                for item in items:
                    name = item.get("customMakeModel") or item.get("displayName", "Schuh")
                    km = item.get("totalDistance", 0)
                    if km:
                        parts.append(f"{name}: {km / 1000:.0f} km")
                return ", ".join(parts) if parts else None
        except Exception:
            pass
        return None
