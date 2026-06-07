import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog
from typing import Optional

log = logging.getLogger("garmin_sync")

# garth speichert den Token hier — wird an api.login() übergeben
TOKENSTORE = str(Path.home() / ".garminconnect")


def _ask_credentials() -> Optional[tuple[str, str]]:
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    email = simpledialog.askstring("Garmin Login", "E-Mail-Adresse:", parent=root)
    if not email:
        root.destroy()
        return None
    password = simpledialog.askstring("Garmin Login", "Passwort:", show="*", parent=root)
    root.destroy()
    if not password:
        return None
    return email.strip(), password


def _ask_mfa() -> str:
    root = tk.Tk()
    root.withdraw()
    root.lift()
    root.attributes("-topmost", True)
    code = simpledialog.askstring(
        "Garmin MFA",
        "Einmalcode (Authenticator-App oder SMS):",
        parent=root,
    )
    root.destroy()
    return (code or "").strip()


def interactive_login() -> bool:
    """Login-Dialoge anzeigen, bei Garmin authentifizieren, Token unter TOKENSTORE speichern."""
    creds = _ask_credentials()
    if not creds:
        return False
    email, password = creds
    try:
        from garminconnect import Garmin

        # 0.3.x: login(tokenstore) macht Resume UND Erst-Login in einem.
        # Mit Credentials: versucht zuerst Resume, fällt auf Credential-Login zurück
        # und speichert den neuen Token in TOKENSTORE. garth.dump() nicht mehr nötig.
        api = Garmin(email, password, prompt_mfa=_ask_mfa)
        api.login(TOKENSTORE)
        log.info("Login erfolgreich. Token gespeichert.")
        return True
    except Exception as exc:
        log.error("Login fehlgeschlagen: %s", exc)
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Login fehlgeschlagen",
            f"Anmeldung bei Garmin Connect fehlgeschlagen:\n\n{exc}\n\nBitte erneut versuchen.",
            parent=root,
        )
        root.destroy()
        return False


def get_client():
    """Garmin-Client mit gespeichertem Token laden. Gibt None zurück wenn nicht angemeldet."""
    try:
        from garminconnect import Garmin

        api = Garmin()
        api.login(TOKENSTORE)          # liest Token aus ~/.garminconnect/
        return api
    except Exception as exc:
        log.debug("get_client fehlgeschlagen (Token abgelaufen oder fehlt): %s", exc)
        return None


def is_logged_in() -> bool:
    return get_client() is not None
