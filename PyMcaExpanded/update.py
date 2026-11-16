"""Download a newer packaged build from the GitHub release.

Pushing the main branch publishes ``pymca-expanded-windows.zip`` and
``pymca-expanded-linux.zip`` on the ``latest`` release. A packaged program can
replace its own folder from that release and start again. A copy started
from source does not overwrite the source tree.

The repository has to be visible to GitHub without a login, or a token
with access to releases has to be saved in the home directory. The token
is not written into the updater or the program.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

from PyMcaExpanded import APP_NAME, __version__

GITHUB_REPO = os.environ.get("XRFDESK_GITHUB_REPO", "michele-de-rege/pymca-excelsheet-improvments")


class UpdateError(RuntimeError):
    """The release could not be read or applied."""


@dataclass(frozen=True)
class Release:
    stamp: str
    version: str
    asset_name: str
    asset_url: str
    page_url: str
    notes: str


def installed_stamp() -> str:
    """Git commit baked into a packaged build. Empty when running from source."""
    try:
        from PyMcaExpanded._build_stamp import STAMP
    except ImportError:
        return ""
    return str(STAMP or "").strip()


def install_folder() -> Path | None:
    """Folder that holds the packaged program, or None when this is a source run."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def token_path() -> Path:
    return Path.home() / ".config" / "xrfdesk" / "github_token"


def load_token() -> str:
    env = os.environ.get("XRFDESK_GITHUB_TOKEN", "").strip()
    if env:
        return env
    path = token_path()
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_token(token: str) -> None:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token.strip() + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        return


def clear_token() -> None:
    path = token_path()
    try:
        path.unlink()
    except OSError:
        return


def asset_name(platform: str) -> str:
    if platform == "win32":
        return "pymca-expanded-windows.zip"
    if platform == "darwin":
        return "pymca-expanded-mac.zip"
    return "pymca-expanded-linux.zip"


def parse_release(payload: dict, platform: str) -> Release:
    body = str(payload.get("body") or "")
    stamp = ""
    version = ""
    for line in body.splitlines():
        lowered = line.strip().lower()
        if lowered.startswith("sha:"):
            stamp = line.split(":", 1)[1].strip()
        elif lowered.startswith("version:"):
            version = line.split(":", 1)[1].strip()
    name = asset_name(platform)
    asset = next((item for item in payload.get("assets") or [] if item.get("name") == name), None)
    if asset is None:
        raise UpdateError(f"The latest release has no {name}.")
    url = str(asset.get("browser_download_url") or "")
    if not url:
        raise UpdateError(f"The latest release has no download for {name}.")
    return Release(
        stamp=stamp,
        version=version or str(payload.get("tag_name") or ""),
        asset_name=name,
        asset_url=url,
        page_url=str(payload.get("html_url") or ""),
        notes=body.strip(),
    )


def same_build(release: Release, stamp: str | None = None) -> bool:
    current = installed_stamp() if stamp is None else stamp
    return bool(current) and current == release.stamp


def fetch_latest(repo: str = GITHUB_REPO, token: str | None = None, platform: str | None = None) -> Release:
    """Read the latest GitHub release. ``token`` is sent only as a header."""
    if token is None:
        token = load_token()
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{APP_NAME}/{__version__}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                "No GitHub release is visible. Publish one by pushing main, "
                "or save a token if the repository is private."
            ) from exc
        raise UpdateError(f"GitHub returned {exc.code}.") from exc
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise UpdateError(f"Could not reach GitHub ({reason}).") from exc
    release = parse_release(payload, platform or sys.platform)
    if token:
        release = Release(
            stamp=release.stamp,
            version=release.version,
            asset_name=release.asset_name,
            asset_url=_api_asset_url(payload, release.asset_name) or release.asset_url,
            page_url=release.page_url,
            notes=release.notes,
        )
    return release


def download_release(release: Release, destination: Path, token: str | None = None, progress=None) -> None:
    """Save the release zip. The token is not written to ``destination``."""
    if token is None:
        token = load_token()
    headers = {"User-Agent": f"{APP_NAME}/{__version__}"}
    if token and "api.github.com" in release.asset_url:
        headers["Accept"] = "application/octet-stream"
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(release.asset_url, headers=headers)
    opener = request.build_opener(_DropTokenOnRedirect())
    try:
        with opener.open(req, timeout=120) as response:
            total = int(response.headers.get("Content-Length") or 0)
            destination.parent.mkdir(parents=True, exist_ok=True)
            got = 0
            with destination.open("wb") as handle:
                while True:
                    block = response.read(1024 * 256)
                    if not block:
                        break
                    handle.write(block)
                    got += len(block)
                    if progress is not None:
                        progress(got, total)
    except error.HTTPError as exc:
        raise UpdateError(f"The download failed ({exc.code}).") from exc
    except error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise UpdateError(f"The download failed ({reason}).") from exc
    assert_safe_archive(destination)


def assert_safe_archive(path: Path) -> None:
    """Reject a zip that would write outside the program folder."""
    try:
        handle = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise UpdateError("The download is not a zip file.") from exc
    with handle:
        names = handle.namelist()
        for name in names:
            parts = Path(name.replace("\\", "/")).parts
            if name.startswith(("/", "\\")) or ".." in parts:
                raise UpdateError(f"The update contains an unsafe path ({name}).")
        program = any(
            item.replace("\\", "/").rstrip("/").endswith(f"{APP_NAME}.exe")
            or item.replace("\\", "/").rstrip("/").endswith("/" + APP_NAME)
            or item.replace("\\", "/").rstrip("/") == APP_NAME
            for item in names
        )
        if not program:
            raise UpdateError(f"The update does not contain the {APP_NAME} program.")


def updater_script(pid: int, archive: Path, install: Path) -> str:
    """Shell or PowerShell that waits for this process, then swaps the folder."""
    if sys.platform == "win32":
        return _windows_script(pid, archive, install)
    return _posix_script(pid, archive, install)


def launch_updater(pid: int, archive: Path, install: Path) -> Path:
    """Start the swap after this process exits. Return the script path."""
    script = updater_script(pid, archive, install)
    if sys.platform == "win32":
        path = Path(os.environ.get("TEMP", ".")) / "pymca-expanded-update.ps1"
        path.write_text(script, encoding="utf-8")
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
            creationflags=flags,
            close_fds=True,
        )
        return path
    path = Path(os.environ.get("TMPDIR", "/tmp")) / f"pymca-expanded-update-{pid}.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o700)
    subprocess.Popen(["/bin/sh", str(path)], start_new_session=True, close_fds=True)
    return path


class _DropTokenOnRedirect(request.HTTPRedirectHandler):
    """GitHub redirects asset downloads to storage. The token stays on GitHub."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and "github.com" not in urlparse(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


def _api_asset_url(payload: dict, name: str) -> str:
    for item in payload.get("assets") or []:
        if item.get("name") == name:
            return str(item.get("url") or "")
    return ""


def _posix_script(pid: int, archive: Path, install: Path) -> str:
    log = Path.home() / ".local" / "share" / APP_NAME / "update.log"
    return f"""#!/bin/sh
set -u
LOG={_sh(log)}
PID={int(pid)}
ARCHIVE={_sh(archive)}
INSTALL={_sh(install)}
mkdir -p "$(dirname "$LOG")"
while kill -0 "$PID" 2>/dev/null; do
  sleep 0.2
done
STAGING=$(mktemp -d "${{TMPDIR:-/tmp}}/pymca-expanded-staging.XXXXXX")
if command -v unzip >/dev/null 2>&1; then
  unzip -q -o "$ARCHIVE" -d "$STAGING" || {{
    echo "Could not unpack the update." >> "$LOG"
    exit 1
  }}
elif command -v python3 >/dev/null 2>&1; then
  python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$ARCHIVE" "$STAGING" || {{
    echo "Could not unpack the update." >> "$LOG"
    exit 1
  }}
elif tar -xf "$ARCHIVE" -C "$STAGING"; then
  :
else
  echo "Could not unpack the update. Install unzip and try again." >> "$LOG"
  exit 1
fi
UNPACKED="$STAGING/{APP_NAME}"
if [ ! -e "$UNPACKED/{APP_NAME}" ] && [ ! -e "$UNPACKED/{APP_NAME}.exe" ]; then
  UNPACKED="$STAGING"
fi
rm -rf "$INSTALL.old"
if ! mv "$INSTALL" "$INSTALL.old"; then
  echo "Could not move the current program aside." >> "$LOG"
  exit 1
fi
if ! mv "$UNPACKED" "$INSTALL"; then
  mv "$INSTALL.old" "$INSTALL"
  echo "Could not move the new program into place." >> "$LOG"
  exit 1
fi
if [ -f "$INSTALL/{APP_NAME}" ]; then
  chmod +x "$INSTALL/{APP_NAME}"
  PROGRAM="$INSTALL/{APP_NAME}"
else
  PROGRAM="$INSTALL/{APP_NAME}.exe"
fi
nohup "$PROGRAM" >/dev/null 2>&1 &
sleep 1
rm -rf "$INSTALL.old" "$STAGING" "$ARCHIVE"
echo "Updated $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
"""


def _windows_script(pid: int, archive: Path, install: Path) -> str:
    log = Path.home() / "AppData" / "Local" / APP_NAME / "update.log"
    return f"""$ErrorActionPreference = "Stop"
$Log = {_ps(log)}
$Archive = {_ps(archive)}
$Install = {_ps(install)}
New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null
Wait-Process -Id {int(pid)} -ErrorAction SilentlyContinue
$Staging = Join-Path $env:TEMP ("pymca-expanded-staging-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Staging | Out-Null
try {{
  tar -xf $Archive -C $Staging
}} catch {{
  Add-Content -Path $Log -Value "Could not unpack the update."
  exit 1
}}
$Unpacked = Join-Path $Staging "{APP_NAME}"
if (-not (Test-Path (Join-Path $Unpacked "{APP_NAME}.exe")) -and -not (Test-Path (Join-Path $Unpacked "{APP_NAME}"))) {{
  $Unpacked = $Staging
}}
$Parent = Split-Path $Install -Parent
$Name = Split-Path $Install -Leaf
$Old = Join-Path $Parent ($Name + ".old")
if (Test-Path $Old) {{ Remove-Item -Recurse -Force $Old }}
try {{
  Rename-Item -Path $Install -NewName ($Name + ".old")
}} catch {{
  Add-Content -Path $Log -Value "Could not move the current program aside."
  exit 1
}}
try {{
  Move-Item -Path $Unpacked -Destination $Install
}} catch {{
  Rename-Item -Path $Old -NewName $Name
  Add-Content -Path $Log -Value "Could not move the new program into place."
  exit 1
}}
$Program = Join-Path $Install "{APP_NAME}.exe"
if (-not (Test-Path $Program)) {{ $Program = Join-Path $Install "{APP_NAME}" }}
Start-Process -FilePath $Program
Start-Sleep -Seconds 2
Remove-Item -Recurse -Force $Old -ErrorAction SilentlyContinue
Remove-Item -Force $Archive -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $Staging -ErrorAction SilentlyContinue
Add-Content -Path $Log -Value ("Updated " + (Get-Date).ToUniversalTime().ToString("o"))
"""


def _sh(path: Path) -> str:
    return "'" + str(path).replace("'", "'\"'\"'") + "'"


def _ps(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"
