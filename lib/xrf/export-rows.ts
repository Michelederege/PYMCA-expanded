import { predictConcentration, primaryLineKey } from "@/lib/xrf/curve";
import type { Layout } from "@/lib/excel/mapping";
import type { CalibrationCurve, FitResult, Spectrum } from "@/lib/xrf/types";

export type ExportRecord = Record<string, string | number | null>;

export function buildExportRecords(
  spectra: Spectrum[],
  fits: Record<string, FitResult>,
  curves: CalibrationCurve[],
  layout: Layout,
): ExportRecord[] {
  if (layout === "wide") return spectra.flatMap((spectrum) => wideRecord(spectrum, fits[spectrum.id], curves));
  return spectra.flatMap((spectrum) => longRecords(spectrum, fits[spectrum.id], curves));
}

function longRecords(spectrum: Spectrum, fit: FitResult | undefined, curves: CalibrationCurve[]): ExportRecord[] {
  if (!fit) return [];
  return fit.peaks.map((peak) => {
    const curve = curves.find((item) => item.element === peak.element);
    const primary = primaryLineKey(fit, peak.element);
    const isPrimary = peak.key === primary;
    const concentration = isPrimary && curve ? predictConcentration(curve, peak.area) : null;
    return {
      sample: spectrum.name,
      element: peak.element,
      line: peak.series,
      energy_keV: round(peak.energy, 4),
      area: round(peak.area, 2),
      fwhm_eV: round(peak.fwhmEv, 1),
      cps: peak.cps === null ? null : round(peak.cps, 3),
      concentration: concentration === null ? null : round(concentration, 4),
      chi2: round(fit.chi2, 3),
      reduced_chi2: round(fit.reducedChi2, 4),
      r2: isPrimary && curve?.r2 !== null && curve?.r2 !== undefined ? round(curve.r2, 4) : null,
      slope: isPrimary && curve ? round(curve.slope, 6) : null,
      intercept: isPrimary && curve ? round(curve.intercept, 4) : null,
      live_time_s: spectrum.liveTimeS || null,
    };
  });
}

function wideRecord(
  spectrum: Spectrum,
  fit: FitResult | undefined,
  curves: CalibrationCurve[],
): ExportRecord[] {
  if (!fit) return [];
  const record: ExportRecord = {
    sample: spectrum.name,
    chi2: round(fit.chi2, 3),
    reduced_chi2: round(fit.reducedChi2, 4),
    live_time_s: spectrum.liveTimeS || null,
  };
  for (const peak of fit.peaks) {
    record[`area:${peak.key}`] = round(peak.area, 2);
    record[`fwhm:${peak.key}`] = round(peak.fwhmEv, 1);
    record[`energy:${peak.key}`] = round(peak.energy, 4);
    record[`cps:${peak.key}`] = peak.cps === null ? null : round(peak.cps, 3);
  }
  const elements = new Set(fit.peaks.map((peak) => peak.element));
  for (const element of elements) {
    const curve = curves.find((item) => item.element === element);
    const primary = fit.peaks.find((peak) => peak.key === primaryLineKey(fit, element));
    if (!primary) continue;
    record[`concentration:${element}`] = curve
      ? round(predictConcentration(curve, primary.area) ?? NaN, 4)
      : null;
    record[`r2:${element}`] = curve?.r2 === null || curve?.r2 === undefined ? null : round(curve.r2, 4);
    record[`slope:${element}`] = curve ? round(curve.slope, 6) : null;
    record[`intercept:${element}`] = curve ? round(curve.intercept, 4) : null;
  }
  return [record];
}

function round(value: number, digits: number): number | null {
  if (!Number.isFinite(value)) return null;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}
