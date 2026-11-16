import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np
import pytest

from xrfdesk.cli import main
from xrfdesk.mapbatch import (
    NOT_STARTED,
    NO_CONFIG,
    OK,
    PROBLEM,
    SKIPPED,
    batch_slices,
    discover_configs,
    discover_samples,
    mca_files,
    output_root,
    run_maps,
    samples_from_location,
)


def test_ten_processes_cover_each_file_once():
    jobs = batch_slices(14000, 10)
    assert len(jobs) == 10
    covered = []
    for begin, end_offset, step, mca_offset, mca_step, chunk in jobs:
        assert (mca_offset, mca_step, step) == (0, 1, 1)
        assert chunk is not None
        covered.extend(range(begin, 14000 - end_offset, step))
    assert covered == list(range(14000))


@pytest.mark.parametrize("n_files,workers", [(12000, 1), (12000, 2), (12000, 3), (15000, 1), (15000, 2), (15000, 3)])
def test_large_batch_covers_every_file_once(n_files, workers):
    jobs = batch_slices(n_files, workers)
    assert 1 <= len(jobs) <= workers
    covered = []
    for begin, end_offset, step, mca_offset, mca_step, chunk in jobs:
        assert (mca_offset, mca_step, step) == (0, 1, 1)
        assert (chunk is None) == (workers == 1)
        covered.extend(range(begin, n_files - end_offset, step))
    assert len(covered) == n_files
    assert sorted(covered) == list(range(n_files))


def test_output_checks_reject_a_short_table_and_a_short_image(tmp_path):
    from xrfdesk.mapbatch import _edf_problem, _table_problem

    short = tmp_path / "00001_to_00002.csv"
    short.write_text('"row";"column";"Fe_K"\n0;0;1.0\n', encoding="utf-8")
    assert "missing" in (_table_problem(short, 2) or "")
    complete = tmp_path / "complete.dat"
    complete.write_text("row column Fe_K\n0 0 1.0\n1 0 2.0\n", encoding="utf-8")
    assert _table_problem(complete, 2) is None
    image = tmp_path / "00001_to_00002_Fe_K.edf"
    image.write_bytes(b"{\nDim_1 = 1 ;\nDim_2 = 1 ;\n}\n")
    assert "for 2 MCA files" in (_edf_problem(image, 2) or "")
    image.write_bytes(b"{\nDim_1 = 1 ;\nDim_2 = 2 ;\n}\n")
    assert _edf_problem(image, 2) is None


def test_discovery_and_file_order(tmp_path):
    cfg = _write_config(tmp_path / "Configuration Files for PyMCA" / "M Series 11112026.cfg")
    (tmp_path / "Configuration Files for PyMCA" / "ITO slides.cfg").write_text("ito\n", encoding="utf-8")
    (tmp_path / "Older cfg used").mkdir()
    (tmp_path / "Older cfg used" / "old.cfg").write_text("keep\n", encoding="utf-8")
    pending = tmp_path / "2026-10-06 - 260401-FC - Nd-Lu 10ppm - pH 6"
    _write_map(pending / "MCA", [1, 2, 10], good=True)
    finished = tmp_path / "2026-10-07 - 260401-FD - done"
    _write_map(finished / "MCA", [1], good=True)
    (finished / "IMAGES").mkdir()
    (finished / "IMAGES" / "marker.txt").write_text("keep-me\n", encoding="utf-8")
    (finished / "00001.h5").write_bytes(b"original-h5")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "readme.txt").write_text("not a sample\n", encoding="utf-8")

    found = discover_samples(tmp_path)
    assert [Path(sample.path).name for sample in found] == [pending.name, finished.name]
    assert [sample.has_results for sample in found] == [False, True]
    assert [path.name for path in mca_files(pending)] == ["00001.mca", "00002.mca", "00010.mca"]
    assert output_root(mca_files(pending)) == "00001_to_00010"
    assert discover_samples(pending)[0].path == str(pending)
    assert [path.name for path in discover_configs(tmp_path)] == ["ITO slides.cfg", "M Series 11112026.cfg"]
    assert cfg.is_file()


def test_run_skips_finished_folders_and_stops_after_a_bad_one(tmp_path):
    cfg = _write_config(tmp_path / "Configuration Files for PyMCA" / "M Series 11112026.cfg")
    cfg_bytes = cfg.read_bytes()
    (tmp_path / "Older cfg used").mkdir()
    (tmp_path / "Older cfg used" / "old.cfg").write_bytes(b"keep-root")
    good = tmp_path / "2026-10-06 - 260401-FC - Nd-Lu 10ppm - pH 6"
    _write_map(good / "MCA", [1, 2, 3, 4], good=True)
    (good / "Older cfg used").mkdir()
    (good / "Older cfg used" / "note.txt").write_text("do not touch\n", encoding="utf-8")
    done = tmp_path / "2026-10-07 - 260401-FD - done"
    _write_map(done / "MCA", [1], good=True)
    (done / "IMAGES").mkdir()
    (done / "IMAGES" / "marker.txt").write_text("keep-me\n", encoding="utf-8")
    (done / "00001.h5").write_bytes(b"original-h5")
    bad = tmp_path / "2026-10-08 - 260401-FE - bad"
    _write_map(bad / "MCA", [1, 2], good=False)
    later = tmp_path / "2026-10-09 - 260401-FF - later"
    _write_map(later / "MCA", [1], good=True)
    before = _bytes(good)

    results = run_maps(str(cfg), root=tmp_path, workers=2, process_limit=2)
    by_name = {result.folder: result for result in results}
    assert [result.folder for result in results] == [good.name, done.name, bad.name, later.name]
    assert by_name[good.name].status == OK
    assert by_name[good.name].mca_count == 4
    assert by_name[good.name].h5_name == "00001_to_00004.h5"
    assert by_name[done.name].status == SKIPPED
    assert by_name[bad.name].status == PROBLEM
    assert "Could not fit" in by_name[bad.name].detail
    assert ".mca" in by_name[bad.name].detail
    assert by_name[later.name].status == NOT_STARTED

    h5 = good / "00001_to_00004.h5"
    images = good / "IMAGES"
    assert h5.is_file()
    assert (images / "00001_to_00004.cfg").is_file()
    assert (images / "00001_to_00004.csv").is_file()
    assert (images / "00001_to_00004.dat").is_file()
    assert list(images.glob("00001_to_00004*.edf"))
    assert not list(images.glob("*.tif"))
    assert not (good / "FIT").exists()
    assert not (good / "HTML").exists()
    assert not list(good.glob("*partial*"))
    assert not list(images.glob("*partial*"))
    dat_lines = [line for line in (images / "00001_to_00004.dat").read_text(encoding="utf-8").splitlines() if line.strip()]
    csv_lines = [line for line in (images / "00001_to_00004.csv").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(dat_lines) == 5
    assert len(csv_lines) == 5
    assert [line.split(";")[0] for line in csv_lines[1:]] == ["0", "1", "2", "3"]
    edf = next(images.glob("00001_to_00004_Fe_K.edf"))
    header = edf.read_bytes().split(b"}", 1)[0].decode("ascii", "replace")
    assert "Dim_2 = 4" in header
    assert _fe_area(h5).shape == (4, 1)
    assert _bytes(good) == before
    assert (done / "IMAGES" / "marker.txt").read_text(encoding="utf-8") == "keep-me\n"
    assert (done / "00001.h5").read_bytes() == b"original-h5"
    assert not (bad / "IMAGES").exists()
    assert not list(bad.glob("*.h5"))
    assert not (later / "IMAGES").exists()
    assert not list(later.glob("*.h5"))
    assert cfg.read_bytes() == cfg_bytes
    assert (tmp_path / "Older cfg used" / "old.cfg").read_bytes() == b"keep-root"
    assert not list((good / "MCA").rglob("*.h5"))
    assert not list((good / "Older cfg used").rglob("*.h5"))


def test_one_folder_uses_the_whole_process_count(tmp_path, monkeypatch):
    from xrfdesk import mapbatch
    from xrfdesk.schedule import processes_in_use

    cfg = _write_config(tmp_path / "fit.cfg")
    sample = tmp_path / "only"
    _write_map(sample / "MCA", [1], good=True)
    seen = []

    def fake(cfg, sample, workers, progress, cancel, together=False):
        seen.append((workers, together))
        return "stopped for the test"

    monkeypatch.setattr(mapbatch, "_fit_folder", fake)
    results = run_maps(str(cfg), folders=[str(sample)], workers=4, process_limit=4)
    assert seen == [(4, False)]
    assert results[0].status == PROBLEM
    assert results[0].detail == "stopped for the test"
    assert processes_in_use() == 0


def test_three_batches_run_together_and_match_one_process(tmp_path, monkeypatch):
    import threading

    from xrfdesk import mapbatch
    from xrfdesk.schedule import processes_in_use

    cfg = _write_config(tmp_path / "fit.cfg")
    serial = []
    for index in range(3):
        folder = tmp_path / f"serial-{index}"
        _write_map(folder / "MCA", [1, 2], good=True)
        assert run_maps(str(cfg), folders=[str(folder)], workers=1)[0].status == OK
        serial.append(_fe_area(folder / "00001_to_00002.h5"))

    folders = []
    for index in range(3):
        folder = tmp_path / f"2026-11-1{index} - together-{index}"
        _write_map(folder / "MCA", [1, 2], good=True)
        folders.append(str(folder))

    barrier = threading.Barrier(3)
    seen = []
    lock = threading.Lock()
    real = mapbatch._fit_folder

    def wrapped(cfg, sample, workers, progress, cancel, together=False):
        with lock:
            seen.append((workers, together))
        barrier.wait(timeout=60)
        return real(cfg, sample, workers, progress, cancel, together=together)

    monkeypatch.setattr(mapbatch, "_fit_folder", wrapped)
    results = run_maps(str(cfg), folders=folders, workers=3, process_limit=3)
    assert [result.status for result in results] == [OK, OK, OK]
    assert sorted(seen) == [(1, True), (1, True), (1, True)]
    for result, expected in zip(results, serial):
        assert _fe_area(Path(result.path) / result.h5_name) == pytest.approx(expected)
    assert processes_in_use() == 0


def test_parallel_map_matches_one_process(tmp_path):
    cfg = _write_config(tmp_path / "fit.cfg")
    serial = tmp_path / "serial"
    parallel = tmp_path / "parallel"
    _write_map(serial / "MCA", [1, 2, 3, 4], good=True)
    _write_map(parallel / "MCA", [1, 2, 3, 4], good=True)
    assert run_maps(str(cfg), folders=[str(serial)], workers=1)[0].status == OK
    assert run_maps(str(cfg), folders=[str(parallel)], workers=2)[0].status == OK
    assert _fe_area(parallel / "00001_to_00004.h5") == pytest.approx(_fe_area(serial / "00001_to_00004.h5"))


def test_more_processes_than_files_still_fits_every_row(tmp_path):
    cfg = _write_config(tmp_path / "fit.cfg")
    sample = tmp_path / "2026-11-01 - 260401-AA - two"
    _write_map(sample / "MCA", [1, 2], good=True)
    result = run_maps(str(cfg), folders=[str(sample)], workers=4)[0]
    assert result.status == OK
    assert result.h5_name == "00001_to_00002.h5"
    assert _fe_area(sample / result.h5_name).shape == (2, 1)


def test_cli_prints_the_result_table(tmp_path, capsys):
    cfg = _write_config(tmp_path / "Configuration Files for PyMCA" / "fit.cfg")
    sample = tmp_path / "2026-11-02 - 260401-AB - cli"
    _write_map(sample / "MCA", [1, 2], good=True)
    code = main(["--map-root", str(tmp_path), "--cfg", str(cfg), "--workers", "2"])
    captured = capsys.readouterr()
    assert code == 0
    assert "00001_to_00002.h5" in captured.out
    assert "OK" in captured.out
    assert sample.name in captured.out


def test_cli_reports_a_root_with_no_samples(tmp_path, capsys):
    cfg = _write_config(tmp_path / "fit.cfg")
    code = main(["--map-root", str(tmp_path), "--cfg", str(cfg)])
    assert code == 2
    assert "No sample folders" in capsys.readouterr().err


def test_map_window_fits_a_sample_root(tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from xrfdesk.gui.fit_window import FitWindow
    from xrfdesk.gui.map_window import MapWindow

    cfg = _write_config(tmp_path / "fit.cfg")
    sample = tmp_path / "2026-11-03 - 260401-AC - window"
    _write_map(sample / "MCA", [1, 2], good=True)
    app = QApplication.instance() or QApplication([])

    def explode(*_args, **_kwargs):
        raise AssertionError("The map window asked a question on a folder with no results.")

    monkeypatch.setattr(QMessageBox, "warning", explode)
    monkeypatch.setattr(QMessageBox, "question", explode)
    fit = FitWindow()
    fit.open_map()
    window = fit._map_window
    assert isinstance(window, MapWindow)
    assert window.cfg == ""
    window.set_root(str(tmp_path))
    window.set_configuration(str(cfg))
    assert window.cfg == str(cfg)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text() == "fit.cfg"
    assert window.table.item(0, 3).text() == "00001_to_00002.h5"
    window.workers.setValue(2)
    window.start(overwrite=False)
    deadline = time.time() + 120
    while window._thread is not None and window._thread.isRunning():
        app.processEvents()
        time.sleep(0.05)
        if time.time() > deadline:
            window.cancel()
            raise AssertionError("Map window did not finish.")
    app.processEvents()
    assert window.results[0].status == OK
    assert window.table.item(0, 4).text() == "OK · in this folder"
    assert str(sample / "00001_to_00002.h5") in window.table.item(0, 3).toolTip()
    assert "IMAGES" in window.status_label.text()
    assert (sample / "IMAGES" / "00001_to_00002.dat").is_file()


def test_open_folder_opens_the_sample_directory(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from xrfdesk.gui.map_window import MapWindow
    from xrfdesk.mapbatch import Sample

    QApplication.instance() or QApplication([])
    sample = tmp_path / "2026-11-04 - saved"
    (sample / "MCA").mkdir(parents=True)
    (sample / "00001_to_00002.h5").write_bytes(b"h5")
    window = MapWindow()
    window.samples = [Sample(str(sample), True, 2, "00001_to_00002.h5", "00001_to_00002.h5")]
    window._fill()
    opened: list[str] = []

    def record(url):
        opened.append(url.toLocalFile())
        return True

    monkeypatch.setattr("xrfdesk.gui.map_window.QDesktopServices.openUrl", record)
    window.table.selectRow(0)
    window.open_selected_folder()
    assert opened == [str(sample)]
    assert "already has results · in this folder" in window.table.item(0, 4).text()
    assert str(sample / "00001_to_00002.h5") in window.table.item(0, 4).toolTip()
    assert str(sample) in window.status_label.text()


def test_map_window_requires_a_selected_configuration(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from xrfdesk.gui.map_window import MapWindow

    library = tmp_path / "Configuration Files for PyMCA"
    library.mkdir()
    (library / "ITO slides.cfg").write_text("ito\n", encoding="utf-8")
    (library / "M Series 11112026.cfg").write_text("series\n", encoding="utf-8")
    (tmp_path / "Older cfg used").mkdir()
    (tmp_path / "Older cfg used" / "retired.cfg").write_text("old\n", encoding="utf-8")
    sample = tmp_path / "2026-11-04 - 260401-AD - configs"
    (sample / "MCA").mkdir(parents=True)
    (sample / "MCA" / "00001.mca").write_text("not fitted\n", encoding="utf-8")
    QApplication.instance() or QApplication([])
    window = MapWindow()
    window.set_configuration(str(library / "ITO slides.cfg"))
    window.set_root(str(tmp_path))
    assert window.cfg == str(library / "ITO slides.cfg")
    assert window.table.item(0, 1).text() == "—"
    assert [window.config_combo.itemText(row) for row in range(window.config_combo.count())] == [
        "ITO slides.cfg",
        "M Series 11112026.cfg",
    ]
    warnings: list[str] = []

    def record(*args, **_kwargs):
        warnings.append(str(args[2] if len(args) > 2 else args))

    monkeypatch.setattr(QMessageBox, "warning", record)
    window.start(overwrite=False)
    assert window._thread is None
    assert warnings
    assert "Select a configuration file" in warnings[0]
    window.table.selectRow(0)
    window.config_combo.setCurrentIndex(1)
    window.apply_selected()
    assert window.table.item(0, 1).text() == "M Series 11112026.cfg"
    assert window.table.item(0, 1).toolTip() == str(library / "M Series 11112026.cfg")
    assert "M Series 11112026.cfg" in window.status_label.text()


def test_each_batch_keeps_its_own_percent_and_time(tmp_path):
    from PySide6.QtWidgets import QApplication

    from xrfdesk.gui.map_window import MapWindow, _RowStatus
    from xrfdesk.mapbatch import MapProgress, Sample

    QApplication.instance() or QApplication([])
    window = MapWindow()
    alpha = tmp_path / "batch-alpha"
    beta = tmp_path / "batch-beta"
    window.samples = [
        Sample(str(alpha), False, 14000, "", "00001_to_14000.h5"),
        Sample(str(beta), False, 14000, "", "00001_to_14000.h5"),
    ]
    window.assigned = {str(alpha): "fit.cfg", str(beta): "fit.cfg"}
    window._fill()
    window._prepare_run(False)
    window._on_progress(MapProgress(0, 2, alpha.name, 7000, 14000, "fitting", 2, 120))
    window._on_progress(MapProgress(1, 2, beta.name, 1400, 14000, "fitting", 2, 800))

    assert window.table.item(0, 4).text() == "50% · 2 min left"
    assert window.table.item(1, 4).text() == "10% · 13 min left"
    assert isinstance(window.table.cellWidget(0, 4), _RowStatus)
    assert isinstance(window.table.cellWidget(1, 4), _RowStatus)
    assert window.table.cellWidget(0, 4).label.text() == "50% · 2 min left"
    assert window.table.cellWidget(0, 4).bar.value() == 50
    assert window.table.cellWidget(1, 4).bar.value() == 10
    assert "batch-alpha" not in window.status_label.text()
    assert "batch-beta" not in window.status_label.text()
    assert "8400 of 28000" in window.status_label.text()
    assert window.progress.value() == 8400
    assert window.progress.maximum() == 28000
    assert "fitting" not in window.table.item(0, 4).text()


def test_a_folder_path_can_come_from_anywhere(tmp_path):
    left = _empty_sample(tmp_path / "drive-a" / "2026-11-04 - left")
    right = _empty_sample(tmp_path / "drive-b" / "2026-11-07 - right")
    found = samples_from_location(left / "MCA")
    assert [Path(sample.path) for sample in found] == [left.resolve()]
    parent = samples_from_location(tmp_path / "drive-b")
    assert [Path(sample.path).name for sample in parent] == ["2026-11-07 - right"]
    with pytest.raises(FileNotFoundError):
        samples_from_location(tmp_path / "missing")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        samples_from_location(tmp_path / "notes.txt")


def test_selected_folders_share_one_configuration_and_can_differ(tmp_path, monkeypatch):
    from PySide6.QtCore import QItemSelectionModel
    from PySide6.QtWidgets import QApplication, QMessageBox

    from xrfdesk.gui.map_window import MapWindow

    QApplication.instance() or QApplication([])
    left = _empty_sample(tmp_path / "lab-a" / "sample-left")
    right = _empty_sample(tmp_path / "lab-b" / "sample-right")
    shared = tmp_path / "shared.cfg"
    other = tmp_path / "other.cfg"
    shared.write_text("shared\n", encoding="utf-8")
    other.write_text("other\n", encoding="utf-8")
    window = MapWindow()
    window.path_edit.setText(f'"{left}"')
    window.add_from_path()
    window.add_location(str(right.parent))
    assert [Path(sample.path).name for sample in window.samples] == ["sample-left", "sample-right"]
    window.add_location(str(left))
    assert len(window.samples) == 2
    assert "Already in the list" in window.status_label.text()

    model = window.table.selectionModel()
    for row in (0, 1):
        model.select(
            window.table.model().index(row, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )
    window.set_configuration(str(shared))
    assert window.table.item(0, 1).text() == "shared.cfg"
    assert window.table.item(1, 1).text() == "shared.cfg"
    assert window.table.item(0, 1).toolTip() == str(shared)
    assert "2 folder" in window.status_label.text()

    window.table.clearSelection()
    window.table.selectRow(1)
    window.set_configuration(str(other))
    assert window.table.item(0, 1).text() == "shared.cfg"
    assert window.table.item(1, 1).text() == "other.cfg"
    assert window.table.item(1, 1).toolTip() == str(other)

    window.table.clearSelection()
    window.table.selectRow(0)
    window.remove_selected()
    assert [Path(sample.path).name for sample in window.samples] == ["sample-right"]
    assert window.assigned[window.samples[0].path] == str(other)

    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: warnings.append("info"))
    window.table.clearSelection()
    window.apply_selected()
    assert warnings


def test_each_folder_uses_its_own_configuration(tmp_path, monkeypatch):
    import xrfdesk.mapbatch as mapbatch

    cfg_a = _write_config(tmp_path / "alpha.cfg")
    cfg_b = _write_config(tmp_path / "beta.cfg")
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    _write_map(alpha / "MCA", [1], good=True)
    _write_map(beta / "MCA", [1], good=True)
    seen: list[tuple[str, str]] = []

    def fake(cfg, sample, workers, progress, cancel, together=False):
        seen.append((Path(cfg).name, Path(sample).name))
        if progress:
            progress(1)
        return ""

    monkeypatch.setattr(mapbatch, "_fit_folder", fake)
    skipped = run_maps(
        folders=[str(alpha), str(beta)],
        configs=[str(cfg_a), ""],
        workers=2,
        process_limit=2,
    )
    assert [result.status for result in skipped] == [OK, NO_CONFIG]
    assert seen == [("alpha.cfg", "alpha")]

    seen.clear()
    fitted = run_maps(
        folders=[str(alpha), str(beta)],
        configs=[str(cfg_a), str(cfg_b)],
        workers=2,
        process_limit=2,
    )
    assert [result.status for result in fitted] == [OK, OK]
    assert set(seen) == {("alpha.cfg", "alpha"), ("beta.cfg", "beta")}


def _empty_sample(folder: Path) -> Path:
    (folder / "MCA").mkdir(parents=True)
    (folder / "MCA" / "00001.mca").write_text("x\n", encoding="utf-8")
    return folder


def _write_config(path: Path) -> Path:
    from PyMca5.PyMcaPhysics.xrf.ClassMcaTheory import ClassMcaTheory

    from xrfdesk.curves import write_config

    path.parent.mkdir(parents=True, exist_ok=True)
    theory = ClassMcaTheory()
    config = theory.getConfiguration()
    config["peaks"] = {"Fe": "K"}
    config["detector"]["zero"] = 0.0
    config["detector"]["gain"] = 0.01
    config["detector"]["fixedzero"] = 1
    config["detector"]["fixedgain"] = 1
    config["fit"]["stripflag"] = 1
    config["fit"]["use_limit"] = 1
    config["fit"]["xmin"] = 400
    config["fit"]["xmax"] = 900
    config["fit"]["hypermetflag"] = 1
    config["fit"]["escapeflag"] = 0
    config["fit"]["sumflag"] = 0
    config["fit"]["strategyflag"] = 0
    config["fit"]["scatterflag"] = 0
    config["fit"]["maxiter"] = 4
    write_config(str(path), config)
    return path


def _write_map(folder: Path, numbers: list[int], good: bool) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for number in numbers:
        path = folder / f"{number:05d}.mca"
        if good:
            path.write_text(_amptek(_counts()), encoding="utf-8")
        else:
            path.write_text("not a spectrum\n", encoding="utf-8")


def _counts() -> np.ndarray:
    channels = np.arange(1024)
    counts = np.full(1024, 8.0)
    peak = np.exp(-0.5 * ((channels - 640) / 8) ** 2)
    return np.rint(counts + peak * (4000 / peak.sum()))


def _amptek(counts: np.ndarray) -> str:
    body = "\n".join(str(int(value)) for value in counts)
    return "<<PMCA SPECTRUM>>\nTAG - LIVE_TIME - 10\n<<CALIBRATION>>\n0\n0.01\n<<DATA>>\n" + body + "\n<<END>>\n"


def _bytes(sample: Path) -> dict[str, bytes]:
    found = {}
    for name in ("MCA", "Older cfg used"):
        folder = sample / name
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file():
                found[str(path.relative_to(sample))] = path.read_bytes()
    return found


def _fe_area(path: Path):
    import h5py

    with h5py.File(path, "r") as handle:
        found = None

        def visit(name, obj):
            nonlocal found
            if found is None and name.endswith("parameters/Fe_K"):
                found = obj[()]

        handle.visititems(visit)
    assert found is not None
    return found
