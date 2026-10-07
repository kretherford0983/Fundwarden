"""1.6.6: rename to Fundwarden - the default data folder of a local installation is adopted, an explicitly chosen
data directory is never touched, and install.sh can still install a release from before the rename.
(1.7.0 renamed the application again, to PennyWarden; the folder from before 1.6.6 is still adopted - these tests -
and so is the Fundwarden one: test_v170_rename.py.)"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from fmpoc import config
from tests.test_v150_install_sh import STUB, _tarball, gh, pytestmark, run  # noqa: F401  (gh is a fixture)

OLD_PKG = "FinancialManagementPOC-linux-x64-portable.tar.gz"


def _old_and_new(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("FM_DATA_DIR", raising=False)
    return config.previous_default_data_dirs()[-1], config.default_data_dir()   # the name before 1.6.6


def test_default_data_dir_uses_the_new_name(tmp_path, monkeypatch):
    old, new = _old_and_new(tmp_path, monkeypatch)
    assert new.name.lower() == "pennywarden" and old != new
    assert old.name in ("FinancialManagementPOC", "financial-management-poc")


def test_legacy_default_data_dir_is_renamed_once_and_keeps_every_file(tmp_path, monkeypatch):
    old, new = _old_and_new(tmp_path, monkeypatch)
    (old / "database").mkdir(parents=True)
    (old / "database" / "fmpoc.sqlite3").write_bytes(b"data")
    (old / "secrets").mkdir()
    (old / "secrets" / "key.json").write_text("{}")
    (old / "config.toml").write_text('[server]\nport = 9001\n')
    s = config.load_settings()
    assert s.data_dir == new and not old.exists()
    assert (new / "database" / "fmpoc.sqlite3").read_bytes() == b"data" and (new / "secrets" / "key.json").is_file()
    assert s.port == 9001  # config.toml moved with the folder and is still read
    assert config.load_settings().data_dir == new  # second start: nothing left to adopt


def test_existing_new_data_dir_wins_and_legacy_is_left_alone(tmp_path, monkeypatch):
    old, new = _old_and_new(tmp_path, monkeypatch)
    (old / "database").mkdir(parents=True)
    (new / "database").mkdir(parents=True)
    assert config.load_settings().data_dir == new and (old / "database").is_dir()


def test_explicit_data_dir_never_touches_the_legacy_folder(tmp_path, monkeypatch):
    old, new = _old_and_new(tmp_path, monkeypatch)
    (old / "database").mkdir(parents=True)
    chosen = tmp_path / "elsewhere"
    assert config.load_settings({"data_dir": str(chosen)}).data_dir == chosen
    monkeypatch.setenv("FM_DATA_DIR", str(chosen))
    assert config.load_settings().data_dir == chosen
    assert old.is_dir() and not new.exists()


def test_legacy_folder_is_used_in_place_when_it_cannot_be_renamed(tmp_path, monkeypatch, capsys):
    old, new = _old_and_new(tmp_path, monkeypatch)
    (old / "database").mkdir(parents=True)

    def boom(self, target):
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "rename", boom)
    assert config.load_settings().data_dir == old
    assert "could not be renamed" in capsys.readouterr().err


def test_install_sh_installs_a_release_from_before_the_rename(gh, tmp_path):  # noqa: F811
    """Rollback to (or deliberate install of) e.g. v1.6.5-test.N: that release only has the old package name."""
    tag, tb = "v1.6.5-test.26", _tarball()
    sums = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in ((OLD_PKG, tb), ("install-server.sh", STUB)))
    gh.files.update({f"/dl/{tag}/{OLD_PKG}": tb, f"/dl/{tag}/install-server.sh": STUB,
                     f"/dl/{tag}/SHA256SUMS.txt": sums.encode()})
    code, out, recorded = run(gh, tmp_path, "--version", tag)
    assert code == 0, out
    assert "before the rename" in out
    assert recorded and recorded[0].endswith(OLD_PKG)
