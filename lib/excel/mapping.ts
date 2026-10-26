export type Layout = "long" | "wide";

export type Binding = {
  header: string;
  column: number;
  field: string;
};

export type MappingProfile = {
  version: 1;
  sheet: string;
  headerRow: number;
  firstDataRow: number;
  layout: Layout;
  clearExtras: boolean;
  bindings: Binding[];
};

export const LONG_FIELDS: { id: string; label: string }[] = [
  { id: "ignore", label: "Don't write" },
  { id: "sample", label: "Sample" },
  { id: "element", label: "Element" },
  { id: "line", label: "Line" },
  { id: "energy_keV", label: "Energy (keV)" },
  { id: "area", label: "Peak area" },
  { id: "fwhm_eV", label: "FWHM (eV)" },
  { id: "cps", label: "Counts per second" },
  { id: "concentration", label: "Concentration" },
  { id: "chi2", label: "Chi-square" },
  { id: "reduced_chi2", label: "Reduced chi-square" },
  { id: "r2", label: "Calibration R²" },
  { id: "slope", label: "Calibration slope" },
  { id: "intercept", label: "Calibration intercept" },
  { id: "live_time_s", label: "Live time (s)" },
];

const ALIASES: Record<string, string[]> = {
  sample: ["sample", "sample id", "sample name", "spectrum", "specimen", "name", "id"],
  element: ["element", "elem", "symbol"],
  line: ["line", "series", "transition", "peak"],
  energy_keV: ["energy", "energy kev", "energy (kev)", "kev", "centroid", "position"],
  area: ["area", "peak area", "net area", "intensity", "net intensity", "counts", "net counts", "net"],
  fwhm_eV: ["fwhm", "fwhm ev", "fwhm (ev)", "width"],
  cps: ["cps", "counts per second", "rate"],
  concentration: ["concentration", "conc", "ppm", "ppb", "wt", "wt%", "mg/kg", "ug/g", "result"],
  chi2: ["chi2", "chi square", "chi-square", "chisq", "chi squared"],
  reduced_chi2: ["reduced chi2", "reduced chi square", "chi2 ndf", "chi2/ndf"],
  r2: ["r2", "r 2", "rsquared", "r squared"],
  slope: ["slope", "calibration slope"],
  intercept: ["intercept", "calibration intercept"],
  live_time_s: ["live time", "livetime", "live time s", "seconds", "acquisition time"],
};

export function normalizeHeader(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/²/g, "2")
    .replace(/μ/g, "u")
    .replace(/[^a-z0-9%]+/g, " ")
    .trim();
}

export function headersFromRow(row: string[] | undefined): { header: string; column: number }[] {
  if (!row) return [];
  const found: { header: string; column: number }[] = [];
  row.forEach((value, column) => {
    const header = value.trim();
    if (header) found.push({ header, column });
  });
  return found;
}

export function guessHeaderRow(rows: string[][]): number {
  let bestRow = 1;
  let bestScore = -1;
  rows.forEach((row, index) => {
    const headers = headersFromRow(row);
    if (headers.length < 2) return;
    const recognized = headers.filter((header) => matchLongField(header.header) !== "ignore").length;
    const score = recognized * 10 + headers.length;
    if (score > bestScore) {
      bestScore = score;
      bestRow = index + 1;
    }
  });
  return bestRow;
}

export function matchLongField(header: string): string {
  const key = normalizeHeader(header);
  for (const [field, aliases] of Object.entries(ALIASES)) {
    if (aliases.some((alias) => alias === key)) return field;
  }
  return "ignore";
}

export function matchWideField(header: string, lineKeys: string[]): string {
  const long = matchLongField(header);
  if (["sample", "chi2", "reduced_chi2", "live_time_s"].includes(long)) return long;
  const text = header.trim();
  const norms = lineKeys.map((key) => ({ key, norm: normalizeHeader(key), element: key.split(" ")[0] ?? key }));

  const areaHit = text.match(/^(.*?)(?:\s+peak)?\s+area$/i);
  if (areaHit) {
    const key = resolveLine(areaHit[1], norms);
    if (key) return `area:${key}`;
  }
  const fwhmHit = text.match(/^(.*?)\s+fwhm(?:\s*\(ev\))?$/i);
  if (fwhmHit) {
    const key = resolveLine(fwhmHit[1], norms);
    if (key) return `fwhm:${key}`;
  }
  const concHit = text.match(/^(.*?)\s+(?:concentration|conc|ppm|ppb|wt%|mg\/kg)$/i);
  if (concHit) {
    const element = resolveElement(concHit[1], norms);
    if (element) return `concentration:${element}`;
  }
  const r2Hit = text.match(/^(.*?)\s+r\s*[²2]$/i);
  if (r2Hit) {
    const element = resolveElement(r2Hit[1], norms);
    if (element) return `r2:${element}`;
  }

  const exact = norms.find((item) => item.norm === normalizeHeader(text));
  if (exact) return `area:${exact.key}`;
  const elementOnly = norms.find((item) => normalizeHeader(item.element) === normalizeHeader(text));
  if (elementOnly) return `concentration:${elementOnly.element}`;
  if (long !== "ignore") return long;
  return "ignore";
}

export function autoBindings(
  row: string[] | undefined,
  layout: Layout,
  lineKeys: string[],
): Binding[] {
  return headersFromRow(row).map((header) => ({
    header: header.header,
    column: header.column,
    field: layout === "wide" ? matchWideField(header.header, lineKeys) : matchLongField(header.header),
  }));
}

export function reconcileBindings(
  previous: Binding[],
  row: string[] | undefined,
  layout: Layout,
  lineKeys: string[],
): { bindings: Binding[]; notes: string[] } {
  const headers = headersFromRow(row);
  const notes: string[] = [];
  const bindings = headers.map((header) => {
    const prior = previous.find((binding) => normalizeHeader(binding.header) === normalizeHeader(header.header));
    if (prior) {
      return { header: header.header, column: header.column, field: prior.field };
    }
    const guessed = layout === "wide" ? matchWideField(header.header, lineKeys) : matchLongField(header.header);
    notes.push(`New column “${header.header}” was matched to ${fieldLabel(guessed, lineKeys)}.`);
    return { header: header.header, column: header.column, field: guessed };
  });
  for (const binding of previous) {
    if (!headers.some((header) => normalizeHeader(header.header) === normalizeHeader(binding.header))) {
      notes.push(`Column “${binding.header}” is no longer on this header row.`);
    }
  }
  return { bindings, notes };
}

export function fieldLabel(field: string, lineKeys: string[] = []): string {
  if (field.startsWith("area:")) return `${field.slice(5)} area`;
  if (field.startsWith("fwhm:")) return `${field.slice(5)} FWHM`;
  if (field.startsWith("concentration:")) return `${field.slice("concentration:".length)} concentration`;
  if (field.startsWith("r2:")) return `${field.slice(3)} R²`;
  if (field.startsWith("slope:")) return `${field.slice(6)} slope`;
  if (field.startsWith("intercept:")) return `${field.slice(10)} intercept`;
  if (field.startsWith("cps:")) return `${field.slice(4)} cps`;
  if (field.startsWith("energy:")) return `${field.slice(7)} energy`;
  const known = LONG_FIELDS.find((item) => item.id === field);
  if (known) return known.label;
  if (lineKeys.length === 0) return field;
  return field;
}

export function fieldOptions(layout: Layout, lineKeys: string[]): { id: string; label: string }[] {
  if (layout === "long") return LONG_FIELDS;
  const elements = [...new Set(lineKeys.map((key) => key.split(" ")[0]).filter(Boolean))];
  const dynamic: { id: string; label: string }[] = [];
  for (const key of lineKeys) {
    dynamic.push({ id: `area:${key}`, label: `${key} area` });
    dynamic.push({ id: `fwhm:${key}`, label: `${key} FWHM` });
    dynamic.push({ id: `cps:${key}`, label: `${key} cps` });
    dynamic.push({ id: `energy:${key}`, label: `${key} energy` });
  }
  for (const element of elements) {
    dynamic.push({ id: `concentration:${element}`, label: `${element} concentration` });
    dynamic.push({ id: `r2:${element}`, label: `${element} R²` });
    dynamic.push({ id: `slope:${element}`, label: `${element} slope` });
    dynamic.push({ id: `intercept:${element}`, label: `${element} intercept` });
  }
  return [
    { id: "ignore", label: "Don't write" },
    { id: "sample", label: "Sample" },
    { id: "chi2", label: "Chi-square" },
    { id: "reduced_chi2", label: "Reduced chi-square" },
    { id: "live_time_s", label: "Live time (s)" },
    ...dynamic,
  ];
}

function resolveLine(
  token: string,
  lines: { key: string; norm: string; element: string }[],
): string | null {
  const norm = normalizeHeader(token);
  return (
    lines.find((line) => line.norm === norm)?.key ??
    lines.find((line) => normalizeHeader(line.element) === norm && line.key.endsWith(" Ka"))?.key ??
    lines.find((line) => normalizeHeader(line.element) === norm)?.key ??
    null
  );
}

function resolveElement(token: string, lines: { key: string; norm: string; element: string }[]): string | null {
  const line = resolveLine(token, lines);
  if (line) return line.split(" ")[0] ?? null;
  const norm = normalizeHeader(token);
  return lines.find((item) => normalizeHeader(item.element) === norm)?.element ?? null;
}
