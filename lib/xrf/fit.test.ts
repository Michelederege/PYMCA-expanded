import { describe, expect, it } from "vitest";
import { fitCurves, predictConcentration } from "@/lib/xrf/curve";
import { DEMO_CALIBRATION, DEMO_FWHM, demoSpectra } from "@/lib/xrf/demo";
import { fitSpectrum, suggestLines } from "@/lib/xrf/fit";
import { buildExportRecords } from "@/lib/xrf/export-rows";
import { nnls } from "@/lib/xrf/nnls";
import type { FitConfig } from "@/lib/xrf/types";

const config: FitConfig = {
  calibration: DEMO_CALIBRATION,
  emin: 1.5,
  emax: 16,
  fwhmAtMnEv: DEMO_FWHM,
  snipIterations: 14,
  lineKeys: ["Ca Ka", "Fe Ka", "Fe Kb", "Cu Ka", "Cu Kb", "Zn Ka", "Pb La", "Pb Lb"],
  excitationKeV: 40,
  includeEscape: false,
};

describe("nnls", () => {
  it("keeps positive amplitudes and drops negative ones", () => {
    const columns = [Float64Array.from([1, 0, 0]), Float64Array.from([0, 1, 0])];
    const y = Float64Array.from([-4, 6, 1]);
    const w = Float64Array.from([1, 1, 1]);
    const x = nnls(columns, y, w);
    expect(x[0]).toBe(0);
    expect(x[1]).toBeCloseTo(6, 5);
  });
});

describe("xrf fit", () => {
  const spectra = demoSpectra();
  const fits = Object.fromEntries(spectra.map((spectrum) => [spectrum.id, fitSpectrum(spectrum, config)]));

  it("recovers the unknown bronze peak areas", () => {
    const unknown = fits["demo-unknown"];
    const area = (key: string) => unknown.peaks.find((peak) => peak.key === key)?.area ?? 0;
    expect(area("Fe Ka")).toBeGreaterThan(1250 * 18 * 0.85);
    expect(area("Fe Ka")).toBeLessThan(1250 * 18 * 1.15);
    expect(area("Cu Ka")).toBeGreaterThan(520 * 25 * 0.85);
    expect(area("Cu Ka")).toBeLessThan(520 * 25 * 1.15);
    expect(area("Pb La")).toBeGreaterThan(7400 * 0.8);
    expect(unknown.peaks.every((peak) => peak.area >= 0)).toBe(true);
    expect(unknown.reducedChi2).toBeGreaterThan(0.2);
    expect(unknown.reducedChi2).toBeLessThan(8);
  });

  it("suggests the lines that are actually in the bronze spectrum", () => {
    const keys = suggestLines(spectra[2], DEMO_CALIBRATION, 1.5, 16, DEMO_FWHM, 40, 14);
    expect(keys).toContain("Fe Ka");
    expect(keys).toContain("Cu Ka");
    expect(keys).toContain("Zn Ka");
    expect(keys).toContain("Pb La");
    expect(keys).not.toContain("Na Ka");
    expect(keys).not.toContain("Ge Ka");
    expect(keys.length).toBeLessThan(16);
  });

  it("writes a row per detected line rather than one per noise bump", () => {
    const suggested = suggestLines(spectra[2], DEMO_CALIBRATION, 1, 20, DEMO_FWHM, 40, 14);
    const suggestedFits = Object.fromEntries(
      spectra.map((spectrum) => [
        spectrum.id,
        fitSpectrum(spectrum, { ...config, emin: 1, emax: 20, lineKeys: suggested }),
      ]),
    );
    const records = buildExportRecords(spectra, suggestedFits, fitCurves(spectra, suggestedFits), "long");
    expect(records.length).toBeGreaterThan(8);
    expect(records.length).toBeLessThan(40);
    expect(records.some((row) => row.element === "Na")).toBe(false);
  });

  it("turns two standards into concentrations near the bronze recipe", () => {
    const curves = fitCurves(spectra, fits);
    const iron = curves.find((curve) => curve.element === "Fe");
    const copper = curves.find((curve) => curve.element === "Cu");
    const zinc = curves.find((curve) => curve.element === "Zn");
    expect(iron?.r2 ?? 0).toBeGreaterThan(0.98);
    const feArea = fits["demo-unknown"].peaks.find((peak) => peak.key === "Fe Ka")!.area;
    const cuArea = fits["demo-unknown"].peaks.find((peak) => peak.key === "Cu Ka")!.area;
    const znArea = fits["demo-unknown"].peaks.find((peak) => peak.key === "Zn Ka")!.area;
    expect(predictConcentration(iron, feArea)!).toBeGreaterThan(1250 * 0.85);
    expect(predictConcentration(iron, feArea)!).toBeLessThan(1250 * 1.15);
    expect(predictConcentration(copper, cuArea)!).toBeGreaterThan(520 * 0.85);
    expect(predictConcentration(copper, cuArea)!).toBeLessThan(520 * 1.15);
    expect(predictConcentration(zinc, znArea)!).toBeGreaterThan(230 * 0.8);
    expect(predictConcentration(zinc, znArea)!).toBeLessThan(230 * 1.2);
  });
});
