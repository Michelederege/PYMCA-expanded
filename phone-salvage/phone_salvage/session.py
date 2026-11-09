"""Open the catalogue folder and load the sample phones on a first run."""

from __future__ import annotations

import os
from pathlib import Path

from phone_salvage.store import Store


def data_root() -> Path:
    override = os.environ.get("PHONE_SALVAGE_HOME")
    if override:
        return Path(override)
    return Path.home() / "PhoneSalvage"


def open_session(root: Path | None = None, *, seed: bool = True) -> Store:
    folder = Path(root) if root is not None else data_root()
    store = Store(folder)
    store.ensure_catalog()
    if seed and store.get_setting("seeded") != "1" and store.phone_count() == 0:
        from phone_salvage.seed import seed_demo

        seed_demo(store)
        store.set_setting("seeded", "1")
    return store
