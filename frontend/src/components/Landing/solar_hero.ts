import { useCallback, useEffect, useRef, useState } from "react";
import {
  DAY_SECONDS,
  KWMAX,
  MODES,
  clearSky,
  forecastAt,
  hourString,
  skyVars,
  type CloudMode,
  type SimState,
} from "./solar";
import { createSolarScene } from "./solar_scene";

export interface Hud {
  t: number;
  time: string;
  live: number;
  fc: number;
  lo: number;
  hi: number;
}

const isDarkNow = () => document.documentElement.classList.contains("dark");

/**
 * Owns the simulation state, the render loop and the sky.
 * Attach `heroRef` to the <section> and `mountRef` to an empty <div> (the scene creates its own canvas inside it).
 */
export function useSolarHero() {
  const heroRef = useRef<HTMLElement>(null);
  const mountRef = useRef<HTMLDivElement>(null);
  const sim = useRef<SimState>({ t: 0.42, mode: 1, playing: false, live: 0, shaded: 0 });
  const push = useRef<() => void>(() => {});

  const [mode, setModeState] = useState<CloudMode>(1);
  const [playing, setPlayingState] = useState(false);
  const [hud, setHud] = useState<Hud>(() => {
    const f = forecastAt(0.42, 1);
    return { t: 0.42, time: hourString(0.42), live: 0, fc: f.p50, lo: f.lo, hi: f.hi };
  });

  const setMode = useCallback((m: CloudMode) => {
    sim.current.mode = m;
    setModeState(m);
    push.current();
  }, []);

  const setPlaying = useCallback((p: boolean) => {
    sim.current.playing = p;
    setPlayingState(p);
  }, []);

  const setTime = useCallback((t: number) => {
    sim.current.t = t;
    sim.current.playing = false;
    setPlayingState(false);
    push.current();
  }, []);

  useEffect(() => {
    const hero = heroRef.current;
    const mount = mountRef.current;
    if (!hero || !mount) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const s = sim.current;
    s.playing = !reduce;
    setPlayingState(!reduce);

    const scene = createSolarScene({ mount, container: hero, sim: s, reduceMotion: reduce });

    // sky + HUD update (called ~10x/s and on every user input)
    const pushHud = () => {
      const f = forecastAt(s.t, s.mode);
      setHud({ t: s.t, time: hourString(s.t), live: s.live, fc: f.p50, lo: f.lo, hi: f.hi });
      const vars = skyVars(s.t, isDarkNow(), s.shaded);
      for (const k in vars) hero.style.setProperty(k, vars[k]);
    };
    push.current = pushHud;

    // follow the shadcn/next-themes `.dark` class
    const mo = new MutationObserver(pushHud);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    // only render while the hero is on screen
    let visible = true;
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
    });
    io.observe(hero);

    let raf = 0;
    let last = performance.now();
    let acc = 1;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!visible) return;

      if (s.playing) {
        s.t += dt / DAY_SECONDS;
        if (s.t > 0.97) s.t = 0.03;
      }
      const moving = !reduce || s.playing;
      if (scene) scene.frame(dt, now, moving);
      else s.live = KWMAX * clearSky(s.t) * (1 - 0.75 * MODES[s.mode].c);

      acc += dt;
      if (acc > 0.1) {
        acc = 0;
        pushHud();
      }
    };
    pushHud();
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      mo.disconnect();
      io.disconnect();
      push.current = () => {};
      scene?.dispose();
    };
  }, []);

  return { heroRef, mountRef, hud, mode, setMode, playing, setPlaying, setTime };
}