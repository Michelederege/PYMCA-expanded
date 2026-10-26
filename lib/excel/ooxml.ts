export type SheetPreview = {
  name: string;
  path: string;
  /** Row-major grid, 0-based, trimmed to the preview window. */
  rows: string[][];
};

export type WorkbookPreview = {
  sheets: SheetPreview[];
  hasMacros: boolean;
  bytes: number;
};

export type CellWrite = {
  column: number;
  value: string | number | null;
};

export type FillRequest = {
  sheet: string;
  headerRow: number;
  firstDataRow: number;
  bindings: { header: string; column: number; field: string }[];
  records: Record<string, string | number | null>[];
  clearExtras: boolean;
};

export type FillResult = {
  bytes: Uint8Array;
  warnings: string[];
  rowsWritten: number;
  cellsSkipped: number;
  cellsCleared: number;
};

export function colToIndex(col: string): number {
  let n = 0;
  for (const char of col.toUpperCase()) {
    if (char < "A" || char > "Z") break;
    n = n * 26 + (char.charCodeAt(0) - 64);
  }
  return n - 1;
}

export function indexToCol(index: number): string {
  let n = index + 1;
  let out = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    out = String.fromCharCode(65 + rem) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

export function decodeXml(value: string): string {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

export function escapeXml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export async function inspectWorkbook(
  data: ArrayBuffer | Uint8Array,
  maxRow = 30,
  maxCol = 20,
): Promise<WorkbookPreview> {
  const JSZip = (await import("jszip")).default;
  const zip = await JSZip.loadAsync(data);
  const workbookXml = await readText(zip, "xl/workbook.xml");
  const relsXml = await readText(zip, "xl/_rels/workbook.xml.rels");
  if (!workbookXml || !relsXml) throw new Error("This file is missing the workbook index.");
  const shared = parseSharedStrings((await readText(zip, "xl/sharedStrings.xml")) ?? "");
  const sheets = sheetIndex(workbookXml, relsXml);
  const previews: SheetPreview[] = [];
  for (const sheet of sheets) {
    const xml = await readText(zip, sheet.path);
    previews.push({
      name: sheet.name,
      path: sheet.path,
      rows: xml ? gridFromSheet(xml, shared, maxRow, maxCol) : [],
    });
  }
  return {
    sheets: previews,
    hasMacros: Boolean(zip.file("xl/vbaProject.bin")),
    bytes: data.byteLength,
  };
}

export async function fillWorkbook(data: ArrayBuffer | Uint8Array, request: FillRequest): Promise<FillResult> {
  const JSZip = (await import("jszip")).default;
  const zip = await JSZip.loadAsync(data);
  const workbookXml = await readText(zip, "xl/workbook.xml");
  const relsXml = await readText(zip, "xl/_rels/workbook.xml.rels");
  if (!workbookXml || !relsXml) throw new Error("This file is missing the workbook index.");
  const sheets = sheetIndex(workbookXml, relsXml);
  const sheet = sheets.find((item) => item.name === request.sheet);
  if (!sheet) throw new Error(`Sheet “${request.sheet}” is not in this workbook.`);
  const xml = await readText(zip, sheet.path);
  if (!xml) throw new Error(`Could not read ${sheet.name}.`);
  const shared = parseSharedStrings((await readText(zip, "xl/sharedStrings.xml")) ?? "");
  const edited = writeRecords(xml, shared, request);
  const bytes = await repack(zip, { [sheet.path]: edited.xml });
  return {
    bytes,
    warnings: edited.warnings,
    rowsWritten: edited.rowsWritten,
    cellsSkipped: edited.cellsSkipped,
    cellsCleared: edited.cellsCleared,
  };
}

export function parseSharedStrings(xml: string): string[] {
  if (!xml) return [];
  const out: string[] = [];
  const pattern = /<(?:\w+:)?si\b[^>]*>([\s\S]*?)<\/(?:\w+:)?si>/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(xml))) {
    const body = match[1];
    const texts = [...body.matchAll(/<(?:\w+:)?t\b[^>]*>([\s\S]*?)<\/(?:\w+:)?t>/g)].map((item) =>
      decodeXml(item[1]),
    );
    out.push(texts.join(""));
  }
  return out;
}

export function gridFromSheet(xml: string, shared: string[], maxRow: number, maxCol: number): string[][] {
  const grid: string[][] = [];
  for (const row of iterateRows(xml, maxRow)) {
    while (grid.length < row.number) grid.push([]);
    const values = Array.from({ length: maxCol }, () => "");
    for (const cell of parseCells(row.xml)) {
      if (cell.column >= maxCol) continue;
      values[cell.column] = cellText(cell.attrs, cell.inner, shared);
    }
    grid[row.number - 1] = values;
  }
  return grid;
}

function writeRecords(
  xml: string,
  shared: string[],
  request: FillRequest,
): { xml: string; warnings: string[]; rowsWritten: number; cellsSkipped: number; cellsCleared: number } {
  const warnings: string[] = [];
  const bindings = request.bindings.filter((binding) => binding.field && binding.field !== "ignore");
  if (bindings.length === 0) {
    throw new Error("Map at least one column before writing.");
  }
  if (request.firstDataRow <= request.headerRow) {
    throw new Error("The first data row has to sit below the header row.");
  }

  const prefix = detectPrefix(xml);
  let working = normalizeSheetData(xml, prefix);
  const lastNeeded =
    request.firstDataRow +
    Math.max(request.records.length, 1) +
    (request.clearExtras ? 400 : 2);
  let cellsSkipped = 0;
  let cellsCleared = 0;
  const spans: { start: number; end: number; text: string }[] = [];

  const header = rowXml(working, request.headerRow);
  const headerCells = header ? parseCells(header.xml) : [];
  const formulaCols = new Set<number>();
  for (const binding of bindings) {
    const headerCell = headerCells.find((cell) => cell.column === binding.column);
    if (headerCell?.formula) {
      warnings.push(`Column ${indexToCol(binding.column)} header contains a formula and was left unchanged.`);
    }
  }

  const writeRow = (rowNumber: number, updates: Map<number, string | number | null>, clearing: boolean) => {
    const located = rowXml(working, rowNumber);
    if (!located && clearing) return;
    const current = located?.xml ?? `<${prefix}row r="${rowNumber}"/>`;
    const result = upsertRow(current, rowNumber, prefix, updates, shared);
    cellsSkipped += result.skipped;
    if (clearing) cellsCleared += result.changed;
    warnings.push(...result.warnings);
    if (located) {
      spans.push({ start: located.start, end: located.end, text: result.xml });
    } else {
      const at = insertionPoint(working, rowNumber, prefix);
      spans.push({ start: at, end: at, text: result.xml });
    }
  };

  request.records.forEach((record, index) => {
    const rowNumber = request.firstDataRow + index;
    const updates = new Map<number, string | number | null>();
    for (const binding of bindings) {
      updates.set(binding.column, record[binding.field] ?? null);
    }
    writeRow(rowNumber, updates, false);
  });

  if (request.clearExtras) {
    const start = request.firstDataRow + request.records.length;
    const indexed = indexRows(working, start, lastNeeded, prefix);
    let expected = start;
    for (const row of indexed) {
      if (row.number !== expected) break;
      expected += 1;
      const cells = parseCells(row.xml);
      const relevant = cells.filter((cell) => bindings.some((binding) => binding.column === cell.column));
      if (relevant.length === 0) break;
      const hasValue = relevant.some((cell) => !cell.formula && cellText(cell.attrs, cell.inner, shared).trim() !== "");
      const blocked = relevant.some((cell) => cell.formula);
      if (blocked) {
        for (const cell of relevant) if (cell.formula) formulaCols.add(cell.column);
        break;
      }
      if (!hasValue) break;
      const updates = new Map<number, string | number | null>();
      for (const binding of bindings) updates.set(binding.column, null);
      writeRow(row.number, updates, true);
    }
  }

  if (formulaCols.size) {
    warnings.push(
      `Stopped clearing at a formula in column ${[...formulaCols].map(indexToCol).join(", ")}. Formulas were not overwritten.`,
    );
  }

  working = applySpans(working, spans);
  const lastRow = request.firstDataRow + Math.max(0, request.records.length - 1);
  const lastCol = Math.max(...bindings.map((binding) => binding.column), 0);
  working = expandDimension(working, lastRow, lastCol);
  const uniqueWarnings = unique(warnings);
  const capped = uniqueWarnings.slice(0, 8);
  if (uniqueWarnings.length > capped.length) {
    capped.push(`${uniqueWarnings.length - capped.length} more cells were left unchanged.`);
  }
  return {
    xml: working,
    warnings: capped,
    rowsWritten: request.records.length,
    cellsSkipped,
    cellsCleared,
  };
}

function upsertRow(
  rowXmlText: string,
  rowNumber: number,
  prefix: string,
  updates: Map<number, string | number | null>,
  shared: string[],
): { xml: string; skipped: number; changed: number; warnings: string[] } {
  const warnings: string[] = [];
  let skipped = 0;
  let changed = 0;
  const selfClosing = /^<(?:\w+:)?row\b([^>]*)\/>\s*$/.test(rowXmlText);
  const open = selfClosing ? null : rowXmlText.match(/^<(?:\w+:)?row\b([^>]*)>/);
  const attrs = (selfClosing ? selfClosingAttrs(rowXmlText) : open?.[1]) ?? "";
  const inner = open ? rowXmlText.slice(open[0].length, rowXmlText.lastIndexOf("</")) : "";
  const direct = parseCellsFragment(inner);

  const byCol = new Map(direct.map((cell) => [cell.column, cell]));
  const pieces: { column: number; xml: string }[] = direct.map((cell) => ({
    column: cell.column,
    xml: cell.raw,
  }));

  for (const [column, value] of updates) {
    const existing = byCol.get(column);
    if (existing?.formula) {
      skipped++;
      warnings.push(
        `${indexToCol(column)}${rowNumber} already has a formula (${formulaPreview(existing.inner)}) and was left as-is.`,
      );
      continue;
    }
    const style = existing ? styleOf(existing.attrs) : null;
    const next = renderCell(indexToCol(column) + rowNumber, style, value);
    if (existing) {
      const pos = pieces.findIndex((piece) => piece.column === column);
      if (pos >= 0) pieces[pos] = { column, xml: next };
    } else {
      pieces.push({ column, xml: next });
    }
    if (existing) {
      const previous = cellText(existing.attrs, existing.inner, shared);
      const incoming = value === null || value === "" ? "" : String(value);
      if (previous !== incoming) changed++;
    } else if (value !== null && value !== "") {
      changed++;
    }
  }

  pieces.sort((a, b) => a.column - b.column);
  const rowAttrs = attrs.includes(`r="`) ? attrs : `${attrs} r="${rowNumber}"`;
  return {
    xml: `<${prefix}row${rowAttrs}>${pieces.map((piece) => piece.xml).join("")}</${prefix}row>`,
    skipped,
    changed,
    warnings,
  };
}

function parseCellsFragment(inner: string): ParsedCell[] {
  return parseCells(`<row>${inner}</row>`);
}

type ParsedCell = {
  column: number;
  attrs: string;
  inner: string;
  raw: string;
  formula: boolean;
};

function parseCells(rowXmlText: string): ParsedCell[] {
  const innerStart = rowXmlText.indexOf(">");
  const inner = innerStart >= 0 ? rowXmlText.slice(innerStart + 1).replace(/<\/(?:\w+:)?row>\s*$/, "") : rowXmlText;
  const cells: ParsedCell[] = [];
  const pattern = /<((?:\w+:)?c)\b([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:\w+:)?c>)/g;
  let match: RegExpExecArray | null;
  let fallback = 0;
  while ((match = pattern.exec(inner))) {
    const attrs = match[2] ?? "";
    const body = match[3] ?? "";
    const ref = /\br="([A-Z]+)(\d+)"/i.exec(attrs);
    const column = ref ? colToIndex(ref[1]) : fallback;
    fallback = column + 1;
    cells.push({
      column,
      attrs,
      inner: body,
      raw: match[0],
      formula: /<(?:\w+:)?f[\s/>]/.test(body),
    });
  }
  return cells;
}

function cellText(attrs: string, inner: string, shared: string[]): string {
  const type = /\bt="([^"]+)"/.exec(attrs)?.[1] ?? "";
  if (type === "inlineStr") {
    return [...inner.matchAll(/<(?:\w+:)?t\b[^>]*>([\s\S]*?)<\/(?:\w+:)?t>/g)]
      .map((item) => decodeXml(item[1]))
      .join("");
  }
  const value = /<(?:\w+:)?v\b[^>]*>([\s\S]*?)<\/(?:\w+:)?v>/.exec(inner);
  const raw = value ? decodeXml(value[1]) : "";
  if (type === "s") return shared[Number(raw)] ?? "";
  return raw;
}

function styleOf(attrs: string): string | null {
  return /\bs="(\d+)"/.exec(attrs)?.[1] ?? null;
}

function renderCell(ref: string, style: string | null, value: string | number | null): string {
  const styleAttr = style ? ` s="${style}"` : "";
  if (typeof value === "number" && Number.isFinite(value)) {
    return `<c r="${ref}"${styleAttr}><v>${trimNumber(value)}</v></c>`;
  }
  if (value === null || value === "") return `<c r="${ref}"${styleAttr}/>`;
  return `<c r="${ref}"${styleAttr} t="inlineStr"><is><t xml:space="preserve">${escapeXml(String(value))}</t></is></c>`;
}

function trimNumber(value: number): string {
  if (Number.isInteger(value)) return String(value);
  const rounded = Number(value.toPrecision(12));
  return String(rounded);
}

function formulaPreview(inner: string): string {
  const formula = /<(?:\w+:)?f\b[^>]*>([\s\S]*?)<\/(?:\w+:)?f>/.exec(inner);
  return formula ? decodeXml(formula[1]).slice(0, 80) : "formula";
}

function selfClosingAttrs(rowXmlText: string): string {
  const match = /^<(?:\w+:)?row\b([^>]*)\/>/.exec(rowXmlText);
  return (match?.[1] ?? "").replace(/\/\s*$/, "");
}

type LocatedRow = { number: number; start: number; end: number; xml: string };

function iterateRows(xml: string, maxRow: number): LocatedRow[] {
  return indexRows(xml, 1, maxRow, detectPrefix(xml));
}

function indexRows(xml: string, minRow: number, maxRow: number, prefix: string): LocatedRow[] {
  const rows: LocatedRow[] = [];
  const data = sheetDataInner(xml, prefix);
  if (!data) return rows;
  const pattern = new RegExp(`<${prefix}row\\b[^>]*\\br="(\\d+)"[^>]*(?:/>|>)`, "g");
  pattern.lastIndex = data.start;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(xml))) {
    if (match.index >= data.end) break;
    const number = Number(match[1]);
    const selfClosing = match[0].endsWith("/>");
    let end = match.index + match[0].length;
    if (!selfClosing) {
      const close = xml.indexOf(`</${prefix}row>`, end);
      if (close < 0) break;
      end = close + `</${prefix}row>`.length;
    }
    if (number >= minRow && number <= maxRow) {
      rows.push({ number, start: match.index, end, xml: xml.slice(match.index, end) });
    }
    if (number > maxRow) break;
    pattern.lastIndex = end;
  }
  return rows;
}

function rowXml(xml: string, rowNumber: number): LocatedRow | null {
  const found = indexRows(xml, rowNumber, rowNumber, detectPrefix(xml));
  return found.find((row) => row.number === rowNumber) ?? null;
}

function insertionPoint(xml: string, rowNumber: number, prefix: string): number {
  const data = sheetDataInner(xml, prefix);
  if (!data) return xml.length;
  const pattern = new RegExp(`<${prefix}row\\b[^>]*\\br="(\\d+)"`, "g");
  pattern.lastIndex = data.start;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(xml))) {
    if (match.index >= data.end) break;
    if (Number(match[1]) > rowNumber) return match.index;
  }
  return data.end;
}

function detectPrefix(xml: string): string {
  const match = xml.match(/<(\w+:)?sheetData\b/);
  return match?.[1] ?? "";
}

function sheetDataInner(xml: string, prefix: string): { start: number; end: number } | null {
  const open = xml.search(new RegExp(`<${prefix}sheetData\\b[^>]*>`));
  if (open < 0) return null;
  const openEnd = xml.indexOf(">", open);
  const token = xml.slice(open, openEnd + 1);
  if (token.endsWith("/>")) return { start: openEnd, end: openEnd };
  const close = xml.indexOf(`</${prefix}sheetData>`, openEnd);
  if (close < 0) return null;
  return { start: openEnd + 1, end: close };
}

function normalizeSheetData(xml: string, prefix: string): string {
  return xml.replace(new RegExp(`<${prefix}sheetData\\b([^>]*)/>`), `<${prefix}sheetData$1></${prefix}sheetData>`);
}

function expandDimension(xml: string, lastRow: number, lastCol: number): string {
  if (lastRow < 1) return xml;
  return xml.replace(/<((?:\w+:)?dimension)\b([^>]*)\/>/, (full, tag: string, attrs: string) => {
    const range = /ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"/i.exec(attrs);
    const single = /ref="([A-Z]+)(\d+)"/i.exec(attrs);
    let c1 = 0;
    let r1 = 1;
    let c2 = lastCol;
    let r2 = lastRow;
    if (range) {
      c1 = colToIndex(range[1]);
      r1 = Number(range[2]);
      c2 = Math.max(colToIndex(range[3]), lastCol);
      r2 = Math.max(Number(range[4]), lastRow);
    } else if (single) {
      c1 = colToIndex(single[1]);
      r1 = Number(single[2]);
      c2 = Math.max(c1, lastCol);
      r2 = Math.max(r1, lastRow);
    }
    const ref = `${indexToCol(c1)}${r1}:${indexToCol(c2)}${r2}`;
    return `<${tag} ref="${ref}"/>`;
  });
}

function applySpans(xml: string, spans: { start: number; end: number; text: string }[]): string {
  const sorted = [...spans].sort((a, b) => a.start - b.start || a.end - b.end);
  let cursor = 0;
  let out = "";
  for (const span of sorted) {
    if (span.start < cursor) {
      throw new Error("Workbook rows overlapped while writing. The sheet may use an unusual layout.");
    }
    out += xml.slice(cursor, span.start);
    out += span.text;
    cursor = span.end;
  }
  out += xml.slice(cursor);
  return out;
}

function sheetIndex(workbookXml: string, relsXml: string): { name: string; path: string }[] {
  const rels = new Map<string, string>();
  const relPattern = /<Relationship\b([^>]*)\/?>/g;
  let match: RegExpExecArray | null;
  while ((match = relPattern.exec(relsXml))) {
    const id = /\bId="([^"]+)"/.exec(match[1])?.[1];
    const target = /\bTarget="([^"]+)"/.exec(match[1])?.[1];
    if (id && target) rels.set(id, target);
  }

  const sheets: { name: string; path: string }[] = [];
  const sheetPattern = /<(?:\w+:)?sheet\b([^>]*)\/?>/g;
  while ((match = sheetPattern.exec(workbookXml))) {
    const name = /\bname="([^"]+)"/.exec(match[1])?.[1];
    const id = /\br:id="([^"]+)"/.exec(match[1])?.[1];
    if (!name || !id) continue;
    const target = rels.get(id);
    if (!target) continue;
    const cleaned = target.replace(/^\//, "").replace(/^\.\.\//, "");
    const path = cleaned.startsWith("xl/") ? cleaned : `xl/${cleaned}`;
    sheets.push({ name: decodeXml(name), path });
  }
  return sheets;
}

async function readText(zip: import("jszip"), path: string): Promise<string | null> {
  const file = zip.file(path);
  if (!file) return null;
  return file.async("string");
}

async function repack(zip: import("jszip"), replacements: Record<string, string>): Promise<Uint8Array> {
  for (const [path, xml] of Object.entries(replacements)) zip.file(path, xml);
  const names = Object.keys(zip.files);
  for (const name of names) {
    const entry = zip.file(name);
    if (!entry || zip.files[name].dir) continue;
    const bytes = await entry.async("uint8array");
    const store = /vbaProject\.bin$/i.test(name) || /\.bin$/i.test(name);
    zip.file(name, bytes, {
      compression: store ? "STORE" : "DEFLATE",
      compressionOptions: store ? undefined : { level: 6 },
    });
  }
  return zip.generateAsync({ type: "uint8array" });
}

export async function compressionMethod(data: Uint8Array, filename: string): Promise<number | null> {
  const encoded = new TextEncoder().encode(filename);
  for (let i = 0; i < data.length - 30 - encoded.length; i++) {
    if (data[i] !== 0x50 || data[i + 1] !== 0x4b || data[i + 2] !== 0x03 || data[i + 3] !== 0x04) continue;
    const nameLen = data[i + 26] | (data[i + 27] << 8);
    if (nameLen !== encoded.length) continue;
    let same = true;
    for (let j = 0; j < encoded.length; j++) {
      if (data[i + 30 + j] !== encoded[j]) {
        same = false;
        break;
      }
    }
    if (!same) continue;
    return data[i + 8] | (data[i + 9] << 8);
  }
  return null;
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}
