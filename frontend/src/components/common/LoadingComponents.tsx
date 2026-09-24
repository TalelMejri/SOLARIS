import { useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import logo_dark from "@/assets/logo/logo_dark.png";
import logo_light from "@/assets/logo/logo_white.png";

interface LoadingScreenProps {
  exiting?: boolean;
  onExitDone?: () => void;
  exitDurationMs?: number;
  progress?: number;
}

export default function LoadingScreen({
  exiting = false,
  onExitDone,
  exitDurationMs = 600,
  progress,
}: LoadingScreenProps) {
  const [p, setP] = useState(progress ?? 0);
  const startedAt = useRef<number>(Date.now());
  const [logoIn, setLogoIn] = useState(false);

  const { theme, systemTheme } = useTheme();
  const currentTheme = theme === "system" ? systemTheme : theme;
  const isDarkMode = currentTheme === "dark";

  // Timed ramp fallback
  useEffect(() => {
    if (progress != null) {
      setP(progress);
      return;
    }
    let raf = 0;
    const durationMs = 3000;
    const tick = () => {
      const t = Math.min(1, (Date.now() - startedAt.current) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setP(eased * 100);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [progress]);

  // Logo entrance
  useEffect(() => {
    const id = requestAnimationFrame(() => setLogoIn(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Notify parent when exit is done
  useEffect(() => {
    if (!exiting) return;
    const t = setTimeout(() => onExitDone?.(), exitDurationMs);
    return () => clearTimeout(t);
  }, [exiting, exitDurationMs, onExitDone]);

  const R = 46;
  const C = 2 * Math.PI * R;
  const dash = C * (1 - Math.min(100, Math.max(0, p)) / 100);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Loading Solaris"
      className={cn(
        "relative flex h-full w-full items-center justify-center overflow-hidden bg-[#061229] text-white",
        "transition-transform duration-500 ease-out will-change-transform",
        exiting ? "scale-[1.02]" : "scale-100",
      )}
    >
      {/* Ambient background */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(1200px 700px at 50% 40%, rgba(255,182,39,0.14), transparent 60%), radial-gradient(900px 600px at 50% 120%, rgba(74,143,208,0.25), transparent 60%)",
        }}
      />
      {/* Grid */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.6) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage:
            "radial-gradient(circle at 50% 50%, black 0%, transparent 70%)",
        }}
      />

      <div className="relative flex flex-col items-center gap-7">
        {/* Logo — fades/rises in first, then the sun takes over */}
        <img
          src={isDarkMode ? logo_dark : logo_light}
          alt="Solaris"
          draggable={false}
          className={cn(
            "h-50 w-50 select-none ",
            "drop-shadow-[0_4px_24px_rgba(255,182,39,0.35)]",
            "transition-all duration-700 ease-out",
            logoIn
              ? "translate-y-0 opacity-100"
              : "-translate-y-2 opacity-0",
          )}
        />

        {/* Sun + progress ring */}
        <div className="relative h-[132px] w-[132px]">
          {/* Rotating rays */}
          <svg
            aria-hidden="true"
            viewBox="0 0 132 132"
            className="absolute inset-0 h-full w-full motion-safe:animate-[spin_14s_linear_infinite]"
          >
            {Array.from({ length: 12 }).map((_, i) => {
              const a = (i / 12) * Math.PI * 2;
              const x1 = 66 + Math.cos(a) * 40;
              const y1 = 66 + Math.sin(a) * 40;
              const x2 = 66 + Math.cos(a) * 54;
              const y2 = 66 + Math.sin(a) * 54;
              return (
                <line
                  key={i}
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="rgba(255,182,39,.55)"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              );
            })}
          </svg>

          {/* Pulsing glow */}
          <div
            aria-hidden="true"
            className="absolute inset-3 rounded-full bg-amber-400/30 blur-xl motion-safe:animate-[pulseGlow_2.4s_ease-in-out_infinite]"
          />

          {/* Progress ring */}
          <svg
            viewBox="0 0 132 132"
            className="absolute inset-0 h-full w-full -rotate-90"
            aria-hidden="true"
          >
            <circle
              cx="66"
              cy="66"
              r={R}
              fill="none"
              stroke="rgba(255,255,255,.12)"
              strokeWidth="4"
            />
            <circle
              cx="66"
              cy="66"
              r={R}
              fill="none"
              stroke="url(#ringGrad)"
              strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={dash}
              style={{ transition: "stroke-dashoffset .35s ease-out" }}
            />
            <defs>
              <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#FFD27A" />
                <stop offset="100%" stopColor="#FFB627" />
              </linearGradient>
            </defs>
          </svg>

          {/* Sun core */}
          <div className="absolute inset-[34px] rounded-full bg-[radial-gradient(circle,#fff3c4_0%,#ffcf6b_60%,#ffb627_100%)] shadow-[0_0_40px_rgba(255,182,39,.45)]" />
        </div>

        {/* Percent */}
        <div className="flex flex-col items-center gap-2">
          <p className="text-3xl font-bold tabular-nums tracking-tight">
            {Math.round(p)}
            <span className="ml-0.5 text-base font-semibold text-white/60">
              %
            </span>
          </p>
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-white/50">
            Preparing forecast
          </p>
        </div>
      </div>
    </div>
  );
}