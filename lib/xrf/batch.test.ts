import { describe, expect, it } from "vitest";
import { buildBatchTable, fitSpectra, fitStamp } from "@/lib/xrf/batch";
import { fitCurves } from "@/lib/xrf/curve";
import { DEMO_CALIBRATION, DEMO_FWHM, demoSpectra } from "@/lib/xrf/demo";
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

describe("batch fit", () => {
  const spectra = demoSpectra();

  it("fits only the scans that were handed to the run", () => {
    const chosen = spectra.filter((spectrum) => spectrum.id !== "demo-std-low");
    const fits = fitSpectra(chosen, config);
    expect(Object.keys(fits).sort()).toEqual(["demo-std-high", "demo-unknown"]);
    expect(fits["demo-unknown"].peaks.some((peak) => peak.key === "Fe Ka" && peak.area > 0)).toBe(true);
  });

  it("builds one row per fitted scan and a concentration for the unknown", () => {
    const fits = fitSpectra(spectra, config);
    const curves = fitCurves(spectra, fits);
    const table = buildBatchTable(spectra, fits, curves);
    expect(table.rows.map((row) => row.name)).toEqual(["Std 500 ppm", "Std 2000 ppm", "Unknown bronze"]);
    expect(table.elements).toEqual(["Ca", "Fe", "Cu", "Zn", "Pb"]);
    const unknown = table.rows[2];
    expect(unknown.cells.Fe.lineKey).toBe("Fe Ka");
    expect(unknown.cells.Fe.concentration).toBeGreaterThan(1250 * 0.85);
    expect(unknown.cells.Fe.concentration).toBeLessThan(1250 * 1.15);
    expect(unknown.cells.Pb.concentration).toBeNull();
    expect(unknown.cells.Pb.area).toBeGreaterThan(5000);
    expect(table.rows[0].cells.Pb.area).toBeLessThan(unknown.cells.Pb.area * 0.05);
  });

  it("changes the run stamp when the scan list or the lines change", () => {
    const first = fitStamp(config, ["a", "b"]);
    expect(fitStamp(config, ["b", "a"])).toBe(first);
    expect(fitStamp(config, ["a"])).not.toBe(first);
    expect(fitStamp({ ...config, lineKeys: ["Fe Ka"] }, ["a", "b"])).not.toBe(first);
  });
});
