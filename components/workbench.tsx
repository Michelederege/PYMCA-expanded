"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ExcelMapper } from "@/components/excel-mapper";
import { SpectrumPlot } from "@/components/spectrum-plot";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fitSpectra } from "@/lib/xrf/batch";
import {
  HANDOFF_KEY,
  configurationFromSession,
  serializeConfiguration,
} from "@/lib/xrf/config";
import { fitCurves, predictConcentration, primaryLineKey } from "@/lib/xrf/curve";
import { DEMO_CALIBRATION, DEMO_FWHM, demoSpectra } from "@/lib/xrf/demo";
import { buildExportRecords } from "@/lib/xrf/export-rows";
import { calibrationFromAnchors, significantPeaks, suggestLines } from "@/lib/xrf/fit";
import { LINES, elementOf, lineKey } from "@/lib/xrf/lines";
import { calibrationFromSpectrum, parseSpectraText, spectrumToCsv } from "@/lib/xrf/spectrum";
import type { Calibration, FitConfig, FitResult, Spectrum } from "@/lib/xrf/types";

export function Workbench() {
  const [spectra, setSpectra] = useState<Spectrum[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [calibration, setCalibration] = useState<Calibration>(DEMO_CALIBRATION);
  const [emin, setEmin] = useState(1);
  const [emax, setEmax] = useState(20);
  const [fwhm, setFwhm] = useState(DEMO_FWHM);
  const [snip, setSnip] = useState(14);
  const [excitation, setExcitation] = useState(40);
  const [escapePeaks, setEscapePeaks] = useState(false);
  const [lineKeys, setLineKeys] = useState<string[]>([]);
  const [fits, setFits] = useState<Record<string, FitResult>>({});
  const [logScale, setLogScale] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [anchorA, setAnchorA] = useState({ channel: "369", energy: "3.6905" });
  const [anchorB, setAnchorB] = useState({ channel: "804", energy: "8.0411" });
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const active = spectra.find((spectrum) => spectrum.id === activeId) ?? null;
  const activeFit = active ? fits[active.id] : undefined;

  const config = useMemo<FitConfig>(
    () => ({
      calibration,
      emin,
      emax,
      fwhmAtMnEv: fwhm,
      snipIterations: snip,
      lineKeys,
      excitationKeV: excitation,
      includeEscape: escapePeaks,
    }),
    [calibration, emin, emax, fwhm, snip, lineKeys, excitation, escapePeaks],
  );

  const curves = useMemo(() => fitCurves(spectra.filter((spectrum) => fits[spectrum.id]), fits), [spectra, fits]);
  const shownPeaks = useMemo(() => (activeFit ? significantPeaks(activeFit.peaks) : []), [activeFit]);
  const recordsLong = useMemo(() => buildExportRecords(spectra, fits, curves, "long"), [spectra, fits, curves]);
  const recordsWide = useMemo(() => buildExportRecords(spectra, fits, curves, "wide"), [spectra, fits, curves]);

  useEffect(() => {
    const loaded = demoSpectra();
    const suggested = suggestLines(loaded[2], DEMO_CALIBRATION, 1, 20, DEMO_FWHM, 40, 14);
    const initial: FitConfig = {
      ...config,
      calibration: DEMO_CALIBRATION,
      lineKeys: suggested,
      fwhmAtMnEv: DEMO_FWHM,
    };
    setSpectra(loaded);
    setActiveId(loaded[2].id);
    setLineKeys(suggested);
    setFits(fitSpectra(loaded, initial));
    // The demo is a fixed starting point; later fits are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function runFit(nextSpectra = spectra, nextConfig = config) {
    setError(null);
    if (nextSpectra.length === 0) {
      setError("Load a spectrum first.");
      return;
    }
    if (nextConfig.lineKeys.length === 0) {
      setError("Select at least one line to fit.");
      return;
    }
    try {
      setFits(fitSpectra(nextSpectra, nextConfig));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The fit failed.");
    }
  }

  function sessionConfiguration() {
    if (config.lineKeys.length === 0) throw new Error("Select at least one line before saving a configuration.");
    return configurationFromSession("Session", config, curves);
  }

  function saveConfiguration() {
    try {
      const saved = sessionConfiguration();
      const blob = new Blob([serializeConfiguration(saved)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = "fit-configuration.json";
      link.click();
      URL.revokeObjectURL(url);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save the configuration.");
    }
  }

  function openBatch() {
    try {
      const saved = sessionConfiguration();
      window.localStorage.setItem(HANDOFF_KEY, serializeConfiguration(saved));
      const popup = window.open(`/batch?handoff=${Date.now()}`, "xrf-batch", "popup,width=1280,height=860");
      if (!popup) {
        setError("The browser blocked the Batch window. Open /batch in a new window after allowing popups.");
        return;
      }
      popup.focus();
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open Batch.");
    }
  }

  function addSpectra(incoming: Spectrum[]) {
    if (incoming.length === 0) return;
    const wasEmpty = spectra.length === 0;
    const withEnergy = incoming.find((spectrum) => spectrum.energy);
    const nextCalibration = withEnergy ? calibrationFromSpectrum(withEnergy, calibration) : calibration;
    const nextLines = lineKeys.length > 0
      ? lineKeys
      : suggestLines(incoming[0], nextCalibration, emin, emax, fwhm, excitation, snip);
    setCalibration(nextCalibration);
    setSpectra((current) => [...current, ...incoming]);
    setActiveId(incoming[incoming.length - 1].id);
    setLineKeys(nextLines);
    if (nextLines.length === 0) {
      setError("No lines stood out above the background. Pick lines, then fit.");
      return;
    }
    setError(null);
    if (wasEmpty) {
      const nextConfig = { ...config, calibration: nextCalibration, lineKeys: nextLines };
      setFits(fitSpectra(incoming, nextConfig));
    }
  }

  async function onSpectrumFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setError(null);
    const incoming: Spectrum[] = [];
    const problems: string[] = [];
    let sequence = 0;
    for (const file of files) {
      try {
        const text = await file.text();
        incoming.push(
          ...parseSpectraText(text, file.name, () => {
            sequence += 1;
            return `file-${Date.now()}-${sequence}-${Math.random().toString(36).slice(2, 6)}`;
          }),
        );
      } catch (caught) {
        problems.push(caught instanceof Error ? caught.message : `Could not read ${file.name}.`);
      }
    }
    if (incoming.length > 0) addSpectra(incoming);
    if (problems.length > 0) setError(problems.join(" "));
  }

  function suggest() {
    if (!active) return;
    const keys = suggestLines(active, calibration, emin, emax, fwhm, excitation, snip);
    setLineKeys(keys);
    if (keys.length === 0) setError("No lines stood out above the background in this window.");
    else setError(null);
  }

  function applyAnchors() {
    try {
      const next = calibrationFromAnchors(
        { channel: Number(anchorA.channel), energy: Number(anchorA.energy) },
        { channel: Number(anchorB.channel), energy: Number(anchorB.energy) },
      );
      if (!Number.isFinite(next.gain) || !Number.isFinite(next.zero)) throw new Error("Enter two numeric anchors.");
      setCalibration(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not set the calibration.");
    }
  }

  const elements = [...new Set(lineKeys.map(elementOf))];
  const visibleLines = LINES.filter((line) => {
    const key = lineKey(line);
    const hay = `${line.symbol} ${line.series}`.toLowerCase();
    if (query.trim() && !hay.includes(query.trim().toLowerCase())) return false;
    if (lineKeys.includes(key)) return true;
    if (line.edge >= excitation) return false;
    if (line.energy > emax + 1 || line.energy < Math.max(0, emin - 1)) return false;
    return true;
  });

  return (
    <div className="min-h-screen">
      <header className="flex h-12 items-center justify-between gap-3 border-b border-border px-3">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold">Fit</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">Calibrate one session, then hand the configuration to Batch</span>
        </div>
        <nav className="flex items-center gap-1">
          <Button type="button" variant="outline" size="sm" onClick={saveConfiguration}>Save configuration</Button>
          <Button type="button" size="sm" onClick={openBatch}>Open Batch</Button>
        </nav>
      </header>

      <div className="grid lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="flex flex-col gap-6 border-b border-border px-4 py-5 lg:border-r lg:border-b-0 md:px-5">
          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">Spectra</h2>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => {
                  const loaded = demoSpectra();
                  const suggested = suggestLines(loaded[2], DEMO_CALIBRATION, emin, emax, fwhm, excitation, snip);
                  const nextConfig = { ...config, calibration: DEMO_CALIBRATION, lineKeys: suggested };
                  setSpectra(loaded);
                  setActiveId(loaded[2].id);
                  setCalibration(DEMO_CALIBRATION);
                  setLineKeys(suggested);
                  setFits(fitSpectra(loaded, nextConfig));
                  setError(null);
                }}>
                  Bronze demo
                </Button>
              </div>
            </div>
            <label className={buttonVariants({ variant: "secondary" }) + " cursor-pointer"}>
              Load spectra
              <input
                className="sr-only"
                type="file"
                accept=".csv,.txt,.mca,.spec,text/csv,text/plain"
                multiple
                onChange={(event) => {
                  void onSpectrumFiles(event.target.files);
                  event.target.value = "";
                }}
              />
            </label>
            <p className="text-xs text-muted-foreground">
              Standards and the spectrum you are fitting live here. A file list for many scans belongs in Batch.
            </p>
            {spectra.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No spectra yet. One column of counts, or energy and counts, is enough.
              </p>
            ) : (
              <ul className="flex max-h-72 flex-col gap-2 overflow-auto">
                {spectra.map((spectrum) => (
                  <li key={spectrum.id}>
                    <button
                      type="button"
                      onClick={() => setActiveId(spectrum.id)}
                      className={`w-full rounded-lg border px-2.5 py-2 text-left ${
                        spectrum.id === activeId ? "border-primary bg-primary/10" : "border-border"
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium">{spectrum.name}</span>
                        <Badge variant="outline">{spectrum.role === "standard" ? "Standard" : "Unknown"}</Badge>
                      </span>
                      <span className="mt-1 block text-xs text-muted-foreground">
                        {spectrum.counts.length} channels · {spectrum.liveTimeS || "—"} s
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {active ? (
              <div className="grid grid-cols-2 gap-2">
                <Field label="Role">
                  <Select
                    value={active.role}
                    onValueChange={(value) => {
                      if (value !== "unknown" && value !== "standard") return;
                      setSpectra((current) =>
                        current.map((spectrum) =>
                          spectrum.id === active.id ? { ...spectrum, role: value } : spectrum,
                        ),
                      );
                    }}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="unknown">Unknown</SelectItem>
                      <SelectItem value="standard">Standard</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Live time (s)">
                  <Input
                    type="number"
                    min={0}
                    step="0.1"
                    value={active.liveTimeS}
                    onChange={(event) => {
                      const liveTimeS = Number(event.target.value);
                      setSpectra((current) =>
                        current.map((spectrum) =>
                          spectrum.id === active.id
                            ? { ...spectrum, liveTimeS: Number.isFinite(liveTimeS) ? liveTimeS : 0 }
                            : spectrum,
                        ),
                      );
                    }}
                  />
                </Field>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const blob = new Blob([spectrumToCsv(active, calibration)], { type: "text/csv" });
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = `${active.name}.csv`;
                    link.click();
                    URL.revokeObjectURL(url);
                  }}
                >
                  Download CSV
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const remaining = spectra.filter((spectrum) => spectrum.id !== active.id);
                    setSpectra(remaining);
                    setActiveId(remaining[0]?.id ?? null);
                    setFits((current) => {
                      const next = { ...current };
                      delete next[active.id];
                      return next;
                    });
                  }}
                >
                  Remove
                </Button>
              </div>
            ) : null}
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium">Calibration</h2>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Zero (keV)">
                <Input
                  type="number"
                  step="0.001"
                  value={calibration.zero}
                  onChange={(event) => setCalibration((current) => ({ ...current, zero: Number(event.target.value) }))}
                />
              </Field>
              <Field label="Gain (keV/ch)">
                <Input
                  type="number"
                  step="0.0001"
                  value={calibration.gain}
                  onChange={(event) => setCalibration((current) => ({ ...current, gain: Number(event.target.value) }))}
                />
              </Field>
            </div>
            <p className="text-xs text-muted-foreground">Two anchors replace zero and gain. Energy = zero + gain × channel.</p>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Channel A">
                <Input value={anchorA.channel} onChange={(event) => setAnchorA((current) => ({ ...current, channel: event.target.value }))} />
              </Field>
              <Field label="Energy A">
                <Input value={anchorA.energy} onChange={(event) => setAnchorA((current) => ({ ...current, energy: event.target.value }))} />
              </Field>
              <Field label="Channel B">
                <Input value={anchorB.channel} onChange={(event) => setAnchorB((current) => ({ ...current, channel: event.target.value }))} />
              </Field>
              <Field label="Energy B">
                <Input value={anchorB.energy} onChange={(event) => setAnchorB((current) => ({ ...current, energy: event.target.value }))} />
              </Field>
            </div>
            <Button type="button" variant="outline" size="sm" onClick={applyAnchors}>
              Apply two-point calibration
            </Button>
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium">Fit</h2>
            <div className="grid grid-cols-2 gap-2">
              <Field label="From (keV)">
                <Input type="number" step="0.1" value={emin} onChange={(event) => setEmin(Number(event.target.value))} />
              </Field>
              <Field label="To (keV)">
                <Input type="number" step="0.1" value={emax} onChange={(event) => setEmax(Number(event.target.value))} />
              </Field>
              <Field label="FWHM at Mn (eV)">
                <Input type="number" step="1" value={fwhm} onChange={(event) => setFwhm(Number(event.target.value))} />
              </Field>
              <Field label="Background width">
                <Input type="number" step="1" min={0} value={snip} onChange={(event) => setSnip(Number(event.target.value))} />
              </Field>
              <Field label="Excitation (keV)">
                <Input type="number" step="0.1" value={excitation} onChange={(event) => setExcitation(Number(event.target.value))} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={escapePeaks} onCheckedChange={(checked) => setEscapePeaks(Boolean(checked))} />
              Include Si escape peaks
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={logScale} onCheckedChange={(checked) => setLogScale(Boolean(checked))} />
              Log counts
            </label>
            <p className="text-xs text-muted-foreground">
              Fit applies these lines to every spectrum in this session. Batch is the separate application that runs a saved configuration over its own file list.
            </p>
            <div className="flex gap-2">
              <Button type="button" onClick={() => runFit()}>
                Fit
              </Button>
              <Button type="button" variant="outline" onClick={suggest}>
                Suggest lines
              </Button>
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">Lines</h2>
              <span className="text-xs text-muted-foreground">{lineKeys.length} selected</span>
            </div>
            <Input
              placeholder="Filter, for example Fe or Pb"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <div className="max-h-64 overflow-auto rounded-lg border border-border">
              <ul className="divide-y divide-border">
                {visibleLines.map((line) => {
                  const key = lineKey(line);
                  const checked = lineKeys.includes(key);
                  return (
                    <li key={key}>
                      <label className="flex cursor-pointer items-center justify-between gap-3 px-2.5 py-1.5 text-sm">
                        <span className="inline-flex items-center gap-2">
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(next) => {
                              setLineKeys((current) =>
                                next ? [...current, key] : current.filter((item) => item !== key),
                              );
                            }}
                          />
                          {key}
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">{line.energy.toFixed(3)}</span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          </section>

          {active?.role === "standard" ? (
            <section className="flex flex-col gap-3">
              <h2 className="text-sm font-medium">Known concentrations</h2>
              <p className="text-xs text-muted-foreground">
                Used for the calibration curve. Units are whatever the template expects.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {elements.map((element) => {
                  const draftKey = `${active.id}:${element}`;
                  return (
                    <Field key={element} label={element}>
                      <Input
                        inputMode="decimal"
                        value={drafts[draftKey] ?? (active.known[element]?.toString() ?? "")}
                        onChange={(event) => {
                          const raw = event.target.value;
                          setDrafts((current) => ({ ...current, [draftKey]: raw }));
                          if (raw.trim() !== "" && !Number.isFinite(Number(raw))) return;
                          setSpectra((current) =>
                            current.map((spectrum) => {
                              if (spectrum.id !== active.id) return spectrum;
                              const known = { ...spectrum.known };
                              if (raw.trim() === "") delete known[element];
                              else known[element] = Number(raw);
                              return { ...spectrum, known };
                            }),
                          );
                        }}
                      />
                    </Field>
                  );
                })}
              </div>
            </section>
          ) : null}
        </aside>

        <main className="flex min-w-0 flex-col gap-4 px-4 py-5 md:px-6">
          {error ? (
            <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <section className="overflow-hidden rounded-xl border border-border bg-[#121612]">
            <SpectrumPlot
              counts={active?.counts ?? null}
              calibration={calibration}
              model={activeFit?.model}
              background={activeFit?.background}
              peaks={shownPeaks}
              logScale={logScale}
            />
          </section>
          {activeFit ? (
            <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              <Metric label="Chi-square" value={activeFit.chi2.toFixed(1)} />
              <Metric label="Reduced chi-square" value={activeFit.reducedChi2.toFixed(3)} />
              <Metric label="Channels" value={String(activeFit.channelsUsed)} />
              <Metric label="Lines with area" value={String(shownPeaks.length)} />
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">
              Fit the loaded spectra to see areas, a calibration curve, and the Excel export.
            </p>
          )}
          {activeFit?.warnings.length ? (
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {activeFit.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}

          <Tabs defaultValue="results">
            <TabsList>
              <TabsTrigger value="results">Results</TabsTrigger>
              <TabsTrigger value="curve">Calibration curve</TabsTrigger>
              <TabsTrigger value="excel">Excel template</TabsTrigger>
            </TabsList>
            <TabsContent value="results" className="pt-4">
              {!activeFit || shownPeaks.length === 0 ? (
                <p className="text-sm text-muted-foreground">No peak areas yet for this spectrum.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-left text-sm">
                    <thead className="text-xs text-muted-foreground">
                      <tr>
                        {["Line", "Energy (keV)", "Area", "FWHM (eV)", "cps", "Concentration"].map((heading) => (
                          <th key={heading} className="py-2 font-medium">{heading}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {shownPeaks.map((peak) => {
                        const curve = curves.find((item) => item.element === peak.element);
                        const primary = primaryLineKey(activeFit, peak.element) === peak.key;
                        const concentration = primary ? predictConcentration(curve, peak.area) : null;
                        return (
                          <tr key={peak.key} className="border-t border-border">
                            <td className="py-2 font-medium">{peak.key}</td>
                            <td className="py-2 font-mono">{peak.energy.toFixed(3)}</td>
                            <td className="py-2 font-mono">{peak.area.toFixed(1)}</td>
                            <td className="py-2 font-mono">{peak.fwhmEv.toFixed(1)}</td>
                            <td className="py-2 font-mono">{peak.cps === null ? "—" : peak.cps.toFixed(2)}</td>
                            <td className="py-2 font-mono">
                              {concentration === null ? "—" : concentration.toFixed(1)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </TabsContent>
            <TabsContent value="curve" className="pt-4">
              {curves.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Mark at least one spectrum as a standard and enter a concentration for an element that was fitted.
                  Two standards give a slope, an intercept, and an R². One standard is forced through the origin.
                </p>
              ) : (
                <div className="flex flex-col gap-4">
                  {curves.map((curve) => (
                    <article key={curve.element} className="rounded-xl border border-border p-3">
                      <h3 className="text-sm font-medium">
                        {curve.element}{" "}
                        <span className="font-normal text-muted-foreground">from {curve.lineKey}</span>
                      </h3>
                      <p className="mt-1 font-mono text-xs text-muted-foreground">
                        concentration = {curve.intercept.toFixed(3)} + {curve.slope.toExponential(3)} × area
                        {curve.r2 === null ? " · one point, intercept fixed at 0" : ` · R² ${curve.r2.toFixed(4)}`}
                      </p>
                      <ul className="mt-2 text-sm">
                        {curve.points.map((point) => (
                          <li key={point.sample} className="flex justify-between gap-4 border-t border-border py-1">
                            <span>{point.sample}</span>
                            <span className="font-mono text-xs">
                              area {point.area.toFixed(0)} → {point.concentration}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </article>
                  ))}
                </div>
              )}
            </TabsContent>
            <TabsContent value="excel" className="pt-4">
              <ExcelMapper lineKeys={lineKeys} recordsLong={recordsLong} recordsWide={recordsWide} />
            </TabsContent>
          </Tabs>
        </main>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-sm">{value}</dd>
    </div>
  );
}
