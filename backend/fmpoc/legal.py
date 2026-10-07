"""v1.5.0: license information (AGPL-3.0) and the link to the source code.

AGPL-3.0 section 13: users interacting with the program over a network must be offered its source code. The app
shows a "Source code" link (sign-in page, My Account, System/About) to the repository at the exact commit of the
build. If you run a MODIFIED version for others, point SOURCE_URL at your own published source.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from .config import build_info

LICENSE_ID = "AGPL-3.0-only"
LICENSE_NAME = "GNU Affero General Public License v3.0"
SOURCE_URL = "https://github.com/kretherford0983/PennyWarden"
DOCS = {"license": "LICENSE", "notices": "THIRD-PARTY-NOTICES.txt"}

_PKG = Path(__file__).resolve().parent


def legal_file(doc: str) -> Path | None:
    """The bundled LICENSE / THIRD-PARTY-NOTICES.txt: inside the one-file .exe (legal/), next to app/ in the
    portable packages, at the repository root in development, next to fmpoc/ in the Docker image."""
    name = DOCS.get(doc)
    if not name:
        return None
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "legal")
        dirs.append(Path(sys.executable).parent)
    dirs += [_PKG.parent.parent, _PKG.parent]
    for d in dirs:
        p = d / name
        if p.is_file():
            return p
    return None


def source_url() -> str:
    commit = (build_info() or {}).get("commit", "")
    return f"{SOURCE_URL}/tree/{commit}" if re.fullmatch(r"[0-9a-f]{7,40}", commit) else SOURCE_URL


def legal_payload() -> dict:
    return {"license": LICENSE_ID, "license_name": LICENSE_NAME, "source_url": source_url()}
