import { fitSpectra } from "@/lib/xrf/batch";
import { fitCurves } from "@/lib/xrf/curve";
import { DEMO_CALIBRATION, DEMO_FWHM, demoSpectra } from "@/lib/xrf/demo";
import { suggestLines } from "@/lib/xrf/fit";
import type { CalibrationCurve, FitConfig } from "@/lib/xrf/types";

/** Written by Fit and read by Batch. Batch does not need the fit window open. */
export const HANDOFF_KEY = "xrf-batch-handoff";

export type StoredCurve = {
  element: string;
  lineKey: string;
  slope: number;
  intercept: number;
  r2: number | null;
};

export type FitConfiguration = {
  version: 1;
  name: string;
  calibration: { zero: number; gain: number };
  emin: number;
  emax: number;
  fwhmAtMnEv: number;
  snipIterations: number;
  excitationKeV: number;
  includeEscape: boolean;
  lineKeys: string[];
  curves: StoredCurve[];
};

export function toFitConfig(configuration: FitConfiguration): FitConfig {
  return {
    calibration: { ...configuration.calibration },
    emin: configuration.emin,
    emax: configuration.emax,
    fwhmAtMnEv: configuration.fwhmAtMnEv,
    snipIterations: configuration.snipIterations,
    excitationKeV: configuration.excitationKeV,
    includeEscape: configuration.includeEscape,
    lineKeys: [...configuration.lineKeys],
  };
}

export function curvesFromConfiguration(configuration: FitConfiguration): CalibrationCurve[] {
  return configuration.curves.map((curve) => ({ ...curve, points: [] }));
}

export function configurationFromSession(name: string, config: FitConfig, curves: CalibrationCurve[]): FitConfiguration {
  return {
    version: 1,
    name,
    calibration: { zero: config.calibration.zero, gain: config.calibration.gain },
    emin: config.emin,
    emax: config.emax,
    fwhmAtMnEv: config.fwhmAtMnEv,
    snipIterations: config.snipIterations,
    excitationKeV: config.excitationKeV,
    includeEscape: config.includeEscape,
    lineKeys: [...config.lineKeys],
    curves: curves.map((curve) => ({
      element: curve.element,
      lineKey: curve.lineKey,
      slope: curve.slope,
      intercept: curve.intercept,
      r2: curve.r2,
    })),
  };
}

/** The bronze standards, saved the way Fit writes a configuration for Batch. */
export function bronzeConfiguration(): FitConfiguration {
  const spectra = demoSpectra();
  const lineKeys = suggestLines(spectra[2], DEMO_CALIBRATION, 1, 20, DEMO_FWHM, 40, 14);
  const config: FitConfig = {
    calibration: DEMO_CALIBRATION,
    emin: 1,
    emax: 20,
    fwhmAtMnEv: DEMO_FWHM,
    snipIterations: 14,
    excitationKeV: 40,
    includeEscape: false,
    lineKeys,
  };
  const fits = fitSpectra(spectra, config);
  return configurationFromSession("Bronze", config, fitCurves(spectra, fits));
}

export function serializeConfiguration(configuration: FitConfiguration): string {
  return JSON.stringify(configuration, null, 2);
}

export function parseConfiguration(text: string): FitConfiguration {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new Error("That file is not a fit configuration.");
  }
  if (!isRecord(raw) || raw.version !== 1) throw new Error("This configuration is not version 1.");
  const calibration = raw.calibration;
  if (!isRecord(calibration)) throw new Error("The configuration has no energy calibration.");
  const lineKeys = stringList(raw.lineKeys, "lines");
  if (lineKeys.length === 0) throw new Error("The configuration has no lines.");
  const curves = Array.isArray(raw.curves) ? raw.curves.map(parseCurve) : [];
  return {
    version: 1,
    name: typeof raw.name === "string" && raw.name.trim() ? raw.name.trim() : "Configuration",
    calibration: {
      zero: finite(calibration.zero, "calibration zero"),
      gain: finite(calibration.gain, "calibration gain"),
    },
    emin: finite(raw.emin, "fit start"),
    emax: finite(raw.emax, "fit end"),
    fwhmAtMnEv: finite(raw.fwhmAtMnEv, "FWHM"),
    snipIterations: finite(raw.snipIterations, "background width"),
    excitationKeV: finite(raw.excitationKeV, "excitation"),
    includeEscape: Boolean(raw.includeEscape),
    lineKeys,
    curves,
  };
}

function parseCurve(value: unknown): StoredCurve {
  if (!isRecord(value)) throw new Error("A calibration curve in the configuration is unreadable.");
  const element = typeof value.element === "string" ? value.element : "";
  const lineKey = typeof value.lineKey === "string" ? value.lineKey : "";
  if (!element || !lineKey) throw new Error("A calibration curve is missing its element or line.");
  return {
    element,
    lineKey,
    slope: finite(value.slope, `${element} slope`),
    intercept: finite(value.intercept, `${element} intercept`),
    r2: value.r2 === null ? null : finite(value.r2, `${element} R²`),
  };
}

function stringList(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`The configuration has no ${label}.`);
  }
  return value;
}

function finite(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`The configuration has no ${label}.`);
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
