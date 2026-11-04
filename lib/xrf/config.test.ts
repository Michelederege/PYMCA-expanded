import { describe, expect, it } from "vitest";
import { buildBatchTable, fitSpectra } from "@/lib/xrf/batch";
import { bronzeConfiguration, curvesFromConfiguration, parseConfiguration, serializeConfiguration, toFitConfig } from "@/lib/xrf/config";
import { demoSpectra } from "@/lib/xrf/demo";
import { recordsToCsv } from "@/lib/xrf/export-rows";

describe("fit configuration", () => {
  it("round-trips through a file", () => {
    const saved = bronzeConfiguration();
    const loaded = parseConfiguration(serializeConfiguration(saved));
    expect(loaded.name).toBe("Bronze");
    expect(loaded.lineKeys).toEqual(saved.lineKeys);
    expect(loaded.curves.map((curve) => curve.element)).toEqual(saved.curves.map((curve) => curve.element));
    expect(loaded.calibration).toEqual(saved.calibration);
  });

  it("quantifies a scan from the configuration, without the standards present", () => {
    const configuration = bronzeConfiguration();
    const unknown = demoSpectra().find((spectrum) => spectrum.id === "demo-unknown");
    if (!unknown) throw new Error("missing unknown");
    const fits = fitSpectra([unknown], toFitConfig(configuration));
    const table = buildBatchTable([unknown], fits, curvesFromConfiguration(configuration));
    expect(table.rows).toHaveLength(1);
    expect(table.rows[0].cells.Fe.concentration).toBeGreaterThan(1250 * 0.85);
    expect(table.rows[0].cells.Fe.concentration).toBeLessThan(1250 * 1.15);
    expect(table.rows[0].cells.Cu.concentration).toBeGreaterThan(520 * 0.85);
    expect(table.rows[0].cells.Zn.concentration).toBeGreaterThan(230 * 0.8);
  });

  it("rejects a file that is not a configuration", () => {
    expect(() => parseConfiguration("{")).toThrow(/not a fit configuration/);
    expect(() => parseConfiguration('{"version":2}')).toThrow(/version 1/);
  });
});

describe("recordsToCsv", () => {
  it("keeps a column that only a later row has", () => {
    const csv = recordsToCsv([
      { sample: "A", "area:Fe Ka": 10 },
      { sample: "B", "area:Pb La": 4 },
    ]);
    expect(csv.split("\n")[0]).toBe("sample,area:Fe Ka,area:Pb La");
    expect(csv).toContain("B,,4");
  });
});
