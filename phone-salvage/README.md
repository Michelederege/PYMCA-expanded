# Phone Salvage

A local desktop catalogue for phones, the boards inside them, and the parts you might reuse. This is stage 1: you mark the map yourself. The window is PySide6. There is no browser, no web server, and no network access.

The Excel workbench in the rest of this repository is a separate project. Phone Salvage lives in this folder.

## What this version does

- Register phones and the boards inside them. Each phone gets a short ID such as `PH-001` to write on a bag.
- Mark parts and named zones on a photo, or on a blank board. Zoom and pan the map.
- Simple view shows the parts that matter for salvage. Detailed view shows every part you marked, including tiny ones.
- Copy a layout onto another phone of the same model. Copied boxes stay dashed until you confirm them.
- A harvest list of what is still worth pulling, modules and plugs before tiny parts.
- One inventory across every phone, with search. A row opens that spot on the map.
- A parts library. Save a marking code once, and the next part with that code can reuse the details.
- Bins for where a removed part is stored.
- Printable labels with a QR code for a phone, a board, or a bin.
- CSV export, and a zip backup of the database plus the images.

## What it does not do yet

Cameras, stitching, detection, damage suggestions, and recording meter readings are later stages. A photo cannot prove a part works. A closed metal shield means the parts under it are unknown.

## Run it

```bash
cd phone-salvage
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m phone_salvage
```

On Windows, activate with `.venv\Scripts\activate`.

The catalogue is created in your home folder as `PhoneSalvage` (`salvage.db`, plus `images` and `datasheets` beside it). The first launch loads two sample phones so you can click through the screens. Set `PHONE_SALVAGE_HOME` to use a different folder.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Backup

File → Back up writes one zip. File → Restore replaces the catalogue on this computer with that zip. Export CSV writes `phones.csv`, `boards.csv`, and `components.csv`.
