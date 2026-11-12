"""Resolve caminhos tanto rodando do código-fonte quanto do .exe (PyInstaller)."""

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def content_dir() -> Path:
    return project_root() / "content"


def assets_dir() -> Path:
    return project_root() / "assets"
