# Curve Fit

An energy-dispersive XRF workbench that follows the PyMca session: calibrate the spectrum, identify lines, strip the background, and extract non-negative peak areas. Standards become a calibration curve. The results are written into an Excel workbook you choose.

This is not the ESRF [PyMca](https://github.com/silx-kit/pymca) application, and it does not reproduce PyMca’s fundamental-parameter quantification or imaging tools. Peak areas come from a detector-resolution gaussian fit. Concentrations come from your standards.

The workbook is never hard-coded. Upload an `.xlsx` or `.xlsm`, pick the sheet and header row, and match each column to a result. Save that mapping and load it again when the template changes. Formulas are left in place. VBA in an `.xlsm` is copied through unchanged, including files larger than 50 MB. The file stays in the browser.

## Run

```bash
npm install
npm run dev
```

Open [http://127.0.0.1:43123](http://127.0.0.1:43123).

```bash
npm test
npm run lint
```

## Spectra

Load a CSV or plain text file:

- one column of counts, or
- `energy, counts` (comma, tab, or whitespace)

The bronze demo loads three spectra: two Fe/Cu/Zn standards and an unknown with lead L lines. Mark a spectrum as a standard and type the known concentrations to build the curve. Two standards produce a slope, intercept, and R². One standard is forced through the origin.

## Excel

1. Open the Excel template tab.
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
