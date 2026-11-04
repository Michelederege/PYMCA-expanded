import type { Calibration, Spectrum } from "@/lib/xrf/types";

export function parseSpectrumText(text: string, name: string, id: string): Spectrum {
  const counts: number[] = [];
  const energies: number[] = [];
  let sawEnergy = false;
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith("//")) continue;
    const parts = trimmed.split(/[,;\t ]+/).filter(Boolean);
    const numbers = parts.map((part) => Number(part.replace(",", ".")));
    if (numbers.some((value) => !Number.isFinite(value))) continue;
    if (numbers.length === 1) {
      counts.push(numbers[0]);
    } else if (numbers.length >= 2) {
      energies.push(numbers[0]);
      counts.push(numbers[1]);
      sawEnergy = true;
    }
  }
  if (counts.length < 8) {
    throw new Error(`${name} needs at least 8 numeric channels. Use one counts column, or energy and counts.`);
  }
  const spectrum: Spectrum = {
    id,
    name: name.replace(/\.(csv|txt|mca)$/i, ""),
    counts: Float64Array.from(counts),
    liveTimeS: 60,
    role: "unknown",
    known: {},
  };
  if (sawEnergy && energies.length === counts.length && looksLikeEnergy(energies)) {
    spectrum.energy = Float64Array.from(energies);
  }
  return spectrum;
}

export function calibrationFromSpectrum(spectrum: Spectrum, fallback: Calibration): Calibration {
  if (!spectrum.energy || spectrum.energy.length < 2) return fallback;
  const n = spectrum.energy.length;
  let sx = 0;
  let sy = 0;
  let sxx = 0;
  let sxy = 0;
  for (let i = 0; i < n; i++) {
    sx += i;
    sy += spectrum.energy[i];
    sxx += i * i;
    sxy += i * spectrum.energy[i];
  }
  const denom = n * sxx - sx * sx;
  if (Math.abs(denom) < 1e-9) return fallback;
  const gain = (n * sxy - sx * sy) / denom;
  const zero = (sy - gain * sx) / n;
  if (!Number.isFinite(gain) || Math.abs(gain) < 1e-9) return fallback;
  return { zero, gain };
}

function looksLikeEnergy(values: number[]): boolean {
  if (values[values.length - 1] > 200) return false;
  let increasing = 0;
  for (let i = 1; i < values.length; i++) if (values[i] >= values[i - 1]) increasing++;
  return increasing / (values.length - 1) > 0.9 && values[values.length - 1] > values[0];
}

const SCAN_HEADER = /^#\s*(?:scan|spectrum)\b[:\s]\s*(.*)$/i;
const SPEC_SCAN = /^#S\s+\d+\s*(.*)$/;

/**
 * One file can hold several scans. A `# scan:` or SPEC `#S` line starts a scan.
 * A header row with two or more sample columns is a scan per column, with an
 * optional energy or channel column. Anything else stays a single spectrum.
 */
export function parseSpectraText(text: string, fallbackName: string, idFactory: () => string): Spectrum[] {
  const marked = splitMarkedScans(text);
  if (marked) {
    return marked.map((block, index) => {
      const label = block.name || fallbackScanName(fallbackName, index, marked.length);
      const spectrum = parseSpectrumText(block.body, label, idFactory());
      return applyBlockMeta(spectrum, block, label);
    });
  }
  const columns = parseColumnarSpectra(text, fallbackName, idFactory);
  if (columns && columns.length > 1) return columns;
  return [parseSpectrumText(text, fallbackName, idFactory())];
}

type ScanBlock = {
  name: string;
  body: string;
  liveTimeS?: number;
  role?: Spectrum["role"];
  known: Record<string, number>;
};

function splitMarkedScans(text: string): ScanBlock[] | null {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  const headers = lines
    .map((line, index) => ({ line: line.trim(), index }))
    .filter(({ line }) => SCAN_HEADER.test(line) || SPEC_SCAN.test(line));
  if (headers.length === 0) return null;

  return headers.map((header, index) => {
    const end = index + 1 < headers.length ? headers[index + 1].index : lines.length;
    const match = SCAN_HEADER.exec(header.line) ?? SPEC_SCAN.exec(header.line);
    const name = (match?.[1] ?? "").trim();
    const known: Record<string, number> = {};
    let liveTimeS: number | undefined;
    let role: Spectrum["role"] | undefined;
    const data: string[] = [];
    for (const raw of lines.slice(header.index + 1, end)) {
      const line = raw.trim();
      const time = /^#\s*(?:live[_\s-]?time|realtime)\b[:\s]\s*([0-9]*\.?[0-9]+)/i.exec(line);
      const roleMatch = /^#\s*role\b[:\s]\s*(standard|unknown)\b/i.exec(line);
      const knownMatch = /^#\s*(?:known|concentration)\b[:\s]\s*([A-Za-z]{1,2})\s+([0-9]*\.?[0-9]+)/i.exec(line);
      if (time) liveTimeS = Number(time[1]);
      else if (roleMatch) role = roleMatch[1].toLowerCase() as Spectrum["role"];
      else if (knownMatch) known[elementSymbol(knownMatch[1])] = Number(knownMatch[2]);
      else data.push(raw);
    }
    return { name, body: data.join("\n"), liveTimeS, role, known };
  });
}

function parseColumnarSpectra(text: string, fallbackName: string, idFactory: () => string): Spectrum[] | null {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  const first = lines.find((line) => {
    const trimmed = line.trim();
    return trimmed && !trimmed.startsWith("#") && !trimmed.startsWith("//");
  });
  if (!first) return null;
  const delimiter = delimiterOf(first);
  const rows: string[][] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith("//")) continue;
    rows.push(trimmed.split(delimiter).map((cell) => cell.trim()).filter((cell) => cell.length > 0));
  }
  if (rows.length < 9) return null;
  const header = rows[0];
  if (header.length < 2 || header.every((cell) => isNumeric(cell))) return null;
  const width = header.length;
  const aligned = rows.slice(1).filter((row) => row.length >= width && row.slice(0, width).every(isNumeric));
  if (aligned.length < 8) return null;

  const columns = Array.from({ length: width }, () => [] as number[]);
  for (const row of aligned) {
    for (let column = 0; column < width; column++) columns[column].push(Number(row[column].replace(",", ".")));
  }

  const axis = columnIsAxis(header[0], columns[0]);
  const sampleStart = axis ? 1 : 0;
  if (width - sampleStart < 2) return null;
  const shareEnergy = axis && looksLikeEnergy(columns[0]);

  return columns.slice(sampleStart).map((counts, index) => {
    const sampleCount = width - sampleStart;
    const spectrum: Spectrum = {
      id: idFactory(),
      name: header[sampleStart + index] || fallbackScanName(fallbackName, index, sampleCount),
      counts: Float64Array.from(counts),
      liveTimeS: 60,
      role: "unknown",
      known: {},
    };
    if (shareEnergy) spectrum.energy = Float64Array.from(columns[0]);
    return spectrum;
  });
}

function applyBlockMeta(spectrum: Spectrum, block: ScanBlock, label: string): Spectrum {
  return {
    ...spectrum,
    name: label,
    liveTimeS: block.liveTimeS ?? spectrum.liveTimeS,
    role: block.role ?? spectrum.role,
    known: Object.keys(block.known).length > 0 ? block.known : spectrum.known,
  };
}

function fallbackScanName(fileName: string, index: number, count: number): string {
  const base = fileName.replace(/\.(csv|txt|mca|spec)$/i, "");
  return count > 1 ? `${base} ${index + 1}` : base;
}

function elementSymbol(raw: string): string {
  return raw[0].toUpperCase() + raw.slice(1).toLowerCase();
}

function delimiterOf(line: string): RegExp {
  if (line.includes("\t")) return /\t/;
  if (line.includes(";")) return /;/;
  if (line.includes(",")) return /,/;
  return /\s+/;
}

function isNumeric(token: string): boolean {
  return Number.isFinite(Number(token.replace(",", ".")));
}

function columnIsAxis(header: string, values: number[]): boolean {
  const label = header.toLowerCase().replace(/[_./-]+/g, " ");
  if (/\b(energy|kev|channel|channels)\b/.test(label)) return true;
  return looksLikeChannelIndex(values);
}

function looksLikeChannelIndex(values: number[]): boolean {
  let matches = 0;
  for (let i = 0; i < values.length; i++) {
    if (values[i] === i || values[i] === i + 1) matches++;
  }
  return matches / values.length > 0.95;
}

export function spectrumToCsv(spectrum: Spectrum, calibration: Calibration): string {
  const rows = ["channel,energy_keV,counts"];
  for (let i = 0; i < spectrum.counts.length; i++) {
    const energy = spectrum.energy ? spectrum.energy[i] : calibration.zero + calibration.gain * i;
    rows.push(`${i},${energy},${spectrum.counts[i]}`);
  }
  return rows.join("\n");
}
