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

export function spectrumToCsv(spectrum: Spectrum, calibration: Calibration): string {
  const rows = ["channel,energy_keV,counts"];
  for (let i = 0; i < spectrum.counts.length; i++) {
    const energy = spectrum.energy ? spectrum.energy[i] : calibration.zero + calibration.gain * i;
    rows.push(`${i},${energy},${spectrum.counts[i]}`);
  }
  return rows.join("\n");
}
