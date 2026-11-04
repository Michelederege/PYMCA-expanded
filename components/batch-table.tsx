"use client";

import { Badge } from "@/components/ui/badge";
import { buildBatchTable } from "@/lib/xrf/batch";
import type { CalibrationCurve, FitResult, Spectrum } from "@/lib/xrf/types";

export function BatchTable({
  spectra,
  fits,
  curves,
  activeId,
  onSelect,
}: {
  spectra: Spectrum[];
  fits: Record<string, FitResult>;
  curves: CalibrationCurve[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  const table = buildBatchTable(spectra, fits, curves);
  if (table.rows.length === 0) {
    return <p className="text-sm text-muted-foreground">Run the checked scans to fill this table.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr>
              <th className="py-2 pr-3 font-medium">Scan</th>
              <th className="py-2 pr-3 font-medium">Reduced chi-square</th>
              {table.elements.map((element) => (
                <th key={element} className="py-2 pr-3 font-medium">
                  {element}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row) => (
              <tr
                key={row.id}
                className={`cursor-pointer border-t border-border ${row.id === activeId ? "bg-primary/10" : "hover:bg-muted/40"}`}
                onClick={() => onSelect(row.id)}
              >
                <td className="py-2 pr-3" title={row.warnings.join("\n")}>
                  <span className="font-medium">{row.name}</span>
                  <Badge variant="outline" className="ml-2">
                    {row.role === "standard" ? "Standard" : "Unknown"}
                  </Badge>
                </td>
                <td className="py-2 pr-3 font-mono">{row.reducedChi2.toFixed(2)}</td>
                {table.elements.map((element) => {
                  const cell = row.cells[element];
                  if (!cell) return <td key={element} className="py-2 pr-3 text-muted-foreground">—</td>;
                  return (
                    <td key={element} className="py-2 pr-3 font-mono">
                      <span className="block">{cell.area.toFixed(0)}</span>
                      <span className="block text-xs text-muted-foreground">
                        {cell.lineKey}
                        {cell.concentration === null ? "" : ` · ${cell.concentration.toFixed(1)}`}
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Each cell is the primary-line area. The second number is the concentration from the calibration curves in the configuration. Select a row to open that scan.
      </p>
    </div>
  );
}
