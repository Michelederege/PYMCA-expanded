import { predictConcentration, primaryLineKey } from "@/lib/xrf/curve";
import { fitSpectrum, significantPeaks } from "@/lib/xrf/fit";
import type { CalibrationCurve, FitConfig, FitResult, Spectrum, SpectrumRole } from "@/lib/xrf/types";

/** Fit every scan with the same configuration. This is the batch step. */
export function fitSpectra(spectra: Spectrum[], config: FitConfig): Record<string, FitResult> {
  return Object.fromEntries(spectra.map((spectrum) => [spectrum.id, fitSpectrum(spectrum, config)]));
}

/** Identity of a run, so the table can tell when the settings have moved on. */
export function fitStamp(config: FitConfig, ids: string[]): string {
  return JSON.stringify({
    ids: [...ids].sort(),
    zero: config.calibration.zero,
    gain: config.calibration.gain,
    emin: config.emin,
    emax: config.emax,
    fwhmAtMnEv: config.fwhmAtMnEv,
    snipIterations: config.snipIterations,
    lineKeys: [...config.lineKeys].sort(),
    excitationKeV: config.excitationKeV,
    includeEscape: config.includeEscape,
  });
}

export type BatchCell = {
  lineKey: string;
  energy: number;
  area: number;
  concentration: number | null;
};

export type BatchRow = {
  id: string;
  name: string;
  role: SpectrumRole;
  reducedChi2: number;
  warnings: string[];
  cells: Record<string, BatchCell>;
};

export type BatchTable = {
  elements: string[];
  rows: BatchRow[];
};

/** One row per fitted scan. Each cell is that scan's primary line for the element. */
export function buildBatchTable(
  spectra: Spectrum[],
  fits: Record<string, FitResult>,
  curves: CalibrationCurve[],
): BatchTable {
  const rows: BatchRow[] = [];
  const present = new Set<string>();

  for (const spectrum of spectra) {
    const fit = fits[spectrum.id];
    if (!fit) continue;
    const visible = new Set(significantPeaks(fit.peaks).map((peak) => peak.key));
    const cells: Record<string, BatchCell> = {};
    for (const element of new Set(fit.peaks.map((peak) => peak.element))) {
      const key = primaryLineKey(fit, element);
      if (!key || !visible.has(key)) continue;
      const peak = fit.peaks.find((item) => item.key === key);
      if (!peak || peak.area <= 0) continue;
      const curve = curves.find((item) => item.element === element);
      cells[element] = {
        lineKey: key,
        energy: peak.energy,
        area: peak.area,
        concentration: curve ? predictConcentration(curve, peak.area) : null,
      };
      present.add(element);
    }
    rows.push({
      id: spectrum.id,
      name: spectrum.name,
      role: spectrum.role,
      reducedChi2: fit.reducedChi2,
      warnings: fit.warnings,
      cells,
    });
  }

  const elements = [...present].sort((a, b) => {
    const energyA = rows.find((row) => row.cells[a])?.cells[a].energy ?? 0;
    const energyB = rows.find((row) => row.cells[b])?.cells[b].energy ?? 0;
    return energyA - energyB || a.localeCompare(b);
  });
  return { elements, rows };
}
