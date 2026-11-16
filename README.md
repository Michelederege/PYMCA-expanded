# xrfdesk

A desktop program for energy-dispersive X-ray fluorescence. [PyMca5](https://github.com/vasole/pymca) (MIT) does the fitting. This program does not reimplement the peak model.

Fit is one spectrum at a time. Batch is a separate window that runs one PyMca `.cfg` over its own file list. The program runs offline.

![Fit window](docs/fit-window.jpg)

## Download

GitHub builds the program. Open the **package** workflow for this repository and download `xrfdesk-windows` or `xrfdesk-linux`. Unzip it and open `xrfdesk.exe` on Windows, or `xrfdesk` on Linux. `How to open.txt` in that folder says the same thing.

Leave the unzipped folder as it is. The program needs the files beside it. That computer does not need Python.

## Requirements

Python 3.12. The pinned PyMca5 build in `requirements.txt` is the Python 3.12 wheel.

`fisx`, which PyMca uses, needs a C compiler and Python headers the first time it is installed (`python3-dev` and `g++` on Debian or Ubuntu).

## Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m xrfdesk
```

On Windows, activate the virtual environment with `.venv\Scripts\activate`.

That opens the Fit window. Batch is a second window, opened from Fit or from the bronze example inside Batch.

## Standalone program

```bash
./build.sh
```

That is `python3 build.py`. It runs PyInstaller for the machine you are on and installs an icon. The built folder is `dist/xrfdesk/`. It is not committed. Copy that whole folder to another machine; that machine does not need Python installed.

Click the **xrfdesk** icon. The Fit window opens on its own. The desktop entry has `Terminal=false`, and on Windows the program is built without a console. Double-click `dist\xrfdesk\xrfdesk.exe` there. If a file manager opens a terminal just to start the program, that terminal closes and the Fit window stays. Passing `--cfg` from a terminal you opened yourself still prints the batch log in that terminal.

## Spectrum files

- `.csv` and `.txt`: one column of counts, or `channel, counts`, or `energy, counts`
- Amptek `.mca` text (`<<DATA>>`, optional `<<CALIBRATION>>`)
- IAEA `.spe` text (`$DATA`, optional `$ENER_FIT`)

A calibration stored in the file is applied on top of the `.cfg`. The bronze files have no calibration of their own; `bronze.cfg` supplies zero and gain.

## Fit window

PyMca's advanced-fit panel is embedded here. Use its **Configure** button for the energy calibration, the elements and lines, and the fit parameters, and **Fit Again!** to draw the fit.

**Record as standard** stores the peak areas of the spectrum you are viewing together with the concentrations you type. One standard is forced through the origin. Two or more produce a slope, an intercept, and an R². **Save configuration** writes a normal PyMca `.cfg`, plus a `curves` section. PyMca ignores that section, so the file still opens there. A `.cfg` saved by PyMca opens here; it simply has no curves until you record standards.

**Open Batch** shows the Batch window with that configuration. The Batch file list starts empty.

## Batch window

Add, remove, and reorder files. The list is not the Fit window's spectrum. Load a `.cfg`, or press **Bronze example** to load `examples/bronze/bronze.cfg` and its three scans without using Fit.

**Start** fits the list in parallel. The process count follows physical cores. A 12-core processor with 24 threads is 12 cores, and the default leaves two of them free. Fit processes run at low priority and stay off the free cores, so Excel and a browser stay usable. A second batch waits instead of starting another full set of processes. Each row is waiting, running, done, or failed with the error text. **Cancel** stops the run. A file that fails does not stop the others. The results stay in the original list order.

Concentrations use the curves stored in the configuration. The standards do not have to be in the list.

**Export CSV** asks where to save. **Fill Excel template** asks for a workbook and where to write the copy.

## Map batch

**Open map batch** fits every `.mca` file in a sample's `MCA` folder and writes the same output as PyMca's Batch Fitting window.

The sample root is the folder that contains the sample folders, for example `C:\Data Workup FD\`. A sample folder contains `MCA`. The window reads the file names itself. It does not open PyMca's file dialog, which stops responding on a folder of thousands of `.mca` files when the file type filter is HDF5.

`Configuration Files for PyMCA` can hold more than one `.cfg`. The window lists those files. Start stays stopped until you select one, and that one file is used for every sample in the run. The window does not pick a file for you. `Older cfg used` is not in the list. **Configuration** can open a `.cfg` from somewhere else. The command needs `--cfg` for the same reason.

For each sample that has no results yet, the options match a manual batch run:

- `.fit` files off, the report off, concentrations off, diagnostics off, ROI fitting off
- HDF5, CSV, DAT, and EDF on
- TIFF off, multipage off
- ROI width 100 eV
- The process count is shared by the sample folders. It is one process per physical core at most, and the default leaves cores free: one core on a small machine, two cores when the machine has eight or more. A 12-core, 24-thread processor defaults to 10 fit processes, so five folders run together with two processes each, and ten folders can run at once. Hyper-threads are not extra fit processes. One folder uses the whole count. One process fits in this program. More than one process splits that folder the same way PyMca does. The fit processes run at low priority and are kept off the free cores, so Excel and a browser stay usable while a fit is running.

The sample folder then holds `00001_to_<last>.h5`. `IMAGES` holds `00001_to_<last>.cfg`, `.csv`, `.dat`, and the EDF peak images. The output folder is the sample folder, next to `MCA`, not inside `MCA` and not inside `IMAGES`. A finished row says `OK · in this folder`. Double-click that row, or press **Open folder**, to open the sample folder. Hover the `.h5` name for the full path.

A sample that already has an `.h5` file or an `IMAGES` folder is skipped. The window asks before overwriting those. `MCA` and `Older cfg used` are not deleted or moved. The run keeps a sample only when the `.h5` row count, the CSV rows, the DAT rows, the EDF image size, and the saved `.cfg` peaks all agree with the MCA files and the configuration that was selected. If they do not, that attempt is removed. Folders that are already fitting finish, their results stay, and the later folders are left untouched.

Folders of 12,000 to 15,000 spectra are the size this is built for. The areas match a one-process PyMca batch fit. While a folder is fitting, its status is a percent and the estimated time left, for example `42% · 14 min left`. The bar under the table is the total of every folder in the run. Each folder keeps its own percent, so the rows do not take turns on one line.

```bash
python -m xrfdesk --map-root "C:\Data Workup FD" --cfg "C:\Data Workup FD\Configuration Files for PyMCA\M Series 11112026.cfg"
```

`--map-folder` names one sample folder and can be repeated. `--workers` sets how many fit processes those folders share. The run leaves at least one core free even if the number is higher. `--overwrite` refits a sample that already has results. The command prints `folder | mca files | output h5 | status`.

### Excel layout

Sheet `XRF`. Row 1 is the header. The first scan is row 2, one row per scan.

| Cell | Contents |
| --- | --- |
| A1 | `Sample` |
| B1, C1, … | Element symbols, in the order of the curves in the `.cfg` |
| A2 | First file name |
| B2 | That file's concentration for the first element |

For the bronze configuration the curve order is Fe, Cu, Zn, so B is Fe, C is Cu, D is Zn, and the first iron concentration is B2. Other sheets, formulas, and cells outside these columns are left as they are.

## Updates

The packaged program can update itself. Pushing `main` on GitHub publishes `xrfdesk-windows.zip` and `xrfdesk-linux.zip` as the **latest** release. **Check for updates**, in the Fit window or the map batch window, reads that release. **Update** downloads it, waits until this program exits, replaces the program folder, and opens the new copy.

The program looks for that release on `michele-de-rege/pymca-excelsheet-improvments`. Set `XRFDESK_GITHUB_REPO` to `owner/name` if the GitHub repository is different. The repository has to be public for the check to work with no token. If it is private, **GitHub token** saves a token that can read releases in the home directory. The token is not written into the program or the updater.

A copy started from source does not replace the source tree. Use git pull for that copy.

The release notes contain `version:` and `sha:`. A packaged build compares that sha with the commit it was built from.

## Command line

```bash
python -m xrfdesk --cfg config.cfg --out results.csv --workers 4 scan1.csv scan2.csv
```

The same flags work on the built program:

```bash
./dist/xrfdesk/xrfdesk --cfg config.cfg --out results.csv --workers 4 scan1.csv scan2.csv
```

`--bronze` uses the included example:

```bash
python -m xrfdesk --bronze --out bronze.csv --workers 2
```

`--excel template.xlsx --excel-out filled.xlsx` fills the template described above.

## Tests

```bash
python -m pytest
```

The bronze batch matches fitting those three scans one at a time in the Fit window, and a two-worker run matches a one-worker run. A second set of 15 simulated spectra, each from 10,000 to 15,000 channels, does the same. Their concentrations stay within 2% of the values used to generate them.

A randomized MCA map is fitted with this program and with PyMca's own batch fitter. The peak areas match, including when several processes split the folder. `XRFDESK_SIM_SPECTRA=15000` runs that check at the size of a full map:

```bash
XRFDESK_SIM_SPECTRA=15000 python -m pytest tests/test_sim.py
```

## Limits

Quantification in the Fit and Batch windows is the empirical curve stored in the `.cfg`, not PyMca's fundamental-parameter concentrations. Map batch leaves concentrations off, as a PyMca map batch does, and writes peak areas. The interactive fit, the peak model, and the `.cfg` contents that PyMca itself understands are PyMca's.

## License

xrfdesk is released under the [MIT License](LICENSE). PyMca5 is MIT, copyright the European Synchrotron Radiation Facility. fisx, which PyMca uses for X-ray cross sections, is MIT as well.
