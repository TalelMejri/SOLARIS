import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { KWMAX, KWP, MODES, forecastAt, type CloudMode } from "./solar";
import type { Hud } from "./solar_hero";

const CW = 400;
const BASE = 96;
const TOP = 8;
const YMAX = KWMAX * 1.06;
const X = (t: number) => t * CW;
const Y = (v: number) => BASE - (v / YMAX) * (BASE - TOP);

const TICKS: { x: number; label: string; anchor: "start" | "middle" }[] = [
  { x: 0, label: "06:00", anchor: "start" },
  { x: 118.5, label: "09:00", anchor: "middle" },
  { x: 207.4, label: "12:00", anchor: "middle" },
  { x: 296.3, label: "15:00", anchor: "middle" },
  { x: 385.2, label: "18:00", anchor: "middle" },
];

interface ForecastDockProps {
  hud: Hud;
  mode: CloudMode;
  playing: boolean;
  onMode: (m: CloudMode) => void;
  onPlaying: (p: boolean) => void;
  onTime: (t: number) => void;
  className?: string;
  /** translated strings, all optional */
  labels?: Partial<{
    title: string;
    cloudCover: string;
    time: string;
    outputNow: string;
    forecast: string;
    range: string;
    to: string;
    hint: string;
    play: string;
    pause: string;
    chartAlt: string;
    modes: [string, string, string];
  }>;
}

export function ForecastDock({ hud, mode, playing, onMode, onPlaying, onTime, className, labels = {} }: ForecastDockProps) {
  const L = {
    title: `Simulated ${KWP} kWp rooftop`,
    cloudCover: "Cloud cover",
    time: "Time",
    outputNow: "Output now",
    forecast: "Forecast",
    range: "range",
    to: "to",
    hint: "Drag to move through the day. Shaded area shows the 10 to 90 percent range.",
    play: "Play day",
    pause: "Pause",
    chartAlt: "Forecast output over the day with the uncertainty range shaded",
    modes: MODES.map((m) => m.label) as [string, string, string],
    ...labels,
  };

  const { median, band } = useMemo(() => {
    const N = 72;
    let med = "";
    let up = "";
    const lo: string[] = [];
    for (let i = 0; i <= N; i++) {
      const t = i / N;
      const f = forecastAt(t, mode);
      const x = X(t).toFixed(1);
      med += `${i ? "L" : "M"}${x} ${Y(f.p50).toFixed(1)}`;
      up += `${i ? "L" : "M"}${x} ${Y(f.hi).toFixed(1)}`;
      lo.push(`L${x} ${Y(f.lo).toFixed(1)}`);
    }
    return { median: med, band: `${up}${lo.reverse().join("")}Z` };
  }, [mode]);

  const cx = X(hud.t);

  return (
    <aside
      aria-label="Live forecast demonstration"
      className={cn(
        "rounded-[22px] border border-white/20 bg-[#091c3a]/60 p-4 pb-3.5 text-white shadow-[0_24px_60px_-24px_rgba(3,10,26,0.6)] backdrop-blur-xl backdrop-saturate-150 dark:bg-[#051024]/70",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-semibold text-white/85">{L.title}</p>
        <div role="radiogroup" aria-label={L.cloudCover} className="inline-flex gap-0.5 rounded-full bg-white/10 p-[3px]">
          {MODES.map((m, i) => (
            <button
              key={m.label}
              type="button"
              role="radio"
              aria-checked={mode === i}
              onClick={() => onMode(i as CloudMode)}
              className={cn(
                "rounded-full px-3 py-2 text-[0.8rem] font-semibold leading-none transition-colors",
                mode === i ? "bg-white text-slate-900" : "text-white/85 hover:text-white",
              )}
            >
              {L.modes[i]}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-1 mt-3.5 grid grid-cols-3 gap-3" role="group" aria-label="Current values">
        <div>
          <p className="mb-0.5 text-xs text-white/85">{L.time}</p>
          <p className="text-2xl font-bold leading-tight tracking-tight tabular-nums">{hud.time}</p>
        </div>
        <div>
          <p className="mb-0.5 text-xs text-white/85">{L.outputNow}</p>
          <p className="text-2xl font-bold leading-tight tracking-tight tabular-nums">
            {hud.live.toFixed(1)}
            <small className="ml-1 text-[0.8rem] font-semibold text-white/85">kW</small>
          </p>
        </div>
        <div>
          <p className="mb-0.5 text-xs text-white/85">{L.forecast}</p>
          <p className="text-2xl font-bold leading-tight tracking-tight tabular-nums">
            {hud.fc.toFixed(1)}
            <small className="ml-1 text-[0.8rem] font-semibold text-white/85">kW</small>
          </p>
          <p className="mt-0.5 text-xs tabular-nums text-white/85">
            {L.range} {hud.lo.toFixed(1)} {L.to} {hud.hi.toFixed(1)}
          </p>
        </div>
      </div>

      <svg viewBox="0 0 400 118" role="img" aria-label={L.chartAlt} className="mx-[9px] mt-0.5 block h-auto w-[calc(100%-18px)] overflow-visible">
        <line x1="0" y1={BASE} x2={CW} y2={BASE} stroke="rgba(255,255,255,.28)" />
        <path d={band} fill="rgba(255,182,39,.28)" />
        <path d={median} fill="none" stroke="#FFB627" strokeWidth={2} strokeLinejoin="round" />
        <line x1={cx} x2={cx} y1="6" y2={BASE} stroke="rgba(255,255,255,.4)" strokeDasharray="3 3" />
        <circle cx={cx} cy={Y(hud.live)} r="5.5" fill="#fff" stroke="#FFB627" strokeWidth={3} />
        {TICKS.map((tk) => (
          <text key={tk.label} x={tk.x} y="112" textAnchor={tk.anchor} fill="rgba(244,248,252,.78)" fontSize="10" fontWeight={500}>
            {tk.label}
          </text>
        ))}
      </svg>

      <input
        type="range"
        min={0}
        max={1000}
        step={4}
        value={Math.round(hud.t * 1000)}
        onChange={(e) => onTime(Number(e.target.value) / 1000)}
        aria-label={L.time}
        className={cn(
          "block h-6 w-full cursor-pointer appearance-none bg-transparent focus-visible:outline-none",
          "[&::-webkit-slider-runnable-track]:h-1 [&::-webkit-slider-runnable-track]:rounded-full [&::-webkit-slider-runnable-track]:bg-white/30",
          "[&::-webkit-slider-thumb]:-mt-[7px] [&::-webkit-slider-thumb]:h-[18px] [&::-webkit-slider-thumb]:w-[18px] [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-[3px] [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:bg-amber-400 [&::-webkit-slider-thumb]:shadow-md",
          "[&::-moz-range-track]:h-1 [&::-moz-range-track]:rounded-full [&::-moz-range-track]:bg-white/30",
          "[&::-moz-range-thumb]:h-3 [&::-moz-range-thumb]:w-3 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-[3px] [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:bg-amber-400",
          "focus-visible:[&::-webkit-slider-thumb]:outline focus-visible:[&::-webkit-slider-thumb]:outline-2 focus-visible:[&::-webkit-slider-thumb]:outline-offset-2 focus-visible:[&::-webkit-slider-thumb]:outline-white",
        )}
      />

      <div className="mt-0.5 flex items-center justify-between gap-3">
        <p className="text-xs text-white/85">{L.hint}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPlaying(!playing)}
          className="shrink-0 rounded-full border-white/50 bg-white/5 text-white hover:border-white hover:bg-white/15 hover:text-white"
        >
          {playing ? L.pause : L.play}
        </Button>
      </div>
    </aside>
  );
}