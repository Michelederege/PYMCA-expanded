"""Fifteen simulated spectra of 10,000 to 15,000 channels."""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from PyMcaExpanded.batch import FAILED, run_batch
from PyMcaExpanded.curves import read_config
from PyMcaExpanded.engine import fit_spectrum
from PyMcaExpanded.launch import desktop_entry
from PyMcaExpanded.spectra import list_labels, load_spectrum
from PyMcaExpanded.wide import LENGTHS, RECIPES, write_wide_set


@pytest.fixture(scope="module")
def wide(tmp_path_factory):
    folder = tmp_path_factory.mktemp("wide")
    paths, config_path = write_wide_set(folder)
    return paths, read_config(str(config_path))


def test_lengths_are_in_range():
    assert len(LENGTHS) == 15
    assert min(LENGTHS) == 10000
    assert max(LENGTHS) == 15000


def test_wide_batch_matches_one_at_a_time(wide):
    paths, config = wide
    loaded = [load_spectrum(path) for path in paths]
    assert [spectrum.counts.size for spectrum in loaded] == LENGTHS
    singles = [fit_spectrum(spectrum, config) for spectrum in loaded]
    serial = run_batch([str(path) for path in paths], config, workers=1)
    parallel = run_batch([str(path) for path in paths], config, workers=2)
    assert [result.status for result in serial] == ["done"] * 15
    assert [result.sample for result in parallel] == [result.sample for result in serial]
    for single, left, right in zip(singles, serial, parallel):
        assert left.areas == right.areas
        assert left.chisq == right.chisq
        assert left.concentrations == right.concentrations
        assert left.areas == {key: pytest.approx(value, rel=0, abs=1e-6) for key, value in single.areas.items()}
        assert left.chisq == pytest.approx(single.chisq, rel=0, abs=1e-6)
        assert left.concentrations == {
            key: pytest.approx(value, rel=0, abs=1e-6) for key, value in single.concentrations.items()
        }
        assert set(left.concentrations) == {"Fe", "Cu", "Zn"}
    for (_name, known), result in zip(RECIPES, serial):
        for element, target in known.items():
            assert result.concentrations[element] == pytest.approx(target, rel=0.02)


def test_a_bad_file_does_not_change_the_others(wide, tmp_path):
    paths, config = wide
    bad = tmp_path / "notes.csv"
    bad.write_text("this is not a spectrum\n", encoding="utf-8")
    files = [str(paths[0]), str(bad), str(paths[14])]
    alone = run_batch([str(paths[0]), str(paths[14])], config, workers=1)
    mixed = run_batch(files, config, workers=2)
    assert [result.status for result in mixed] == ["done", FAILED, "done"]
    assert mixed[1].error
    assert mixed[0].areas == alone[0].areas
    assert mixed[2].areas == alone[1].areas
    assert mixed[0].concentrations == alone[0].concentrations
    assert mixed[2].concentrations == alone[1].concentrations


def test_duplicate_names_keep_their_folder():
    labels = list_labels(
        [
            "/data/morning/scan.csv",
            "/data/evening/scan.csv",
            "/data/evening/other.csv",
        ]
    )
    assert labels == ["morning/scan", "evening/scan", "other"]


def test_desktop_launcher_does_not_open_a_terminal(tmp_path: Path):
    text = desktop_entry(tmp_path / "dist" / "PyMca Expanded", tmp_path / "PyMca Expanded.png")
    assert "Name=PyMca Expanded" in text
    assert "Terminal=false" in text
    assert "x-terminal-emulator" not in text
    assert "bash" not in text
    assert "gnome-terminal" not in text
    assert text.split("Exec=", 1)[1].splitlines()[0] == '"%s"' % (tmp_path / "dist" / "PyMca Expanded")
    assert 'Path="' not in text
