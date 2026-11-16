"""Map output compared with PyMca's own batch fitter.

The default size stays small enough for a normal test run. A full map is:

    XRFDESK_SIM_SPECTRA=15000 python -m pytest tests/test_sim.py
"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

import numpy as np

from xrfdesk.mapbatch import output_root, run_maps


def test_randomized_map_matches_pymca(tmp_path):
    n = int(os.environ.get("XRFDESK_SIM_SPECTRA", "24"))
    if n < 1:
        raise AssertionError("XRFDESK_SIM_SPECTRA must be at least 1.")
    cfg = _write_config(tmp_path / "fit.cfg")
    serial = tmp_path / "serial"
    parallel = tmp_path / "parallel"
    _write_randomized_map(serial / "MCA", n, seed=15000)
    _clone(serial / "MCA", parallel / "MCA")
    files = [str(path) for path in sorted((serial / "MCA").iterdir())]
    _pymca_batch(str(cfg), files, str(serial))
    workers = 1 if n < 4 else 3
    result = run_maps(str(cfg), folders=[str(parallel)], workers=workers, process_limit=workers)[0]
    assert result.status == "OK"
    assert result.mca_count == n
    assert result.h5_name == f"{output_root(files)}.h5"
    expected = _parameters(serial / result.h5_name)
    actual = _parameters(parallel / result.h5_name)
    assert sorted(actual) == sorted(expected)
    assert expected
    for name in expected:
        assert actual[name].shape == expected[name].shape
        assert actual[name].shape[0] == n
        difference = np.nanmax(np.abs(actual[name] - expected[name]))
        assert difference == 0, f"{name} differed by {difference}"
    assert _table_rows(serial / "IMAGES" / f"{output_root(files)}.csv") == n
    assert _table_rows(parallel / "IMAGES" / f"{output_root(files)}.csv") == n


def _pymca_batch(cfg: str, files: list[str], output: str) -> None:
    from PyMca5.PyMcaPhysics.xrf.McaAdvancedFitBatch import McaAdvancedFitBatch

    batch = McaAdvancedFitBatch(
        cfg,
        filelist=files,
        outputdir=output,
        roifit=0,
        roiwidth=100,
        overwrite=1,
        fitfiles=0,
        concentrations=0,
        fitimages=1,
        quiet=True,
        filebeginoffset=0,
        fileendoffset=0,
        filestep=1,
        mcaoffset=0,
        mcastep=1,
        h5=1,
        csv=1,
        dat=1,
        edf=1,
        tif=0,
        multipage=0,
        diagnostics=0,
    )
    batch.processList()


def _write_config(path: Path) -> Path:
    from PyMca5.PyMcaPhysics.xrf.ClassMcaTheory import ClassMcaTheory

    from xrfdesk.curves import write_config

    path.parent.mkdir(parents=True, exist_ok=True)
    theory = ClassMcaTheory()
    config = theory.getConfiguration()
    config["peaks"] = {"Fe": "K", "Cu": "K", "Zn": "K"}
    config["detector"]["zero"] = 0.0
    config["detector"]["gain"] = 0.01
    config["detector"]["fixedzero"] = 1
    config["detector"]["fixedgain"] = 1
    config["fit"]["stripflag"] = 1
    config["fit"]["use_limit"] = 1
    config["fit"]["xmin"] = 400
    config["fit"]["xmax"] = 950
    config["fit"]["hypermetflag"] = 1
    config["fit"]["escapeflag"] = 0
    config["fit"]["sumflag"] = 0
    config["fit"]["strategyflag"] = 0
    config["fit"]["scatterflag"] = 0
    config["fit"]["maxiter"] = 4
    write_config(str(path), config)
    return path


def _write_randomized_map(folder: Path, count: int, seed: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    channels = np.arange(1024)
    # Fe, Cu, and Zn K lines at 10 eV per channel.
    centers = (640.0, 804.0, 863.0)
    for index in range(count):
        counts = np.full(1024, rng.uniform(4.0, 14.0))
        for center in centers:
            height = rng.uniform(300.0, 12000.0)
            width = rng.uniform(6.5, 10.5)
            shift = rng.normal(0.0, 0.35)
            counts += height * np.exp(-0.5 * ((channels - (center + shift)) / width) ** 2)
        drawn = rng.poisson(np.clip(counts, 0, None))
        path = folder / f"{index + 1:05d}.mca"
        path.write_text(_amptek(drawn), encoding="utf-8")


def _clone(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        os.link(path, destination / path.name)


def _amptek(counts: np.ndarray) -> str:
    body = "\n".join(str(int(value)) for value in counts)
    return "<<PMCA SPECTRUM>>\nTAG - LIVE_TIME - 10\n<<CALIBRATION>>\n0\n0.01\n<<DATA>>\n" + body + "\n<<END>>\n"


def _parameters(path: Path) -> dict[str, np.ndarray]:
    import h5py

    found: dict[str, np.ndarray] = {}
    with h5py.File(path, "r") as handle:

        def visit(name, obj):
            if hasattr(obj, "shape") and getattr(obj.dtype, "kind", "") == "f" and "parameters" in name.split("/"):
                found[name] = np.array(obj[()])

        handle.visititems(visit)
    return found


def _table_rows(path: Path) -> int:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return max(0, len(lines) - 1)
