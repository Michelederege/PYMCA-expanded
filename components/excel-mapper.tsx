"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
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
import { buildPracticeWorkbook } from "@/lib/excel/sample";
import {
  autoBindings,
  fieldLabel,
  fieldOptions,
  guessHeaderRow,
  headersFromRow,
  reconcileBindings,
  type Layout,
  type MappingProfile,
} from "@/lib/excel/mapping";
import { fillWorkbook, inspectWorkbook, type WorkbookPreview } from "@/lib/excel/ooxml";
import type { ExportRecord } from "@/lib/xrf/export-rows";

const STORAGE_KEY = "xrf-curve-fit-profile";

type Props = {
  lineKeys: string[];
  recordsLong: ExportRecord[];
  recordsWide: ExportRecord[];
};

export function ExcelMapper({ lineKeys, recordsLong, recordsWide }: Props) {
  const [preview, setPreview] = useState<WorkbookPreview | null>(null);
  const [fileName, setFileName] = useState("");
  const [buffer, setBuffer] = useState<ArrayBuffer | null>(null);
  const [profile, setProfile] = useState<MappingProfile | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sheet = preview?.sheets.find((item) => item.name === profile?.sheet) ?? preview?.sheets[0];
  const headerCells = sheet && profile ? sheet.rows[profile.headerRow - 1] : undefined;
  const options = fieldOptions(profile?.layout ?? "long", lineKeys);
  const records = profile?.layout === "wide" ? recordsWide : recordsLong;

  const recognized = useMemo(
    () => (profile ? profile.bindings.filter((binding) => binding.field !== "ignore").length : 0),
    [profile],
  );

  useEffect(() => {
    if (!profile) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
  }, [profile]);

  async function openBuffer(data: ArrayBuffer, name: string, maxRow = 40) {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const nextPreview = await inspectWorkbook(data, maxRow, 24);
      if (nextPreview.sheets.length === 0) throw new Error("No worksheets were found in that file.");
      const saved = readSavedProfile();
      const preferred =
        (saved && nextPreview.sheets.find((item) => item.name === saved.sheet)) ||
        bestSheet(nextPreview);
      const headerRow = saved && saved.sheet === preferred.name ? saved.headerRow : guessHeaderRow(preferred.rows);
      const row = preferred.rows[headerRow - 1];
      const layout = saved && saved.sheet === preferred.name ? saved.layout : guessLayout(preferred.name, row);
      const reconciled =
        saved && saved.sheet === preferred.name
          ? reconcileBindings(saved.bindings, row, layout, lineKeys)
          : { bindings: autoBindings(row, layout, lineKeys), notes: [] };
      setBuffer(data);
      setPreview(nextPreview);
      setFileName(name);
      setNotes(reconciled.notes);
      setProfile({
        version: 1,
        sheet: preferred.name,
        headerRow,
        firstDataRow: saved && saved.sheet === preferred.name ? saved.firstDataRow : headerRow + 1,
        layout,
        clearExtras: saved?.clearExtras ?? true,
        bindings: reconciled.bindings,
      });
      setStatus(
        nextPreview.hasMacros
          ? "Macros detected. They are copied through and not edited."
          : "Workbook loaded. Map columns, then download the filled copy.",
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not read that workbook.");
    } finally {
      setBusy(false);
    }
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    const data = await file.arrayBuffer();
    await openBuffer(data, file.name);
  }

  function updateProfile(patch: Partial<MappingProfile>, rebind = false) {
    setProfile((current) => {
      if (!current || !preview) return current;
      const next = { ...current, ...patch };
      const currentSheet = preview.sheets.find((item) => item.name === next.sheet);
      if (!currentSheet) return next;
      if (rebind) {
        const row = currentSheet.rows[next.headerRow - 1];
        const reconciled = reconcileBindings(current.bindings, row, next.layout, lineKeys);
        next.bindings = patch.layout && patch.layout !== current.layout
          ? autoBindings(row, next.layout, lineKeys)
          : reconciled.bindings;
        setNotes(reconciled.notes);
      }
      return next;
    });
  }

  async function changeHeaderRow(value: number) {
    if (!buffer || !profile) return;
    let currentPreview = preview;
    if (value > (sheet?.rows.length ?? 0)) {
      const nextPreview = await inspectWorkbook(buffer, Math.max(value + 5, 40), 24);
      setPreview(nextPreview);
      currentPreview = nextPreview;
    }
    const currentSheet = currentPreview?.sheets.find((item) => item.name === profile.sheet);
    const row = currentSheet?.rows[value - 1];
    const reconciled = reconcileBindings(profile.bindings, row, profile.layout, lineKeys);
    setNotes(reconciled.notes);
    setProfile({
      ...profile,
      headerRow: value,
      firstDataRow: Math.max(profile.firstDataRow, value + 1),
      bindings: reconciled.bindings,
    });
  }

  async function writeFile() {
    if (!buffer || !profile) return;
    if (records.length === 0) {
      setError("Fit at least one spectrum before writing the workbook.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await fillWorkbook(buffer, {
        sheet: profile.sheet,
        headerRow: profile.headerRow,
        firstDataRow: profile.firstDataRow,
        bindings: profile.bindings,
        records,
        clearExtras: profile.clearExtras,
      });
      downloadBytes(result.bytes, filledName(fileName));
      const warning = result.warnings.length ? ` ${result.warnings[0]}` : "";
      setStatus(
        `Wrote ${result.rowsWritten} row${result.rowsWritten === 1 ? "" : "s"}` +
          (result.cellsSkipped ? `, left ${result.cellsSkipped} formula cell${result.cellsSkipped === 1 ? "" : "s"} untouched` : "") +
          (result.cellsCleared ? `, cleared ${result.cellsCleared} stale cell${result.cellsCleared === 1 ? "" : "s"}` : "") +
          `.${warning}`,
      );
      setNotes(result.warnings);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not write the workbook.");
    } finally {
      setBusy(false);
    }
  }

  async function loadPractice() {
    const bytes = await buildPracticeWorkbook();
    const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
    await openBuffer(copy, "practice-curve-fit.xlsx");
  }

  function downloadProfile() {
    if (!profile) return;
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "curve-fit-mapping.json";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function importProfile(file: File | undefined) {
    if (!file || !preview || !profile) return;
    try {
      const parsed = JSON.parse(await file.text()) as MappingProfile;
      if (parsed.version !== 1 || !parsed.sheet) throw new Error("That mapping file is not from this app.");
      const target = preview.sheets.find((item) => item.name === parsed.sheet) ?? sheet;
      if (!target) throw new Error("Load a workbook before a mapping file.");
      const row = target.rows[(parsed.headerRow ?? profile.headerRow) - 1];
      const reconciled = reconcileBindings(parsed.bindings ?? [], row, parsed.layout ?? profile.layout, lineKeys);
      setNotes(reconciled.notes);
      setProfile({
        ...parsed,
        sheet: target.name,
        bindings: reconciled.bindings,
      });
      setStatus(`Loaded mapping for “${target.name}”.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not read that mapping file.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 rounded-xl border border-dashed border-border bg-background/40 p-4 md:flex-row md:items-center md:justify-between">
        <div className="max-w-xl">
          <p className="text-sm font-medium">Workbook</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Drop in the curve-fit .xlsm, even if it is larger than 50 MB or the sheets have been renamed.
            It stays in this browser. Pick the header row, match columns, and download a filled copy.
            Formulas are skipped. Macros are copied unchanged.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={() => void loadPractice()} disabled={busy}>
            Practice template
          </Button>
          <label className={buttonVariants({ variant: "outline" }) + " cursor-pointer"}>
            Choose workbook
            <input
              className="sr-only"
              type="file"
              accept=".xlsx,.xlsm,application/vnd.ms-excel.sheet.macroEnabled.12,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(event) => {
                void onFile(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
        </div>
      </div>

      {error ? (
        <p className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {status ? <p className="text-sm text-muted-foreground">{status}</p> : null}

      {preview && profile && sheet ? (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{fileName}</span>
            <Badge variant="outline">{formatBytes(preview.bytes)}</Badge>
            {preview.hasMacros ? <Badge variant="secondary">Macros kept</Badge> : null}
            <Badge variant="outline">
              {recognized} mapped column{recognized === 1 ? "" : "s"}
            </Badge>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Sheet">
              <Select
                value={profile.sheet}
                onValueChange={(value) => {
                  if (!value) return;
                  const nextSheet = preview.sheets.find((item) => item.name === value);
                  const headerRow = guessHeaderRow(nextSheet?.rows ?? []);
                  updateProfile(
                    {
                      sheet: value,
                      headerRow,
                      firstDataRow: headerRow + 1,
                      layout: guessLayout(value, nextSheet?.rows[headerRow - 1]),
                    },
                    true,
                  );
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {preview.sheets.map((item) => (
                    <SelectItem key={item.name} value={item.name}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Header row">
              <Input
                type="number"
                min={1}
                value={profile.headerRow}
                onChange={(event) => void changeHeaderRow(Number(event.target.value) || 1)}
              />
            </Field>
            <Field label="First data row">
              <Input
                type="number"
                min={profile.headerRow + 1}
                value={profile.firstDataRow}
                onChange={(event) =>
                  updateProfile({ firstDataRow: Number(event.target.value) || profile.headerRow + 1 })
                }
              />
            </Field>
            <Field label="Layout">
              <Select
                value={profile.layout}
                onValueChange={(value) => {
                  if (value === "long" || value === "wide") updateProfile({ layout: value }, true);
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="long">One row per peak</SelectItem>
                  <SelectItem value="wide">One row per sample</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={profile.clearExtras}
              onCheckedChange={(checked) => updateProfile({ clearExtras: Boolean(checked) })}
            />
            Clear leftover values in mapped columns under the new rows
          </label>

          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[640px] text-left text-xs">
              <tbody>
                {sheet.rows.slice(0, 8).map((row, index) => (
                  <tr
                    key={index}
                    className={index + 1 === profile.headerRow ? "bg-primary/15" : "odd:bg-background/40"}
                  >
                    <th className="px-2 py-1 font-mono text-muted-foreground">{index + 1}</th>
                    {row.slice(0, 10).map((cell, column) => (
                      <td key={column} className="max-w-40 truncate px-2 py-1 font-mono">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">Highlighted row is the header. The preview shows the first rows only.</p>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 font-medium">Column</th>
                  <th className="py-1 font-medium">Header in the file</th>
                  <th className="py-1 font-medium">Write this</th>
                </tr>
              </thead>
              <tbody>
                {profile.bindings.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="py-3 text-muted-foreground">
                      No headers on row {profile.headerRow}. Change the header row if the titles moved.
                    </td>
                  </tr>
                ) : (
                  profile.bindings.map((binding) => (
                    <tr key={`${binding.column}-${binding.header}`} className="border-t border-border">
                      <td className="py-2 font-mono text-xs">{columnLetter(binding.column)}</td>
                      <td className="py-2">{binding.header}</td>
                      <td className="py-2">
                        <Select
                          value={binding.field}
                          onValueChange={(value) => {
                            if (!value) return;
                            setProfile((current) =>
                              current
                                ? {
                                    ...current,
                                    bindings: current.bindings.map((item) =>
                                      item.column === binding.column ? { ...item, field: value } : item,
                                    ),
                                  }
                                : current,
                            );
                          }}
                        >
                          <SelectTrigger className="w-full max-w-xs">
                            <SelectValue>{fieldLabel(binding.field)}</SelectValue>
                          </SelectTrigger>
                          <SelectContent>
                            {options.some((option) => option.id === binding.field) ? null : (
                              <SelectItem value={binding.field}>{fieldLabel(binding.field)}</SelectItem>
                            )}
                            {options.map((option) => (
                              <SelectItem key={option.id} value={option.id}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {notes.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {notes.slice(0, 6).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button type="button" onClick={() => void writeFile()} disabled={busy || records.length === 0}>
              Download filled workbook
            </Button>
            <Button type="button" variant="outline" onClick={downloadProfile}>
              Save mapping
            </Button>
            <label className={buttonVariants({ variant: "outline" }) + " cursor-pointer"}>
              Load mapping
              <input
                className="sr-only"
                type="file"
                accept="application/json,.json"
                onChange={(event) => {
                  void importProfile(event.target.files?.[0]);
                  event.target.value = "";
                }}
              />
            </label>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                const bytes = buffer;
                if (!bytes) return;
                const copy = bytes.slice(0);
                void openBuffer(copy, fileName);
              }}
            >
              Rematch headers
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            {records.length} result row{records.length === 1 ? "" : "s"} ready
            {profile.layout === "wide" ? " (one per spectrum)" : " (one per fitted line)"}.{" "}
            {headersFromRow(headerCells).length} headers on this row.
          </p>
        </>
      ) : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function bestSheet(preview: WorkbookPreview) {
  return preview.sheets.reduce((best, sheet) =>
    guessHeaderRow(sheet.rows) >= 1 && headersFromRow(sheet.rows[guessHeaderRow(sheet.rows) - 1]).length >
      headersFromRow(best.rows[guessHeaderRow(best.rows) - 1] ?? []).length
      ? sheet
      : best,
  );
}

function guessLayout(name: string, row: string[] | undefined): Layout {
  if (/wide|summary|sample/i.test(name) && !/result/i.test(name)) return "wide";
  const headers = headersFromRow(row).map((header) => header.header.toLowerCase());
  if (headers.includes("element") || headers.includes("line")) return "long";
  return "wide";
}

function readSavedProfile(): MappingProfile | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MappingProfile;
    if (parsed.version !== 1 || !parsed.sheet) return null;
    return parsed;
  } catch {
    return null;
  }
}

function filledName(name: string): string {
  const dot = name.lastIndexOf(".");
  if (dot <= 0) return `${name}-filled.xlsx`;
  return `${name.slice(0, dot)}-filled${name.slice(dot)}`;
}

function downloadBytes(bytes: Uint8Array, name: string) {
  const copy = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  const blob = new Blob([copy], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function columnLetter(index: number): string {
  let n = index + 1;
  let out = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    out = String.fromCharCode(65 + rem) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}
