export type SpectrumRole = "unknown" | "standard";

export type Spectrum = {
  id: string;
  name: string;
  counts: Float64Array;
  /** When set, channel index i already has this energy and calibration is derived from it. */
  energy?: Float64Array;
  liveTimeS: number;
  role: SpectrumRole;
  /** Known concentrations keyed by element symbol. Empty fields are omitted. */
  known: Record<string, number>;
};

export type Calibration = {
  zero: number;
  gain: number;
};

export type FitConfig = {
  calibration: Calibration;
  emin: number;
  emax: number;
  /** Detector FWHM at Mn Ka, electronvolts. */
  fwhmAtMnEv: number;
  /** SNIP window in channels. */
  snipIterations: number;
  /** Line keys such as "Fe Ka". */
  lineKeys: string[];
  excitationKeV: number;
  includeEscape: boolean;
};

export type PeakResult = {
  key: string;
  element: string;
  series: string;
  energy: number;
  area: number;
  fwhmEv: number;
  amplitude: number;
  cps: number | null;
};

export type FitResult = {
  peaks: PeakResult[];
  background: Float64Array;
  model: Float64Array;
  chi2: number;
  reducedChi2: number;
  dof: number;
  channelsUsed: number;
  warnings: string[];
};

export type CalibrationCurve = {
  element: string;
  lineKey: string;
  slope: number;
  intercept: number;
  r2: number | null;
  points: { sample: string; area: number; concentration: number }[];
};
