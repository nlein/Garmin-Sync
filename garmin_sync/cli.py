import argparse
import sys
from pathlib import Path

from .auth import get_client, interactive_login, is_logged_in
from .config import Config
from .state import SyncState


def run_cli():
    parser = argparse.ArgumentParser(prog="garmin-sync", description="Garmin Connect Sync Tool")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("login", help="Einmalige Anmeldung (speichert Token lokal)")

    p_sync = sub.add_parser("sync", help="Daten synchronisieren (Export + Upload)")
    p_sync.add_argument(
        "--backfill", type=int, metavar="TAGE",
        help="Historie über N Tage laden (z. B. --backfill 365)"
    )

    sub.add_parser("upload", help="Workouts aus Eingangs-Inbox hochladen")
    sub.add_parser("status", help="Token-Status und Sync-Übersicht anzeigen")

    p_cfg = sub.add_parser("config", help="Einstellungen setzen")
    p_cfg.add_argument("--export-dir", metavar="PFAD", help="Export-Verzeichnis setzen")
    p_cfg.add_argument("--upload-dir", metavar="PFAD", help="Upload-Verzeichnis setzen")
    p_cfg.add_argument("--sync-time", metavar="HH:MM", help="Tägliche Sync-Zeit setzen (z. B. 07:00)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    config = Config()

    if args.command == "login":
        _cmd_login(config)
    elif args.command == "sync":
        _cmd_sync(config, getattr(args, "backfill", None))
    elif args.command == "upload":
        _cmd_upload(config)
    elif args.command == "status":
        _cmd_status(config)
    elif args.command == "config":
        _cmd_config(config, args)


def _cmd_login(config: Config):
    print("Garmin Connect Login …")
    if interactive_login():
        print("Login erfolgreich. Token gespeichert.")
    else:
        print("Login fehlgeschlagen.")
        sys.exit(1)


def _cmd_sync(config: Config, backfill: int | None):
    api = get_client()
    if not api:
        print("Nicht angemeldet. Bitte zuerst: garmin-sync login")
        sys.exit(1)

    from .report import ReportWriter
    from .sync import GarminSync
    from .upload import GarminUpload

    state = SyncState(config.export_dir / "sync_state.json")
    syncer = GarminSync(config, state, api)
    success = syncer.run(backfill_days=backfill)

    uploader = GarminUpload(config, api)
    upload_results = uploader.process()

    ReportWriter(config.export_dir).write(success, syncer.new_activities, syncer.errors, upload_results)

    print(f"Sync abgeschlossen — {len(syncer.new_activities)} neue Aktivität(en).")
    if not success:
        print("Achtung: Kern-Sync fehlgeschlagen. Siehe sync.log.")
        sys.exit(1)


def _cmd_upload(config: Config):
    api = get_client()
    if not api:
        print("Nicht angemeldet.")
        sys.exit(1)

    from .upload import GarminUpload

    results = GarminUpload(config, api).process()
    ok = sum(1 for r in results if r["status"] == "ok")
    err = len(results) - ok
    print(f"Upload: {ok} erfolgreich, {err} fehlgeschlagen.")


def _cmd_status(config: Config):
    state = SyncState(config.export_dir / "sync_state.json")
    act_dir = config.export_dir / "aktivitaeten"
    act_count = len(list(act_dir.glob("*"))) if act_dir.exists() else 0

    print(f"Token gültig  : {'Ja' if is_logged_in() else 'Nein — bitte login ausführen'}")
    print(f"Letzter Sync  : {state.last_sync or '—'}")
    print(f"Aktivitäten   : {act_count} lokal gespeichert")
    print(f"Autostart     : {'Aktiviert' if config.autostart else 'Deaktiviert'}")
    print(f"Export-Ordner : {config.export_dir}")
    print(f"Upload-Ordner : {config.upload_dir}")


def _cmd_config(config: Config, args):
    changed = False
    if args.export_dir:
        config.export_dir = Path(args.export_dir)
        print(f"Export-Ordner gesetzt: {args.export_dir}")
        changed = True
    if args.upload_dir:
        config.upload_dir = Path(args.upload_dir)
        print(f"Upload-Ordner gesetzt: {args.upload_dir}")
        changed = True
    if args.sync_time:
        config.set("sync_time", args.sync_time)
        print(f"Sync-Zeit gesetzt: {args.sync_time}")
        changed = True
    if not changed:
        print(f"Export-Ordner : {config.export_dir}")
        print(f"Upload-Ordner : {config.upload_dir}")
        print(f"Sync-Zeit     : {config.sync_time}")
        print(f"Autostart     : {config.autostart}")
