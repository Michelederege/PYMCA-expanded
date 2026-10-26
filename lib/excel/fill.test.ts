import JSZip from "jszip";
import { describe, expect, it } from "vitest";
import { autoBindings, guessHeaderRow } from "@/lib/excel/mapping";
import {
  compressionMethod,
  fillWorkbook,
  gridFromSheet,
  inspectWorkbook,
  parseSharedStrings,
} from "@/lib/excel/ooxml";
import { buildPracticeWorkbook } from "@/lib/excel/sample";

describe("workbook fill", () => {
  it("writes a changed template without touching formulas or macros", async () => {
    const practice = await buildPracticeWorkbook();
    const zip = await JSZip.loadAsync(practice);
    zip.file("xl/vbaProject.bin", Uint8Array.from([9, 8, 7, 6, 5]), { compression: "STORE" });
    const original = await zip.generateAsync({ type: "uint8array" });
    const preview = await inspectWorkbook(original);
    expect(preview.hasMacros).toBe(true);
    expect(preview.sheets.map((sheet) => sheet.name)).toEqual(["Results", "Wide"]);

    const results = preview.sheets[0];
    const headerRow = guessHeaderRow(results.rows);
    expect(headerRow).toBe(4);
    const bindings = autoBindings(results.rows[headerRow - 1], "long", []);
    expect(bindings.find((binding) => binding.header === "Peak Area")?.field).toBe("area");
    expect(bindings.find((binding) => binding.header === "Sample")?.field).toBe("sample");

    const records = [
      {
        sample: "Unknown bronze",
        element: "Fe",
        line: "Ka",
        energy_keV: 6.3995,
        area: 22500.25,
        fwhm_eV: 155.2,
        concentration: 1248.5,
        r2: 0.999,
        chi2: 812.4,
      },
      {
        sample: "Unknown bronze",
        element: "Cu",
        line: "Ka",
        energy_keV: 8.0411,
        area: 13000,
        fwhm_eV: 160,
        concentration: 518,
        r2: 0.998,
        chi2: 812.4,
      },
    ];

    const filled = await fillWorkbook(original, {
      sheet: "Results",
      headerRow,
      firstDataRow: headerRow + 1,
      bindings,
      records,
      clearExtras: true,
    });
    expect(filled.rowsWritten).toBe(2);
    expect(filled.cellsSkipped).toBe(0);

    const packed = await JSZip.loadAsync(filled.bytes);
    const sheet = await packed.file("xl/worksheets/sheet1.xml")!.async("string");
    expect(sheet).toContain("<f>COUNTA(A5:A400)</f>");
    expect(sheet).toContain("Unknown bronze");
    expect(sheet).toContain(">22500.25<");
    const macro = await packed.file("xl/vbaProject.bin")!.async("uint8array");
    expect([...macro]).toEqual([9, 8, 7, 6, 5]);
    expect(await compressionMethod(filled.bytes, "xl/vbaProject.bin")).toBe(0);

    const again = await fillWorkbook(filled.bytes, {
      sheet: "Results",
      headerRow,
      firstDataRow: headerRow + 1,
      bindings,
      records: records.slice(0, 1),
      clearExtras: true,
    });
    const sheet2 = await JSZip.loadAsync(again.bytes).then((next) =>
      next.file("xl/worksheets/sheet1.xml")!.async("string"),
    );
    expect(sheet2).toContain("Unknown bronze");
    expect(sheet2).not.toContain(">13000<");
    expect(sheet2).toContain("<f>COUNTA(A5:A400)</f>");

    const shared = parseSharedStrings(await packed.file("xl/sharedStrings.xml")!.async("string"));
    const grid = gridFromSheet(sheet, shared, 8, 12);
    expect(grid[4][0]).toBe("Unknown bronze");
    expect(grid[4][1]).toBe("Fe");
    expect(grid[5][1]).toBe("Cu");
  });

  it("refuses to overwrite a formula in a mapped column", async () => {
    const practice = await buildPracticeWorkbook();
    const zip = await JSZip.loadAsync(practice);
    const sheet = await zip.file("xl/worksheets/sheet1.xml")!.async("string");
    const withFormula = sheet.replace(
      "</sheetData>",
      `<row r="5"><c r="G5"><f>E5/20</f><v>0</v></c></row></sheetData>`,
    );
    zip.file("xl/worksheets/sheet1.xml", withFormula);
    const bytes = await zip.generateAsync({ type: "uint8array" });
    const preview = await inspectWorkbook(bytes);
    const headerRow = 4;
    const bindings = autoBindings(preview.sheets[0].rows[headerRow - 1], "long", []);
    const filled = await fillWorkbook(bytes, {
      sheet: "Results",
      headerRow,
      firstDataRow: 5,
      bindings,
      records: [
        {
          sample: "Alloy",
          element: "Fe",
          line: "Ka",
          energy_keV: 6.4,
          area: 10,
          fwhm_eV: 150,
          concentration: 99,
          r2: 1,
          chi2: 1,
        },
      ],
      clearExtras: false,
    });
    const xml = await JSZip.loadAsync(filled.bytes).then((next) =>
      next.file("xl/worksheets/sheet1.xml")!.async("string"),
    );
    expect(xml).toContain("<f>E5/20</f>");
    expect(xml).not.toContain(">99<");
    expect(filled.cellsSkipped).toBe(1);
    expect(filled.warnings.some((warning) => warning.includes("G5"))).toBe(true);
    expect(xml).toContain("Alloy");
  });
});
