import { snipBackground } from "@/lib/xrf/background";
import { findLine, LINES, lineKey, type XrayLine } from "@/lib/xrf/lines";
import { nnls } from "@/lib/xrf/nnls";
import {
  addUnitGaussian,
  channelOf,
  energyOf,
  fwhmEv,
  sigmaChannels,
} from "@/lib/xrf/shape";
import type { Calibration, FitConfig, FitResult, PeakResult, Spectrum } from "@/lib/xrf/types";

const SI_ESCAPE_KEV = 1.73998;

export function fitSpectrum(spectrum: Spectrum, config: FitConfig): FitResult {
  const counts = spectrum.counts;
  const n = counts.length;
  const warnings: string[] = [];
  const { zero, gain } = config.calibration;
  if (!(Math.abs(gain) > 1e-9)) {
    throw new Error("Energy gain must not be zero.");
  }

  const [lo, hi] = region(n, config);
  const regionCounts = counts.subarray(lo, hi + 1);
  const fullBackground = new Float64Array(n);
  const snip = snipBackground(regionCounts, config.snipIterations);
  fullBackground.set(snip, lo);

  const selected = config.lineKeys
    .map((key) => findLine(key))
    .filter((line): line is XrayLine => Boolean(line))
    .filter((line) => line.edge < config.excitationKeV)
    .filter((line) => line.energy >= config.emin && line.energy <= config.emax);

  const skipped = config.lineKeys.length - selected.length;
  if (skipped > 0) {
    warnings.push(
      `${skipped} line${skipped === 1 ? "" : "s"} dropped because they sit outside the fit window or above the excitation energy.`,
    );
  }

  warnOverlaps(selected, config.fwhmAtMnEv, warnings);

  const length = hi - lo + 1;
  const columns: Float64Array[] = [];
  const meta: { line: XrayLine; escapeFraction: number; sigmaCh: number }[] = [];

  for (const line of selected) {
    const column = new Float64Array(length);
    const mu = channelOf(line.energy, zero, gain) - lo;
    const sigma = sigmaChannels(line.energy, config.fwhmAtMnEv, gain);
    addUnitGaussian(column, mu, sigma, 1);
    let escapeFraction = 0;
    if (config.includeEscape && line.energy - SI_ESCAPE_KEV > config.emin) {
      escapeFraction = escapeYield(line.energy);
      const escapeMu = channelOf(line.energy - SI_ESCAPE_KEV, zero, gain) - lo;
      const escapeSigma = sigmaChannels(line.energy - SI_ESCAPE_KEV, config.fwhmAtMnEv, gain);
      addUnitGaussian(column, escapeMu, escapeSigma, escapeFraction);
    }
    normalize(column);
    columns.push(column);
    meta.push({ line, escapeFraction, sigmaCh: sigma });
  }

  const net = new Float64Array(length);
  const invVar = new Float64Array(length);
  for (let i = 0; i < length; i++) {
    const gross = counts[lo + i];
    net[i] = gross - fullBackground[lo + i];
    invVar[i] = 1 / Math.max(gross, 1);
  }

  const areas = nnls(columns, net, invVar);
  const model = counts.slice();
  for (let i = 0; i < n; i++) model[i] = fullBackground[i];

  const peaks: PeakResult[] = meta.map((entry, index) => {
    const total = areas[index] ?? 0;
    const mainShare = 1 / (1 + entry.escapeFraction);
    const area = total * mainShare;
    const peak = new Float64Array(length);
    const mu = channelOf(entry.line.energy, zero, gain) - lo;
    addUnitGaussian(peak, mu, entry.sigmaCh, 1);
    normalize(peak);
    for (let i = 0; i < length; i++) model[lo + i] += peak[i] * area;
    if (entry.escapeFraction > 0) {
      const escape = new Float64Array(length);
      const escapeMu = channelOf(entry.line.energy - SI_ESCAPE_KEV, zero, gain) - lo;
      const escapeSigma = sigmaChannels(entry.line.energy - SI_ESCAPE_KEV, config.fwhmAtMnEv, gain);
      addUnitGaussian(escape, escapeMu, escapeSigma, 1);
      normalize(escape);
      for (let i = 0; i < length; i++) model[lo + i] += escape[i] * area * entry.escapeFraction;
    }
    const width = fwhmEv(entry.line.energy, config.fwhmAtMnEv);
    const sigmaCh = entry.sigmaCh;
    const amplitude = sigmaCh > 0 ? area / (sigmaCh * Math.sqrt(2 * Math.PI)) : 0;
    return {
      key: lineKey(entry.line),
      element: entry.line.symbol,
      series: entry.line.series,
      energy: entry.line.energy,
      area,
      fwhmEv: width,
      amplitude,
      cps: spectrum.liveTimeS > 0 ? area / spectrum.liveTimeS : null,
    };
  });

  peaks.sort((a, b) => a.energy - b.energy);

  let chi2 = 0;
  for (let i = lo; i <= hi; i++) {
    const delta = counts[i] - model[i];
    chi2 += (delta * delta) / Math.max(counts[i], 1);
  }
  const used = Math.max(0, hi - lo + 1);
  const free = peaks.filter((peak) => peak.area > 0).length;
  const dof = Math.max(1, used - free);
  return {
    peaks,
    background: fullBackground,
    model,
    chi2,
    reducedChi2: chi2 / dof,
    dof,
    channelsUsed: used,
    warnings,
  };
}

export function suggestLines(
  spectrum: Spectrum,
  calibration: Calibration,
  emin: number,
  emax: number,
  fwhmAtMnEv: number,
  excitationKeV: number,
  snipIterations: number,
): string[] {
  const counts = spectrum.counts;
  const [lo, hi] = region(counts.length, {
    calibration,
    emin,
    emax,
    fwhmAtMnEv,
    snipIterations,
    lineKeys: [],
    excitationKeV,
    includeEscape: false,
  });
  const background = snipBackground(counts.subarray(lo, hi + 1), snipIterations);
  const peaks: number[] = [];
  for (let i = lo + 2; i <= hi - 2; i++) {
    const local = i - lo;
    const y = counts[i];
    const bg = background[local];
    const threshold = bg + 4 * Math.sqrt(Math.max(bg, 1));
    if (y < threshold) continue;
    if (y < counts[i - 1] || y < counts[i + 1]) continue;
    if (y < counts[i - 2] || y < counts[i + 2]) continue;
    if (peaks.length && i - peaks[peaks.length - 1] < 3) {
      if (y > counts[peaks[peaks.length - 1]]) peaks[peaks.length - 1] = i;
      continue;
    }
    peaks.push(i);
  }

  const chosen = new Map<string, XrayLine>();
  for (const channel of peaks) {
    const energy = energyOf(channel, calibration.zero, calibration.gain);
    const width = fwhmEv(energy, fwhmAtMnEv) / 1000;
    const tolerance = Math.max(0.08, 0.55 * width);
    let best: XrayLine | null = null;
    let bestDist = tolerance;
    for (const line of LINES) {
      if (line.edge >= excitationKeV) continue;
      if (line.energy < emin || line.energy > emax) continue;
      const dist = Math.abs(line.energy - energy);
      if (dist < bestDist) {
        best = line;
        bestDist = dist;
      }
    }
    if (best) chosen.set(lineKey(best), best);
  }

  for (const line of [...chosen.values()]) {
    const partner = line.series === "Ka" ? "Kb" : line.series === "La" ? "Lb" : null;
    if (!partner) continue;
    const extra = LINES.find((item) => item.symbol === line.symbol && item.series === partner);
    if (!extra) continue;
    if (extra.edge >= excitationKeV) continue;
    if (extra.energy < emin || extra.energy > emax) continue;
    chosen.set(lineKey(extra), extra);
  }

  return [...chosen.values()]
    .sort((a, b) => a.energy - b.energy)
    .map((line) => lineKey(line));
}

export function calibrationFromAnchors(
  a: { channel: number; energy: number },
  b: { channel: number; energy: number },
): Calibration {
  if (a.channel === b.channel) throw new Error("The two calibration channels must differ.");
  const gain = (b.energy - a.energy) / (b.channel - a.channel);
  const zero = a.energy - gain * a.channel;
  return { zero, gain };
}

function region(n: number, config: FitConfig): [number, number] {
  const { zero, gain } = config.calibration;
  let lo = Math.ceil(channelOf(config.emin, zero, gain));
  let hi = Math.floor(channelOf(config.emax, zero, gain));
  if (hi < lo) {
    const swap = lo;
    lo = hi;
    hi = swap;
  }
  lo = Math.max(0, Math.min(n - 1, lo));
  hi = Math.max(0, Math.min(n - 1, hi));
  return [lo, hi];
}

function normalize(column: Float64Array) {
  let sum = 0;
  for (let i = 0; i < column.length; i++) sum += column[i];
  if (sum > 0) {
    for (let i = 0; i < column.length; i++) column[i] /= sum;
  }
}

function escapeYield(energyKeV: number): number {
  if (energyKeV < 2) return 0;
  return 0.012 * Math.exp(-(energyKeV - 4) / 14);
}

function warnOverlaps(lines: XrayLine[], fwhmAtMnEv: number, warnings: string[]) {
  for (let i = 0; i < lines.length; i++) {
    for (let j = i + 1; j < lines.length; j++) {
      const gap = Math.abs(lines[i].energy - lines[j].energy);
      const width = (0.45 * fwhmEv((lines[i].energy + lines[j].energy) / 2, fwhmAtMnEv)) / 1000;
      if (gap < width) {
        warnings.push(
          `${lineKey(lines[i])} and ${lineKey(lines[j])} are closer than the detector can separate cleanly. Areas will be shared between them.`,
        );
      }
    }
  }
}
