import type { CalibrationCurve, FitResult, Spectrum } from "@/lib/xrf/types";

export function primaryLineKey(fit: FitResult, element: string): string | null {
  const peaks = fit.peaks.filter((peak) => peak.element === element && peak.area > 0);
  if (peaks.length === 0) {
    const any = fit.peaks.find((peak) => peak.element === element);
    return any?.key ?? null;
  }
  const preferred = peaks.find((peak) => peak.series === "Ka" || peak.series === "La");
  if (preferred) return preferred.key;
  return peaks.reduce((best, peak) => (peak.area > best.area ? peak : best)).key;
}

export function areaForElement(fit: FitResult, element: string): { key: string; area: number } | null {
  const key = primaryLineKey(fit, element);
  if (!key) return null;
  const peak = fit.peaks.find((item) => item.key === key);
  if (!peak) return null;
  return { key, area: peak.area };
}

export function fitCurves(
  spectra: Spectrum[],
  fits: Record<string, FitResult>,
): CalibrationCurve[] {
  const elements = new Set<string>();
  for (const spectrum of spectra) {
    if (spectrum.role !== "standard") continue;
    for (const element of Object.keys(spectrum.known)) elements.add(element);
  }

  const curves: CalibrationCurve[] = [];
  for (const element of elements) {
    const points: CalibrationCurve["points"] = [];
    let lineKey = "";
    for (const spectrum of spectra) {
      if (spectrum.role !== "standard") continue;
      const known = spectrum.known[element];
      if (known === undefined || !Number.isFinite(known)) continue;
      const fit = fits[spectrum.id];
      if (!fit) continue;
      const area = areaForElement(fit, element);
      if (!area || area.area <= 0) continue;
      lineKey = area.key;
      points.push({ sample: spectrum.name, area: area.area, concentration: known });
    }
    if (!lineKey || points.length === 0) continue;
    const regression = regress(points.map((point) => point.area), points.map((point) => point.concentration));
    curves.push({
      element,
      lineKey,
      slope: regression.slope,
      intercept: regression.intercept,
      r2: regression.r2,
      points,
    });
  }
  curves.sort((a, b) => a.element.localeCompare(b.element));
  return curves;
}

export function predictConcentration(curve: CalibrationCurve | undefined, area: number): number | null {
  if (!curve || !Number.isFinite(area)) return null;
  return curve.intercept + curve.slope * area;
}

function regress(x: number[], y: number[]): { slope: number; intercept: number; r2: number | null } {
  if (x.length === 1) {
    const slope = x[0] !== 0 ? y[0] / x[0] : 0;
    return { slope, intercept: 0, r2: null };
  }
  const n = x.length;
  let sx = 0;
  let sy = 0;
  let sxx = 0;
  let sxy = 0;
  for (let i = 0; i < n; i++) {
    sx += x[i];
    sy += y[i];
    sxx += x[i] * x[i];
    sxy += x[i] * y[i];
  }
  const denom = n * sxx - sx * sx;
  const slope = Math.abs(denom) < 1e-12 ? 0 : (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  let ssTot = 0;
  let ssRes = 0;
  const mean = sy / n;
  for (let i = 0; i < n; i++) {
    const pred = intercept + slope * x[i];
    ssRes += (y[i] - pred) ** 2;
    ssTot += (y[i] - mean) ** 2;
  }
  const r2 = ssTot <= 1e-12 ? 1 : 1 - ssRes / ssTot;
  return { slope, intercept, r2 };
}
