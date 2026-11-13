"""Command line and application entry.

With no arguments this opens the Fit window.
With ``--cfg`` it fits the given files and writes a CSV, without a window.
"""

from __future__ import annotations

import argparse
import multiprocessing
import sys

from xrfdesk.batch import default_workers, run_batch, write_csv
from xrfdesk.curves import curves_from_config, read_config
from xrfdesk.demo import bronze_files
from xrfdesk.excel_fill import fill_workbook


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(prog="xrfdesk", description="Fit XRF spectra with PyMca.")
    parser.add_argument("--cfg", help="PyMca .cfg configuration")
    parser.add_argument("--out", help="CSV file to write")
    parser.add_argument("--workers", type=int, default=default_workers(), help="Worker processes (default: CPU cores minus 1)")
    parser.add_argument("--excel", help="Existing .xlsx or .xlsm template")
    parser.add_argument("--excel-out", help="Where to write the filled workbook")
    parser.add_argument("--bronze", action="store_true", help="Run the bronze example")
    parser.add_argument("files", nargs="*", help="Spectrum files, in the order they should be reported")
    args = parser.parse_args(argv)

    if args.bronze or args.cfg or args.files:
        return _batch_cli(args)
    _launch_gui()
    return 0


def _batch_cli(args) -> int:
    if args.bronze:
        config_path, scans, template = bronze_files()
        config_file = str(config_path)
        files = [str(path) for path in scans]
        if args.excel is None:
            args.excel = str(template) if args.excel_out else None
    else:
        if not args.cfg:
            print("A --cfg configuration is required.", file=sys.stderr)
            return 2
        if not args.files:
            print("Give at least one spectrum file.", file=sys.stderr)
            return 2
        config_file = args.cfg
        files = list(args.files)
    if not args.out:
        print("Give --out for the CSV results.", file=sys.stderr)
        return 2
    config = read_config(config_file)
    results = run_batch(files, config, workers=args.workers)
    curves = curves_from_config(config)
    write_csv(args.out, results, [curve.element for curve in curves], [curve.group for curve in curves])
    if args.excel or args.excel_out:
        if not args.excel or not args.excel_out:
            print("Excel fill needs both --excel and --excel-out.", file=sys.stderr)
            return 2
        fill_workbook(args.excel, args.excel_out, results, [curve.element for curve in curves])
    failed = 0
    for result in results:
        if result.status == "done":
            print(f"done    {result.sample}  chi-square {result.chisq:.4f}")
        else:
            failed += 1
            print(f"{result.status:7} {result.sample}  {result.error or ''}", file=sys.stderr)
    print(f"Wrote {args.out}")
    return 1 if failed else 0


def _launch_gui() -> None:
    from PySide6.QtWidgets import QApplication

    from xrfdesk.gui.fit_window import FitWindow
    from xrfdesk.launch import apply_window_icon, install_exception_dialog, prepare_windowed_launch

    prepare_windowed_launch()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("xrfdesk")
    apply_window_icon(app)
    install_exception_dialog()
    window = FitWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
