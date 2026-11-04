# Fit and Batch

Two applications for energy-dispersive XRF. Fit is the session: calibrate a spectrum, name the lines, strip the background, and extract non-negative peak areas. Standards in that session become a calibration curve. Batch is separate. It takes a saved configuration and runs it over its own file list, the way PyMca Batch is its own program.

Neither application is the ESRF [PyMca](https://github.com/silx-kit/pymca) program, and neither reproduces PyMca’s fundamental-parameter quantification or imaging tools. Peak areas come from a detector-resolution gaussian fit. Concentrations come from your standards, stored in the configuration Batch reads.

The workbook is never hard-coded. Upload an `.xlsx` or `.xlsm`, pick the sheet and header row, and match each column to a result. Save that mapping and load it again when the template changes. Formulas are left in place. VBA in an `.xlsm` is copied through unchanged, including files larger than 50 MB. The file stays in the browser.

## Run

```bash
npm install
npm run dev
```

Open [http://127.0.0.1:43123](http://127.0.0.1:43123) for Fit. Batch is [http://127.0.0.1:43123/batch](http://127.0.0.1:43123/batch). Fit’s **Open Batch** hands the current configuration to a separate window.

```bash
npm test
npm run lint
```

## Fit

Load a CSV or plain text file:

- one column of counts, or
- `energy, counts` (comma, tab, or whitespace)

The bronze demo loads three spectra: two Fe/Cu/Zn standards and an unknown with lead L lines. Mark a spectrum as a standard and type the known concentrations to build the curve. Two standards produce a slope, intercept, and R². One standard is forced through the origin. **Save configuration** writes that fit, including the curves, to a JSON file.

## Batch

Batch does not share Fit’s spectrum list. Add the scans to run, open a configuration (or take the one Fit just handed over), and press **Start**. Every file in the list is fitted in the order you left it. Remove a file to leave it out. Concentrations come from the curves stored in the configuration, so the standards do not have to be in the list.

The output is a CSV, downloaded or written into a folder you choose, plus the same Excel template fill. The bronze example loads a configuration and the three demo scans so Batch can be tried on its own.

A scan file can hold more than one spectrum:

- a block per scan, started by `# scan: name` or a SPEC `#S` line (`# role`, `# live time`, and `# known: Fe 500` sit under that header)
- a table whose first row names each scan, with an optional `energy` or `channel` column

## Excel

1. Open the Excel template section.
2. Load your workbook, or use the practice template to see the shape.
3. Set the header row. The preview highlights it.
4. Choose **one row per peak** or **one row per sample**.
5. Point each header at a field. Unmapped columns are not touched.
6. Download the filled copy. The original file is not modified.

A mapping file (`curve-fit-mapping.json`) stores the sheet name, header row, and column bindings. If a later template renames or drops a column, those bindings are reported and the new headers are matched again.

## Limits

- The fit is a stripped background plus gaussian lines at library energies. It is not a Hypermet or fundamental-parameter model.
- Si escape peaks are optional and use a fixed yield.
- Pile-up is not modeled.
- Very large workbooks are unpacked in memory. Give the browser a moment on a 50 MB file.
