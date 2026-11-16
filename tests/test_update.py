import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from xrfdesk.update import (
    UpdateError,
    assert_safe_archive,
    parse_release,
    same_build,
    save_token,
    updater_script,
)


def _payload(platform_asset="xrfdesk-linux.zip"):
    return {
        "tag_name": "latest",
        "html_url": "https://github.com/example/xrfdesk/releases/latest",
        "body": "version: 1.2.0\nsha: abcdef1234567890\n",
        "assets": [
            {
                "name": platform_asset,
                "browser_download_url": "https://example.com/xrfdesk.zip",
                "url": "https://api.github.com/repos/example/xrfdesk/releases/assets/1",
            }
        ],
    }


def test_release_notes_carry_the_commit():
    release = parse_release(_payload(), "linux")
    assert release.version == "1.2.0"
    assert release.stamp == "abcdef1234567890"
    assert release.asset_name == "xrfdesk-linux.zip"
    assert same_build(release, "abcdef1234567890")
    assert not same_build(release, "other")
    assert not same_build(release, "")


def test_windows_release_selects_the_windows_zip():
    release = parse_release(_payload("xrfdesk-windows.zip"), "win32")
    assert release.asset_name == "xrfdesk-windows.zip"


def test_a_release_without_the_program_zip_is_refused():
    payload = _payload()
    payload["assets"] = [{"name": "notes.txt", "browser_download_url": "https://example.com/n"}]
    with pytest.raises(UpdateError):
        parse_release(payload, "linux")


def test_archive_paths_cannot_escape_the_folder(tmp_path):
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(good, "w") as handle:
        handle.writestr("xrfdesk/xrfdesk", "program")
    assert_safe_archive(good)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as handle:
        handle.writestr("../outside", "no")
    with pytest.raises(UpdateError):
        assert_safe_archive(bad)


def test_saved_token_is_not_copied_into_the_updater(tmp_path, monkeypatch):
    monkeypatch.setattr("xrfdesk.update.token_path", lambda: tmp_path / "github_token")
    save_token("secret-token-value")
    script = updater_script(123, tmp_path / "xrfdesk-linux.zip", tmp_path / "app")
    assert "secret-token-value" not in script
    assert "Wait-Process" not in script
    assert "xrfdesk-linux.zip" in script


def test_windows_script_waits_and_swaps(monkeypatch):
    monkeypatch.setattr("xrfdesk.update.sys.platform", "win32")
    script = updater_script(4321, Path(r"C:\Temp\xrfdesk-windows.zip"), Path(r"C:\Apps\xrfdesk"))
    assert "Wait-Process -Id 4321" in script
    assert r"C:\Apps\xrfdesk" in script
    assert "secret" not in script


def test_posix_updater_replaces_the_program_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    install = tmp_path / "xrfdesk"
    install.mkdir()
    (install / "xrfdesk").write_text("old\n", encoding="utf-8")
    archive = tmp_path / "xrfdesk-linux.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("xrfdesk/xrfdesk", "new\n")
    # The grandchild is reparented to init, so the script sees it exit.
    # A child of this test would stay a zombie and the wait would not end.
    grandchild = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import os, time\n"
            "pid = os.fork()\n"
            "if pid > 0:\n"
            "    print(pid, flush=True)\n"
            "    raise SystemExit(0)\n"
            "os.setsid()\n"
            "time.sleep(0.6)\n",
        ],
        text=True,
    )
    script = tmp_path / "update.sh"
    script.write_text(updater_script(int(grandchild.strip()), archive, install), encoding="utf-8")
    subprocess.check_call(["/bin/sh", str(script)], timeout=30)
    assert (install / "xrfdesk").read_text(encoding="utf-8") == "new\n"
    assert not Path(str(install) + ".old").exists()


def test_update_bar_offers_a_check_without_calling_github():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from xrfdesk.gui.update_bar import UpdateBar

    QApplication.instance() or QApplication([])
    bar = UpdateBar()
    assert bar.check_button.text() == "Check for updates"
    assert bar.update_button.isEnabled() is False
