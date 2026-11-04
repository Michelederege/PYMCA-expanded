"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { BatchTable } from "@/components/batch-table";
import { ExcelMapper } from "@/components/excel-mapper";
import { SpectrumPlot } from "@/components/spectrum-plot";
import { Button, buttonVariants } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { buildBatchTable, fitSpectra } from "@/lib/xrf/batch";
import {
  HANDOFF_KEY,
  bronzeConfiguration,
  curvesFromConfiguration,
  parseConfiguration,
  serializeConfiguration,
  toFitConfig,
  type FitConfiguration,
} from "@/lib/xrf/config";
import { demoSpectra } from "@/lib/xrf/demo";
import { buildExportRecords, recordsToCsv } from "@/lib/xrf/export-rows";
import { significantPeaks } from "@/lib/xrf/fit";
import { parseSpectraText } from "@/lib/xrf/spectrum";
import type { FitResult, Spectrum } from "@/lib/xrf/types";

type OutputMode = "download" | "folder";

type DirectoryHandle = {
  name: string;
  getFileHandle: (
    name: string,
    options: { create: boolean },
  ) => Promise<{ createWritable: () => Promise<{ write: (data: string) => Promise<void>; close: () => Promise<void> }> }>;
};

export function BatchApp() {
  const [spectra, setSpectra] = useState<Spectrum[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [configuration, setConfiguration] = useState<FitConfiguration | null>(null);
  const [fits, setFits] = useState<Record<string, FitResult>>({});
  const [logScale, setLogScale] = useState(false);
  const [outputMode, setOutputMode] = useState<OutputMode>("download");
  const [folderName, setFolderName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>(["Add scans, open a fit configuration, then start."]);
  const [running, setRunning] = useState(false);
  const folderRef = useRef<DirectoryHandle | null>(null);

  const active = spectra.find((spectrum) => spectrum.id === activeId) ?? null;
  const activeFit = active ? fits[active.id] : undefined;
  const curves = useMemo(
    () => (configuration ? curvesFromConfiguration(configuration) : []),
    [configuration],
  );
  const recordsWide = useMemo(
    () => buildExportRecords(spectra, fits, curves, "wide"),
    [spectra, fits, curves],
  );
  const recordsLong = useMemo(
    () => buildExportRecords(spectra, fits, curves, "long"),
    [spectra, fits, curves],
  );

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (!params.has("handoff")) return;
    const raw = window.localStorage.getItem(HANDOFF_KEY);
    if (!raw) return;
    try {
      const next = parseConfiguration(raw);
      setConfiguration(next);
      setLog([`Loaded “${next.name}” from Fit. Add the scans to run, then start.`]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Fit handed over a configuration Batch could not read.");
    }
  }, []);

  function loadConfigurationText(text: string, source: string) {
    const next = parseConfiguration(text);
    setConfiguration(next);
    setFits({});
    setError(null);
    setLog([`Opened configuration “${next.name}” from ${source}.`]);
  }

  function loadBronze() {
    const next = bronzeConfiguration();
    const scans = demoSpectra();
    setConfiguration(next);
    setSpectra(scans);
    setActiveId(scans[2]?.id ?? scans[0]?.id ?? null);
    setFits({});
    setError(null);
    setLog([
      "Opened the bronze example.",
      "The file list is the three demo scans. The configuration already holds their calibration curves.",
      "Start runs every scan in the list.",
    ]);
  }

  async function onConfigurationFile(file: File | undefined) {
    if (!file) return;
    try {
      loadConfigurationText(await file.text(), file.name);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open that configuration.");
    }
  }

  function saveConfiguration() {
    if (!configuration) {
      setError("Open a configuration before saving one.");
      return;
    }
    download(`${configuration.name}.json`, serializeConfiguration(configuration), "application/json");
  }

  async function onSpectrumFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const incoming: Spectrum[] = [];
    const problems: string[] = [];
    let sequence = 0;
    for (const file of files) {
      try {
        incoming.push(
          ...parseSpectraText(await file.text(), file.name, () => {
            sequence += 1;
            return `batch-${Date.now()}-${sequence}-${Math.random().toString(36).slice(2, 6)}`;
          }),
        );
      } catch (caught) {
        problems.push(caught instanceof Error ? caught.message : `Could not read ${file.name}.`);
      }
    }
    if (incoming.length > 0) {
      setSpectra((current) => [...current, ...incoming]);
      setActiveId(incoming[incoming.length - 1].id);
      setError(problems.length > 0 ? problems.join(" ") : null);
      setLog((current) => [...current, `Added ${incoming.length} scan${incoming.length === 1 ? "" : "s"} to the file list.`]);
    } else if (problems.length > 0) {
      setError(problems.join(" "));
    }
  }

  function removeActive() {
    if (!active) return;
    const remaining = spectra.filter((spectrum) => spectrum.id !== active.id);
    setSpectra(remaining);
    setActiveId(remaining[0]?.id ?? null);
    setFits((current) => {
      const next = { ...current };
      delete next[active.id];
      return next;
    });
  }

  function moveActive(direction: -1 | 1) {
    if (!active) return;
    const index = spectra.findIndex((spectrum) => spectrum.id === active.id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= spectra.length) return;
    const next = spectra.slice();
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    setSpectra(next);
  }

  async function chooseFolder() {
    const picker = (window as unknown as { showDirectoryPicker?: () => Promise<DirectoryHandle> }).showDirectoryPicker;
    if (!picker) {
      setError("This browser cannot write a folder. Batch will download the CSV instead.");
      setOutputMode("download");
      return;
    }
    try {
      const handle = await picker();
      folderRef.current = handle;
      setFolderName(handle.name);
      setOutputMode("folder");
      setError(null);
    } catch {
      // The picker was dismissed.
    }
  }

  async function start() {
    setError(null);
    if (!configuration) {
      setError("Open a fit configuration first. Fit can hand one over, or open the bronze example.");
      return;
    }
    if (spectra.length === 0) {
      setError("Add at least one scan to the file list.");
      return;
    }
    if (outputMode === "folder" && !folderRef.current) {
      setError("Choose an output folder, or download the CSV instead.");
      return;
    }
    setRunning(true);
    try {
      const nextFits = fitSpectra(spectra, toFitConfig(configuration));
      setFits(nextFits);
      const table = buildBatchTable(spectra, nextFits, curvesFromConfiguration(configuration));
      const csv = recordsToCsv(buildExportRecords(spectra, nextFits, curvesFromConfiguration(configuration), "wide"));
      const fileName = `${configuration.name.replace(/[^\w.-]+/g, "-").toLowerCase() || "batch"}-results.csv`;
      if (outputMode === "folder" && folderRef.current) {
        await writeTextFile(folderRef.current, fileName, csv);
        setLog([
          `Started ${spectra.length} scan${spectra.length === 1 ? "" : "s"} with “${configuration.name}”.`,
          ...table.rows.map((row) => `${row.name}: reduced chi-square ${row.reducedChi2.toFixed(2)}`),
          `Wrote ${fileName} in ${folderRef.current.name}.`,
        ]);
      } else {
        download(fileName, csv, "text/csv");
        setLog([
          `Started ${spectra.length} scan${spectra.length === 1 ? "" : "s"} with “${configuration.name}”.`,
          ...table.rows.map((row) => `${row.name}: reduced chi-square ${row.reducedChi2.toFixed(2)}`),
          `Downloaded ${fileName}.`,
        ]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The batch run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between gap-3 border-b border-border px-3">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold">Batch</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">One configuration, every scan in the list</span>
        </div>
        <nav className="flex items-center gap-1">
          <Link className={buttonVariants({ variant: "ghost", size: "sm" })} href="/">Fit</Link>
          <Button type="button" variant="ghost" size="sm" onClick={loadBronze}>Bronze example</Button>
          <Button type="button" variant="outline" size="sm" onClick={saveConfiguration}>Save configuration</Button>
          <Button type="button" size="sm" disabled={running} onClick={() => void start()}>
            {running ? "Running…" : "Start"}
          </Button>
        </nav>
      </header>

      {error ? (
        <p className="border-b border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
      ) : null}

      <div className="grid flex-1 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="flex flex-col gap-3 border-b border-border px-3 py-4 lg:border-r lg:border-b-0">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium">Input file list</h2>
            <span className="text-xs text-muted-foreground">{spectra.length}</span>
          </div>
          <label className={buttonVariants({ variant: "secondary", size: "sm" }) + " cursor-pointer"}>
            Add scans
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
            The list is the run. Order is kept. Remove a scan to leave it out.
          </p>
          {spectra.length === 0 ? (
            <p className="text-sm text-muted-foreground">No scans yet.</p>
          ) : (
            <ul className="flex max-h-80 flex-col gap-2 overflow-auto">
              {spectra.map((spectrum, index) => (
                <li key={spectrum.id}>
                  <button
                    type="button"
                    onClick={() => setActiveId(spectrum.id)}
                    className={`w-full rounded-lg border px-2.5 py-2 text-left ${
                      spectrum.id === activeId ? "border-primary bg-primary/10" : "border-border"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{index + 1}. {spectrum.name}</span>
                      {fits[spectrum.id] ? <span className="text-xs text-muted-foreground">fitted</span> : null}
                    </span>
                    <span className="mt-1 block text-xs text-muted-foreground">{spectrum.counts.length} channels</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => moveActive(-1)} disabled={!active}>Up</Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => moveActive(1)} disabled={!active}>Down</Button>
            <Button type="button" variant="ghost" size="sm" onClick={removeActive} disabled={!active}>Remove</Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                setSpectra([]);
                setActiveId(null);
                setFits({});
              }}
              disabled={spectra.length === 0}
            >
              Remove all
            </Button>
          </div>
        </aside>

        <main className="flex min-w-0 flex-col gap-4 px-4 py-4 md:px-6">
          <section className="grid gap-3 rounded-xl border border-border p-3 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">Fit configuration</h2>
              {configuration ? (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  <dt className="text-muted-foreground">Name</dt>
                  <dd>{configuration.name}</dd>
                  <dt className="text-muted-foreground">Calibration</dt>
                  <dd className="font-mono text-xs">{configuration.calibration.zero} + {configuration.calibration.gain} × channel</dd>
                  <dt className="text-muted-foreground">Window</dt>
                  <dd className="font-mono text-xs">{configuration.emin}–{configuration.emax} keV</dd>
                  <dt className="text-muted-foreground">Lines</dt>
                  <dd>{configuration.lineKeys.length}</dd>
                  <dt className="text-muted-foreground">Curves</dt>
                  <dd>{configuration.curves.length === 0 ? "Areas only" : configuration.curves.map((curve) => curve.element).join(", ")}</dd>
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No configuration yet. Save one from Fit and open it here, or use the bronze example.
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <label className={buttonVariants({ variant: "outline", size: "sm" }) + " cursor-pointer"}>
                  Open configuration
                  <input
                    className="sr-only"
                    type="file"
                    accept=".json,application/json"
                    onChange={(event) => {
                      void onConfigurationFile(event.target.files?.[0]);
                      event.target.value = "";
                    }}
                  />
                </label>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">Output</h2>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="output"
                  checked={outputMode === "download"}
                  onChange={() => setOutputMode("download")}
                />
                Download a CSV
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="output"
                  checked={outputMode === "folder"}
                  onChange={() => setOutputMode("folder")}
                />
                Write into a folder{folderName ? `: ${folderName}` : ""}
              </label>
              <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => void chooseFolder()}>
                Choose folder
              </Button>
              <label className="flex items-center gap-2 text-sm">
                <Checkbox checked={logScale} onCheckedChange={(checked) => setLogScale(Boolean(checked))} />
                Log counts
              </label>
            </div>
          </section>

          <section className="overflow-hidden rounded-xl border border-border bg-[#121612]">
            <SpectrumPlot
              counts={active?.counts ?? null}
              calibration={configuration?.calibration ?? { zero: 0, gain: 0.01 }}
              model={activeFit?.model}
              background={activeFit?.background}
              peaks={activeFit ? significantPeaks(activeFit.peaks) : []}
              logScale={logScale}
            />
          </section>

          <section className="rounded-xl border border-border p-3">
            <h2 className="text-sm font-medium">Log</h2>
            <ul className="mt-2 text-sm text-muted-foreground">
              {log.map((line, index) => (
                <li key={`${index}-${line}`}>{line}</li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="mb-2 text-sm font-medium">Results</h2>
            <BatchTable
              spectra={spectra}
              fits={fits}
              curves={curves}
              activeId={activeId}
              onSelect={setActiveId}
            />
          </section>

          <section className="pb-6">
            <h2 className="mb-2 text-sm font-medium">Excel template</h2>
            <ExcelMapper
              lineKeys={configuration?.lineKeys ?? []}
              recordsLong={recordsLong}
              recordsWide={recordsWide}
            />
          </section>
        </main>
      </div>
    </div>
  );
}

function download(name: string, contents: string, type: string) {
  const blob = new Blob([contents], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

async function writeTextFile(directory: DirectoryHandle, name: string, contents: string) {
  const handle = await directory.getFileHandle(name, { create: true });
  const writable = await handle.createWritable();
  await writable.write(contents);
  await writable.close();
}
