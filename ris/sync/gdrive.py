"""Google Drive remote store (Drive API v3) with OAuth for installed apps (SYN-02).

* Scope: ``drive.file`` only — the app can see and change only files it created.
* OAuth: Google's installed-app flow with a loopback redirect, run in your
  browser. The application never asks for or sees your Google password.
* You provide your own OAuth client (Desktop app) JSON from Google Cloud
  Console; no credentials are bundled. See docs/GOOGLE_DRIVE_SETUP.md.
* The refresh token is stored only in the OS credential store.

Live operation requires network access and your OAuth client; automated tests
exercise this module with a mocked HTTP session.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ris.errors import AuthExpired, NetworkUnavailable, RemoteChanged, SyncError
from ris.sync.remote import RemoteFile, check_name

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
TOKEN_SECRET = "gdrive_token"
FOLDER_MIME = "application/vnd.google-apps.folder"


def google_libraries_available() -> bool:
    try:
        import google.auth  # noqa: F401
        import google_auth_oauthlib  # noqa: F401
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


class GoogleDriveAuth:
    def __init__(self, secrets, client_secrets_path: str | None = None, secret_name: str = TOKEN_SECRET) -> None:
        self.secrets = secrets
        self.client_secrets_path = client_secrets_path
        self.secret_name = secret_name

    def connected(self) -> bool:
        return self.secrets.has(self.secret_name)

    def connect_interactive(self) -> None:
        """Open the browser for Google sign-in and consent; store the refresh token in the keychain."""
        if not google_libraries_available():
            raise SyncError("Google Drive support needs the optional packages: pip install -r requirements-optional.txt")
        if not self.client_secrets_path or not Path(self.client_secrets_path).exists():
            raise SyncError("Choose your Google OAuth client file (Desktop app) first. See the Google Drive setup guide.")
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_path, SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True, prompt="consent", access_type="offline",
                                      authorization_prompt_message="", success_message=(
                                          "Resume Intelligence Studio is connected. You can close this window."))
        self.secrets.set(self.secret_name, creds.to_json())

    def credentials(self):
        raw = self.secrets.get(self.secret_name)
        if not raw:
            raise AuthExpired("Google Drive is not connected.")
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
        if not creds.valid:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                raise AuthExpired("Google Drive authorisation has expired or was revoked. Reconnect your account.") from exc
            except Exception as exc:  # noqa: BLE001 - network errors during refresh
                raise NetworkUnavailable("Could not reach Google to renew authorisation.") from exc
            self.secrets.set(self.secret_name, creds.to_json())
        return creds

    def session(self):
        from google.auth.transport.requests import AuthorizedSession

        return AuthorizedSession(self.credentials())

    def disconnect(self, revoke: bool = True) -> None:
        raw = self.secrets.get(self.secret_name)
        if raw and revoke:
            try:
                import requests

                token = json.loads(raw).get("refresh_token") or json.loads(raw).get("token")
                if token:
                    requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=10)
            except Exception:  # noqa: BLE001 - revocation is best effort; local token is removed regardless
                log.info("Token revocation could not be confirmed")
        self.secrets.delete(self.secret_name)


class GoogleDriveRemote:
    name = "gdrive"

    def __init__(self, session, folder_name: str = "Resume Intelligence Studio", folder_id: str = "") -> None:
        self.session = session
        self.folder_name = folder_name
        self.folder_id = folder_id
        self._ids: dict[str, str] = {}

    def describe(self) -> str:
        return f"Google Drive folder '{self.folder_name}' (app-created files only)"

    # ------------------------------------------------------------------ HTTP
    def _call(self, method: str, url: str, **kw) -> Any:
        try:
            resp = self.session.request(method, url, timeout=60, **kw)
        except Exception as exc:  # noqa: BLE001 - requests/socket errors → offline
            name = type(exc).__name__
            if "Refresh" in name or "Auth" in name:
                raise AuthExpired("Google Drive authorisation needs renewing.") from exc
            raise NetworkUnavailable("Could not reach Google Drive. Check your connection and try again.") from exc
        code = resp.status_code
        if code == 401:
            raise AuthExpired("Google Drive authorisation has expired. Reconnect your account.")
        if code in (429, 500, 502, 503, 504) or (code == 403 and "rateLimit" in (resp.text or "")):
            raise NetworkUnavailable("Google Drive is busy; it will be retried.")
        if code == 404:
            raise SyncError("The file was not found on Google Drive.")
        if code >= 400:
            raise SyncError(f"Google Drive returned an error ({code}).")
        return resp

    # ------------------------------------------------------------------ folder and lookup
    def ensure_folder(self) -> str:
        if self.folder_id:
            return self.folder_id
        q = f"mimeType='{FOLDER_MIME}' and name='{self.folder_name.replace(chr(39), '')}' and trashed=false"
        resp = self._call("GET", f"{API}/files", params={"q": q, "fields": "files(id,name)", "spaces": "drive"})
        files = resp.json().get("files", [])
        if files:
            self.folder_id = files[0]["id"]
        else:
            resp = self._call("POST", f"{API}/files", params={"fields": "id"},
                              json={"name": self.folder_name, "mimeType": FOLDER_MIME})
            self.folder_id = resp.json()["id"]
        return self.folder_id

    def _flat(self, name: str) -> str:
        # Drive folders are flat here: "ris-sync/state.json" → "ris-sync__state.json".
        return check_name(name).replace("/", "__")

    def _meta(self, f: dict) -> RemoteFile:
        return RemoteFile(f["name"].replace("__", "/"), int(f.get("size", 0) or 0), f.get("modifiedTime", ""),
                          str(f.get("version", "")), f["id"])

    def list_files(self, prefix: str = "") -> list[RemoteFile]:
        folder = self.ensure_folder()
        out: list[RemoteFile] = []
        page = None
        while True:
            params = {"q": f"'{folder}' in parents and trashed=false",
                      "fields": "nextPageToken,files(id,name,size,modifiedTime,version,md5Checksum)", "pageSize": 200}
            if page:
                params["pageToken"] = page
            data = self._call("GET", f"{API}/files", params=params).json()
            for f in data.get("files", []):
                rf = self._meta(f)
                self._ids[rf.name] = rf.remote_id
                if rf.name.startswith(prefix):
                    out.append(rf)
            page = data.get("nextPageToken")
            if not page:
                break
        return sorted(out, key=lambda r: r.name)

    def stat(self, name: str) -> RemoteFile | None:
        folder = self.ensure_folder()
        flat = self._flat(name)
        q = f"'{folder}' in parents and name='{flat}' and trashed=false"
        files = self._call("GET", f"{API}/files", params={"q": q, "fields": "files(id,name,size,modifiedTime,version)"}
                           ).json().get("files", [])
        if not files:
            return None
        rf = self._meta(files[0])
        self._ids[name] = rf.remote_id
        return rf

    def read(self, name: str) -> tuple[bytes, RemoteFile]:
        info = self.stat(name)
        if info is None:
            raise SyncError(f"Remote file not found: {name}")
        resp = self._call("GET", f"{API}/files/{info.remote_id}", params={"alt": "media"})
        return resp.content, info

    def write(self, name: str, data: bytes, expected_version: str | None = None) -> RemoteFile:
        folder = self.ensure_folder()
        current = self.stat(name)
        if expected_version is not None and (current.version if current else "") != expected_version:
            raise RemoteChanged("The Google Drive copy changed during synchronisation.")
        fields = "id,name,size,modifiedTime,version"
        if current is None:
            boundary = "risboundary7c1f"
            meta = json.dumps({"name": self._flat(name), "parents": [folder]}).encode()
            body = (b"--" + boundary.encode() + b"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + meta
                    + b"\r\n--" + boundary.encode() + b"\r\nContent-Type: application/octet-stream\r\n\r\n" + data
                    + b"\r\n--" + boundary.encode() + b"--")
            resp = self._call("POST", f"{UPLOAD}/files", params={"uploadType": "multipart", "fields": fields},
                              data=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"})
        else:
            resp = self._call("PATCH", f"{UPLOAD}/files/{current.remote_id}", params={"uploadType": "media",
                                                                                      "fields": fields},
                              data=data, headers={"Content-Type": "application/octet-stream"})
        rf = self._meta(resp.json())
        self._ids[name] = rf.remote_id
        return rf

    def delete(self, name: str) -> None:
        """Move the cloud copy to the Drive trash (recoverable there for about 30 days)."""
        info = self.stat(name)
        if info is None:
            return
        self._call("PATCH", f"{API}/files/{info.remote_id}", params={"fields": "id"}, json={"trashed": True})


def drive_remote_from_settings(workspace, secrets) -> GoogleDriveRemote:
    if not google_libraries_available():
        raise SyncError("Google Drive support needs the optional packages: pip install -r requirements-optional.txt")
    auth = GoogleDriveAuth(secrets, workspace.settings.get("sync.drive_client_file") or None,
                           secret_name=f"{TOKEN_SECRET}:{workspace.id or workspace.name}")
    remote = GoogleDriveRemote(auth.session(), workspace.settings.get("sync.drive_folder_name") or
                               "Resume Intelligence Studio", workspace.settings.get("sync.drive_folder_id") or "")
    fid = remote.ensure_folder()
    if fid != workspace.settings.get("sync.drive_folder_id"):
        workspace.settings.set("sync.drive_folder_id", fid)
    return remote
