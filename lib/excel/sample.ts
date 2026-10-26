import { escapeXml } from "@/lib/excel/ooxml";

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>`;

export async function buildPracticeWorkbook(): Promise<Uint8Array> {
  const strings = [
    "Beta XRF curve fit",
    "Practice template. Swap in your own workbook when you have it. Formulas on this sheet are left alone.",
    "Filled peak rows",
    "Sample",
    "Element",
    "Line",
    "Energy (keV)",
    "Peak Area",
    "FWHM (eV)",
    "Concentration",
    "R2",
    "Chi-square",
    "Fe Ka",
    "Cu Ka",
    "Zn Ka",
    "Pb La",
  ];
  const results = sheetXml(
    "A1:L4",
    [
      `<row r="1"><c r="A1" t="s"><v>0</v></c></row>`,
      `<row r="2"><c r="A2" t="s"><v>1</v></c><c r="J2" t="s"><v>2</v></c><c r="K2"><f>COUNTA(A5:A400)</f><v>0</v></c></row>`,
      `<row r="4">${["3", "4", "5", "6", "7", "8", "9", "10", "11"]
        .map((index, column) => `<c r="${String.fromCharCode(65 + column)}4" t="s"><v>${index}</v></c>`)
        .join("")}</row>`,
    ].join(""),
  );
  const wide = sheetXml(
    "A1:F1",
    `<row r="1"><c r="A1" t="s"><v>3</v></c><c r="B1" t="s"><v>12</v></c><c r="C1" t="s"><v>13</v></c><c r="D1" t="s"><v>14</v></c><c r="E1" t="s"><v>15</v></c><c r="F1" t="s"><v>11</v></c></row><row r="20"><c r="H20"><f>SUM(B2:E19)</f><v>0</v></c></row>`,
  );
  return packXlsx([
    ["[Content_Types].xml", contentTypes(false)],
    ["_rels/.rels", rootRels()],
    ["xl/workbook.xml", workbookXml(["Results", "Wide"])],
    ["xl/_rels/workbook.xml.rels", workbookRels(2)],
    ["xl/styles.xml", STYLES],
    ["xl/sharedStrings.xml", sharedStrings(strings)],
    ["xl/worksheets/sheet1.xml", results],
    ["xl/worksheets/sheet2.xml", wide],
  ]);
}

export async function packXlsx(files: [string, string | Uint8Array][]): Promise<Uint8Array> {
  const JSZip = (await import("jszip")).default;
  const zip = new JSZip();
  for (const [name, content] of files) {
    const store = /vbaProject\.bin$/i.test(name);
    zip.file(name, content, { compression: store ? "STORE" : "DEFLATE" });
  }
  return zip.generateAsync({ type: "uint8array" });
}

function contentTypes(macros: boolean): string {
  const macro = macros
    ? `<Override PartName="/xl/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/>`
    : "";
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  ${macro}
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`;
}

function rootRels(): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;
}

function workbookXml(names: string[]): string {
  const sheets = names
    .map(
      (name, index) =>
        `<sheet name="${escapeXml(name)}" sheetId="${index + 1}" r:id="rId${index + 1}"/>`,
    )
    .join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>${sheets}</sheets>
</workbook>`;
}

function workbookRels(count: number): string {
  const sheets = Array.from({ length: count }, (_, index) => {
    return `<Relationship Id="rId${index + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${index + 1}.xml"/>`;
  }).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheets}</Relationships>`;
}

function sharedStrings(values: string[]): string {
  const items = values.map((value) => `<si><t>${escapeXml(value)}</t></si>`).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="${values.length}" uniqueCount="${values.length}">${items}</sst>`;
}

function sheetXml(dimension: string, rows: string): string {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="${dimension}"/>
  <sheetData>${rows}</sheetData>
</worksheet>`;
}
