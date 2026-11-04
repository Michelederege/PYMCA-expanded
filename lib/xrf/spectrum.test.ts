import { describe, expect, it } from "vitest";
import { parseSpectraText, parseSpectrumText } from "@/lib/xrf/spectrum";

function ids() {
  let n = 0;
  return () => `id-${++n}`;
}

function counts(start: number, length = 8): string {
  return Array.from({ length }, (_, index) => String(start + index)).join("\n");
}

describe("parseSpectraText", () => {
  it("keeps a two-column file as one spectrum named from the file", () => {
    const text = ["energy,counts", ...Array.from({ length: 8 }, (_, i) => `${i * 0.01},${10 + i}`)].join("\n");
    const spectra = parseSpectraText(text, "foil.csv", ids());
    expect(spectra).toHaveLength(1);
    expect(spectra[0].name).toBe("foil");
    expect(spectra[0].counts.length).toBe(8);
    expect(spectra[0].energy?.[0]).toBe(0);
  });

  it("reads several scans from scan headers, including role and concentrations", () => {
    const text = [
      "# scan: Std low",
      "# role: standard",
      "# live time: 30",
      "# known: Fe 500",
      "# known: Cu 200",
      counts(10),
      "#S 2 Unknown bronze",
      counts(40),
    ].join("\n");
    const spectra = parseSpectraText(text, "session.txt", ids());
    expect(spectra.map((spectrum) => spectrum.name)).toEqual(["Std low", "Unknown bronze"]);
    expect(spectra[0].role).toBe("standard");
    expect(spectra[0].liveTimeS).toBe(30);
    expect(spectra[0].known).toEqual({ Fe: 500, Cu: 200 });
    expect(spectra[1].role).toBe("unknown");
    expect(spectra[1].counts[0]).toBe(40);
    expect(spectra[0].id).not.toBe(spectra[1].id);
  });

  it("reads one column per sample when the header names the scans", () => {
    const header = "energy_keV,Low,High";
    const body = Array.from({ length: 8 }, (_, i) => `${(i * 0.05).toFixed(2)},${100 + i},${200 + i}`);
    const spectra = parseSpectraText([header, ...body].join("\n"), "batch.csv", ids());
    expect(spectra.map((spectrum) => spectrum.name)).toEqual(["Low", "High"]);
    expect(spectra[0].counts[0]).toBe(100);
    expect(spectra[1].counts[7]).toBe(207);
    expect(spectra[0].energy?.[1]).toBeCloseTo(0.05);
    expect(spectra[1].energy?.[1]).toBeCloseTo(0.05);
  });

  it("treats every column as a scan when none of them is an energy axis", () => {
    const header = "Alpha,Beta";
    const body = Array.from({ length: 8 }, (_, i) => `${10 + i},${20 + i}`);
    const spectra = parseSpectraText([header, ...body].join("\n"), "counts.csv", ids());
    expect(spectra.map((spectrum) => spectrum.name)).toEqual(["Alpha", "Beta"]);
    expect(spectra[0].energy).toBeUndefined();
    expect(spectra[1].counts[0]).toBe(20);
  });

  it("still parses a single counts column", () => {
    const spectrum = parseSpectrumText(counts(3, 10), "one.csv", "only");
    expect(spectrum.name).toBe("one");
    expect(spectrum.counts.length).toBe(10);
  });
});
