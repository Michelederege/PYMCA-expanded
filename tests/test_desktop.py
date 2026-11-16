import os
from pathlib import Path
from threading import Event

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from PyMcaExpanded.batch import FAILED, run_batch
from PyMcaExpanded.cli import main
from PyMcaExpanded.curves import curves_from_config, read_config
from PyMcaExpanded.demo import bronze_files, write_bronze_example
from PyMcaExpanded.engine import fit_spectrum
from PyMcaExpanded.excel_fill import fill_workbook
from PyMcaExpanded.spectra import load_spectrum
from openpyxl import load_workbook


@pytest.fixture(scope="module")
def bronze(tmp_path_factory):
    folder = tmp_path_factory.mktemp("bronze")
    write_bronze_example(folder)
    return folder


def _areas(outcome):
    return {key: round(value, 4) for key, value in outcome.areas.items()}


def test_batch_matches_fitting_each_scan(bronze):
    from PySide6.QtWidgets import QApplication

    from PyMcaExpanded.gui.fit_window import FitWindow

    app = QApplication.instance() or QApplication([])
    config_path, scans, _template = bronze_files_from(bronze)
    window = FitWindow()
    window.load_configuration(str(config_path))
    one_at_a_time = []
    for scan in scans:
        window.open_spectrum(str(scan))
        one_at_a_time.append(window.fit_current())
    batch = run_batch([str(scan) for scan in scans], window.current_config(), workers=1)
    assert [result.status for result in batch] == ["done", "done", "done"]
    for single, result in zip(one_at_a_time, batch):
        assert _areas(single) == {key: round(value, 4) for key, value in result.areas.items()}
        assert round(single.chisq, 6) == round(result.chisq, 6)
        assert single.concentrations.keys() == result.concentrations.keys()
        for element, value in single.concentrations.items():
            assert value == pytest.approx(result.concentrations[element], rel=0, abs=1e-6)
    app.processEvents()


def test_parallel_matches_single_worker(bronze):
    config_path, scans, _template = bronze_files_from(bronze)
    config = read_config(str(config_path))
    files = [str(scan) for scan in scans]
    serial = run_batch(files, config, workers=1)
    parallel = run_batch(files, config, workers=2)
    assert [item.sample for item in parallel] == [item.sample for item in serial]
    for left, right in zip(serial, parallel):
        assert left.areas == right.areas
        assert left.chisq == right.chisq
        assert left.concentrations == right.concentrations


def test_a_failed_file_does_not_stop_the_batch(bronze, tmp_path):
    config_path, scans, _template = bronze_files_from(bronze)
    bad = tmp_path / "empty.csv"
    bad.write_text("not a spectrum\n", encoding="utf-8")
    files = [str(scans[0]), str(bad), str(scans[2])]
    results = run_batch(files, read_config(str(config_path)), workers=2)
    assert [result.status for result in results] == ["done", FAILED, "done"]
    assert results[1].error
    assert results[0].areas["Fe K"] > 0
    assert results[2].concentrations["Fe"] == pytest.approx(1250, rel=0.2)


def test_cancel_before_start_fits_nothing(bronze):
    config_path, scans, _template = bronze_files_from(bronze)
    cancel = Event()
    cancel.set()
    results = run_batch([str(scan) for scan in scans], read_config(str(config_path)), workers=1, cancel=cancel)
    assert [result.status for result in results] == ["cancelled", "cancelled", "cancelled"]


def test_excel_fill_uses_row_two(bronze, tmp_path):
    config_path, scans, template = bronze_files_from(bronze)
    config = read_config(str(config_path))
    results = run_batch([str(scan) for scan in scans], config, workers=1)
    filled = tmp_path / "filled.xlsx"
    elements = [curve.element for curve in curves_from_config(config)]
    fill_workbook(str(template), str(filled), results, elements)
    sheet = load_workbook(filled)["XRF"]
    assert [sheet.cell(1, column).value for column in range(1, 5)] == ["Sample", *elements]
    assert sheet["A2"].value == "std_500"
    assert sheet["A4"].value == "unknown"
    iron = sheet.cell(4, 1 + elements.index("Fe") + 1).value
    assert iron == pytest.approx(1250, rel=0.2)
    notes = load_workbook(filled)["Notes"]
    assert notes["A1"].value.startswith("Batch writes")


def test_cli_bronze(bronze, tmp_path, monkeypatch):
    monkeypatch.setattr("PyMcaExpanded.cli.bronze_files", lambda: bronze_files_from(bronze))
    out = tmp_path / "results.csv"
    code = main(["--bronze", "--out", str(out), "--workers", "2"])
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "unknown" in text
    assert text.splitlines()[1].startswith("std_500,done")


def test_mca_and_spe_readers(tmp_path):
    mca = tmp_path / "sample.mca"
    mca.write_text("<<CALIBRATION>>\n0\n0.01\n<<DATA>>\n" + "\n".join(["1"] * 16) + "\n<<END>>\n", encoding="utf-8")
    loaded = load_spectrum(mca)
    assert loaded.counts.size == 16
    assert loaded.zero == 0
    assert loaded.gain == 0.01
    spe = tmp_path / "sample.spe"
    spe.write_text("$SPEC_ID:\ndemo\n$DATA:\n0 7\n" + "\n".join(str(i) for i in range(8)) + "\n$ENER_FIT:\n0.0 0.02\n", encoding="utf-8")
    loaded = load_spectrum(spe)
    assert loaded.counts.tolist() == list(range(8))
    assert loaded.gain == pytest.approx(0.02)


def bronze_files_from(folder: Path):
    scans = [folder / "std_500.csv", folder / "std_2000.csv", folder / "unknown.csv"]
    return folder / "bronze.cfg", scans, folder / "template.xlsx"


def test_batch_window_keeps_list_order(bronze):
    import time

    from PySide6.QtWidgets import QApplication

    from PyMcaExpanded.gui.batch_window import BatchWindow

    app = QApplication.instance() or QApplication([])
    config_path, scans, _template = bronze_files_from(bronze)
    window = BatchWindow()
    window.load_configuration(str(config_path))
    window.add_files([str(scan) for scan in scans])
    window.file_table.setCurrentCell(0, 0)
    window.move_selected(1)
    assert [window.file_table.item(row, 0).text() for row in range(3)] == ["std_2000", "std_500", "unknown"]
    window.remove_selected()
    assert [window.file_table.item(row, 0).text() for row in range(2)] == ["std_2000", "unknown"]
    window.paths = [str(scan) for scan in scans]
    window._fill_rows()
    window.workers.setValue(2)
    window.start()
    deadline = time.time() + 60
    while window._thread is not None and window._thread.isRunning():
        app.processEvents()
        time.sleep(0.05)
        if time.time() > deadline:
            window.cancel()
            raise AssertionError("Batch window did not finish.")
    app.processEvents()
    assert [result.status for result in window.results] == ["done", "done", "done"]
    assert [window.file_table.item(row, 0).text() for row in range(3)] == ["std_500", "std_2000", "unknown"]
    assert [window.file_table.item(row, 1).text() for row in range(3)] == ["done", "done", "done"]
    headers = [window.file_table.horizontalHeaderItem(column).text() for column in range(window.file_table.columnCount())]
    assert headers == ["File", "Status", "Detail", "Fe", "Cu", "Zn"]
    iron = float(window.file_table.item(2, 3).text())
    assert iron == pytest.approx(window.results[2].concentrations["Fe"])
    assert window.progress.value() == 3


def test_shipped_example_matches_generator(tmp_path):
    """The files shipped with the app are the bronze example the generator writes.

    The calibration slopes come from a fit, so the last digits can differ between
    machines. The spectra and the rest of the configuration must match exactly.
    """
    write_bronze_example(tmp_path)
    shipped = Path(__file__).resolve().parents[1] / "examples" / "bronze"
    if not (shipped / "bronze.cfg").exists():
        pytest.skip("shipped bronze example is generated by the test run")
    for name in ("std_500.csv", "std_2000.csv", "unknown.csv"):
        assert (shipped / name).read_bytes() == (tmp_path / name).read_bytes()
    shipped_cfg = read_config(str(shipped / "bronze.cfg"))
    fresh_cfg = read_config(str(tmp_path / "bronze.cfg"))
    shipped_curves = curves_from_config(shipped_cfg)
    fresh_curves = curves_from_config(fresh_cfg)
    shipped_cfg.pop("curves", None)
    fresh_cfg.pop("curves", None)
    assert shipped_cfg == fresh_cfg
    assert [(curve.element, curve.group) for curve in shipped_curves] == [
        (curve.element, curve.group) for curve in fresh_curves
    ]
    for shipped_curve, fresh_curve in zip(shipped_curves, fresh_curves):
        assert shipped_curve.slope == pytest.approx(fresh_curve.slope, rel=1e-6, abs=1e-9)
        assert shipped_curve.intercept == pytest.approx(fresh_curve.intercept, rel=1e-6, abs=1e-9)
        assert shipped_curve.r2 == pytest.approx(fresh_curve.r2, rel=1e-6, abs=1e-9)
