import { addUnitGaussian, sigmaChannels } from "@/lib/xrf/shape";
import type { Spectrum } from "@/lib/xrf/types";

const CHANNELS = 2048;
const ZERO = 0;
const GAIN = 0.01;
const FWHM = 155;

type Recipe = {
  id: string;
  name: string;
  role: Spectrum["role"];
  known: Record<string, number>;
  areas: { energy: number; counts: number }[];
  seed: number;
};

const RECIPES: Recipe[] = [
  {
    id: "demo-std-low",
    name: "Std 500 ppm",
    role: "standard",
    known: { Fe: 500, Cu: 200, Zn: 100 },
    areas: [
      { energy: 3.6905, counts: 4200 },
      { energy: 6.3995, counts: 500 * 18 },
      { energy: 7.05798, counts: 500 * 2.4 },
      { energy: 8.0411, counts: 200 * 25 },
      { energy: 8.90529, counts: 200 * 3.2 },
      { energy: 8.6312, counts: 100 * 22 },
    ],
    seed: 11,
  },
  {
    id: "demo-std-high",
    name: "Std 2000 ppm",
    role: "standard",
    known: { Fe: 2000, Cu: 800, Zn: 400 },
    areas: [
      { energy: 3.6905, counts: 4500 },
      { energy: 6.3995, counts: 2000 * 18 },
      { energy: 7.05798, counts: 2000 * 2.4 },
      { energy: 8.0411, counts: 800 * 25 },
      { energy: 8.90529, counts: 800 * 3.2 },
      { energy: 8.6312, counts: 400 * 22 },
    ],
    seed: 29,
  },
  {
    id: "demo-unknown",
    name: "Unknown bronze",
    role: "unknown",
    known: {},
    areas: [
      { energy: 3.6905, counts: 3800 },
      { energy: 6.3995, counts: 1250 * 18 },
      { energy: 7.05798, counts: 1250 * 2.4 },
      { energy: 8.0411, counts: 520 * 25 },
      { energy: 8.90529, counts: 520 * 3.2 },
      { energy: 8.6312, counts: 230 * 22 },
      { energy: 10.5515, counts: 7400 },
      { energy: 12.6137, counts: 4200 },
    ],
    seed: 47,
  },
];

export const DEMO_CALIBRATION = { zero: ZERO, gain: GAIN };
export const DEMO_FWHM = FWHM;

export function demoSpectra(): Spectrum[] {
  return RECIPES.map((recipe) => {
    const expected = new Float64Array(CHANNELS);
    for (let i = 0; i < CHANNELS; i++) {
      const energy = ZERO + GAIN * i;
      expected[i] = 22 * Math.exp(-energy / 7) + 3;
    }
    for (const peak of recipe.areas) {
      const mu = (peak.energy - ZERO) / GAIN;
      const sigma = sigmaChannels(peak.energy, FWHM, GAIN);
      addUnitGaussian(expected, mu, sigma, peak.counts);
    }
    const rng = mulberry32(recipe.seed);
    const counts = new Float64Array(CHANNELS);
    for (let i = 0; i < CHANNELS; i++) counts[i] = poisson(rng, expected[i]);
    return {
      id: recipe.id,
      name: recipe.name,
      counts,
      liveTimeS: 60,
      role: recipe.role,
      known: { ...recipe.known },
    };
  });
}

function mulberry32(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function poisson(rng: () => number, lambda: number): number {
  if (lambda <= 0) return 0;
  if (lambda > 40) {
    const u = Math.max(1e-12, rng());
    const v = rng();
    const z = Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    return Math.max(0, Math.round(lambda + Math.sqrt(lambda) * z));
  }
  const limit = Math.exp(-lambda);
  let k = 0;
  let p = 1;
  do {
    k++;
    p *= rng();
  } while (p > limit);
  return k - 1;
}
