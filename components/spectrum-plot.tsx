"use client";

import { useEffect, useRef, useState } from "react";
import type { Calibration } from "@/lib/xrf/types";

type PeakMark = { energy: number; key: string };

type Props = {
  counts: Float64Array | null;
  calibration: Calibration;
  model?: Float64Array | null;
  background?: Float64Array | null;
  peaks?: PeakMark[];
  logScale: boolean;
};

type Readout = { energy: number; counts: number; model: number | null };

const PAD = { left: 56, right: 16, top: 16, bottom: 32 };

export function SpectrumPlot({
  counts,
  calibration,
  model,
  background,
  peaks = [],
  logScale,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [readout, setReadout] = useState<Readout | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;

    const draw = () => {
      const rect = wrap.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(320, rect.width);
      const height = Math.max(280, rect.height);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      paint(ctx, width, height, {
        counts,
        calibration,
        model: model ?? null,
        background: background ?? null,
        peaks,
        logScale,
      });
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [counts, calibration, model, background, peaks, logScale]);

  function onMove(event: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas || !counts) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const plotWidth = rect.width - PAD.left - PAD.right;
    const fraction = (x - PAD.left) / plotWidth;
    if (fraction < 0 || fraction > 1) {
      setReadout(null);
      return;
    }
    const channel = Math.round(fraction * (counts.length - 1));
    const energy = calibration.zero + calibration.gain * channel;
    setReadout({
      energy,
      counts: counts[channel] ?? 0,
      model: model ? (model[channel] ?? null) : null,
    });
  }

  return (
    <div ref={wrapRef} className="relative h-[320px] w-full lg:h-[460px]">
      <canvas
        ref={canvasRef}
        className="block h-full w-full"
        onMouseMove={onMove}
        onMouseLeave={() => setReadout(null)}
      />
      <div className="pointer-events-none absolute top-3 right-3 flex gap-3 text-[11px] text-[#d9d3c3]">
        <Legend swatch="#f4f0e6" label="Counts" />
        <Legend swatch="#e0a45a" label="Background" />
        <Legend swatch="#8dceab" label="Fit" />
      </div>
      {readout ? (
        <div className="pointer-events-none absolute bottom-10 left-16 rounded-md bg-[#10140f]/90 px-2 py-1 font-mono text-[11px] text-[#f4f0e6] ring-1 ring-white/10">
          {readout.energy.toFixed(3)} keV · {Math.round(readout.counts)} counts
          {readout.model !== null ? ` · fit ${Math.round(readout.model)}` : ""}
        </div>
      ) : null}
      {!counts ? (
        <div className="absolute inset-0 flex items-center justify-center px-8 text-center text-sm text-muted-foreground">
          Load a spectrum, or open the bronze demo, to see counts against energy.
        </div>
      ) : null}
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-0.5 w-4 rounded" style={{ background: swatch }} />
      {label}
    </span>
  );
}

function paint(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  view: {
    counts: Float64Array | null;
    calibration: Calibration;
    model: Float64Array | null;
    background: Float64Array | null;
    peaks: PeakMark[];
    logScale: boolean;
  },
) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#121612";
  ctx.fillRect(0, 0, width, height);

  const residualH = Math.round(height * 0.22);
  const plotBottom = height - PAD.bottom - residualH - 10;
  const plotTop = PAD.top;
  const plotLeft = PAD.left;
  const plotRight = width - PAD.right;
  const plotW = plotRight - plotLeft;
  const plotH = plotBottom - plotTop;

  ctx.strokeStyle = "#2a332c";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = plotTop + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(plotLeft, y);
    ctx.lineTo(plotRight, y);
    ctx.stroke();
  }

  if (!view.counts || view.counts.length < 2) {
    ctx.fillStyle = "#8d887c";
    ctx.font = "13px ui-sans-serif, system-ui, sans-serif";
    ctx.fillText("No spectrum loaded", plotLeft, plotTop + 24);
    return;
  }

  const counts = view.counts;
  const n = counts.length;
  const transform = (value: number) => (view.logScale ? Math.log10(value + 1) : value);
  let yMax = 1;
  for (let i = 0; i < n; i++) {
    yMax = Math.max(yMax, transform(counts[i]), view.model ? transform(view.model[i]) : 0);
  }
  yMax *= 1.08;

  const mapX = (channel: number) => plotLeft + (channel / (n - 1)) * plotW;
  const mapY = (value: number) => plotBottom - (transform(value) / yMax) * plotH;

  strokeEnvelope(ctx, counts, mapX, mapY, "#f4f0e6", plotLeft, plotRight, n);
  if (view.background) strokeEnvelope(ctx, view.background, mapX, mapY, "#e0a45a", plotLeft, plotRight, n);
  if (view.model) strokeEnvelope(ctx, view.model, mapX, mapY, "#8dceab", plotLeft, plotRight, n);

  ctx.fillStyle = "#8d887c";
  ctx.font = "11px ui-monospace, monospace";
  ctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const fraction = 1 - i / 4;
    const raw = view.logScale ? 10 ** (yMax * fraction) - 1 : yMax * fraction;
    const y = plotTop + (plotH * i) / 4;
    ctx.fillText(formatTick(raw), plotLeft - 8, y + 4);
  }

  ctx.textAlign = "center";
  const energyTicks = 6;
  for (let i = 0; i <= energyTicks; i++) {
    const channel = ((n - 1) * i) / energyTicks;
    const energy = view.calibration.zero + view.calibration.gain * channel;
    const x = mapX(channel);
    ctx.fillText(energy.toFixed(1), x, plotBottom + 16);
  }
  ctx.fillText("keV", plotRight, height - residualH + 4);

  let lastLabel = -Infinity;
  for (const peak of view.peaks) {
    const channel = (peak.energy - view.calibration.zero) / view.calibration.gain;
    if (channel < 0 || channel > n - 1) continue;
    const x = mapX(channel);
    ctx.strokeStyle = "rgba(242, 212, 138, 0.35)";
    ctx.beginPath();
    ctx.moveTo(x, plotTop);
    ctx.lineTo(x, plotBottom);
    ctx.stroke();
    if (x - lastLabel < 46) continue;
    lastLabel = x;
    ctx.fillStyle = "#f2d48a";
    ctx.textAlign = "center";
    ctx.fillText(peak.key, x, plotTop + 12);
  }

  const resTop = height - residualH - PAD.bottom + 18;
  const resBottom = height - PAD.bottom;
  ctx.fillStyle = "#8d887c";
  ctx.textAlign = "left";
  ctx.fillText("Residual", plotLeft, resTop - 6);
  ctx.strokeStyle = "#2a332c";
  ctx.beginPath();
  ctx.moveTo(plotLeft, (resTop + resBottom) / 2);
  ctx.lineTo(plotRight, (resTop + resBottom) / 2);
  ctx.stroke();

  if (view.model) {
    let maxAbs = 1;
    for (let i = 0; i < n; i++) maxAbs = Math.max(maxAbs, Math.abs(counts[i] - view.model[i]));
    ctx.beginPath();
    ctx.strokeStyle = "#e07a5a";
    for (let i = 0; i < n; i += Math.max(1, Math.floor(n / plotW))) {
      const residual = counts[i] - view.model[i];
      const x = mapX(i);
      const y = (resTop + resBottom) / 2 - (residual / maxAbs) * ((resBottom - resTop) / 2) * 0.9;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
}

function strokeEnvelope(
  ctx: CanvasRenderingContext2D,
  values: Float64Array,
  mapX: (channel: number) => number,
  mapY: (value: number) => number,
  color: string,
  plotLeft: number,
  plotRight: number,
  n: number,
) {
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.2;
  const pixels = Math.max(1, Math.floor(plotRight - plotLeft));
  let started = false;
  for (let px = 0; px <= pixels; px++) {
    const c0 = Math.floor((px / pixels) * (n - 1));
    const c1 = Math.max(c0 + 1, Math.floor(((px + 1) / pixels) * (n - 1)));
    let lo = Infinity;
    let hi = -Infinity;
    for (let c = c0; c < c1 && c < n; c++) {
      const value = values[c];
      if (value < lo) lo = value;
      if (value > hi) hi = value;
    }
    if (!Number.isFinite(lo)) continue;
    const x = plotLeft + px;
    const yLo = mapY(lo);
    const yHi = mapY(hi);
    if (!started) {
      ctx.moveTo(x, yHi);
      started = true;
    } else {
      ctx.lineTo(x, yHi);
    }
    if (yLo !== yHi) ctx.lineTo(x, yLo);
  }
  ctx.stroke();
}

function formatTick(value: number): string {
  if (!Number.isFinite(value)) return "";
  if (value >= 1000) return `${Math.round(value / 100) / 10}k`;
  if (value >= 10) return String(Math.round(value));
  return value.toFixed(1);
}
