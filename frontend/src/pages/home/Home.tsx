import { useState } from "react";
import { ForecastDock } from "@/components/Landing/forecast";
import { useSolarHero } from "@/components/Landing/solar_hero";
import { useTheme } from "next-themes";
import logo_dark from "@/assets/logo/logo_dark.png";
import logo_light from "@/assets/logo/logo_white.png";
import { LoginModal } from "@/components/auth/LoginModal";

const COPY = {
  brand: "Solaris",
  headline: "Every rooftop's sunshine, forecast before it reaches the grid.",
  lede: "Solaris predicts photovoltaic output across Tunisia, from a single roof to a whole governorate.",
  primary: "Enter Administration Portal",
} as const;

export default function HeroSection() {
  const {
    heroRef,
    mountRef,
    hud,
    mode,
    setMode,
    playing,
    setPlaying,
    setTime,
  } = useSolarHero();

  const { theme, systemTheme } = useTheme();
  const currentTheme = theme === "system" ? systemTheme : theme;
  const isDarkMode = currentTheme === "dark";

  const [loginOpen, setLoginOpen] = useState(false);

  return (
    <>
      <section
        id="hero"
        ref={heroRef}
        aria-labelledby="hero-heading"
        className="relative isolate flex min-h-[max(100svh,880px)] flex-col overflow-hidden px-5 text-white sm:px-8 lg:min-h-[max(100svh,720px)] lg:px-16"
        style={{
          background:
            "var(--sky, linear-gradient(180deg,#2266b0 0%,#4a8fd0 52%,#8fc0e8 100%))",
        }}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute z-0 aspect-square w-[min(70vw,460px)] -translate-x-1/2 -translate-y-1/2 rounded-full lg:w-[520px] motion-safe:transition-[left,top,opacity] motion-safe:duration-700 motion-safe:ease-out"
          style={{
            left: "var(--sx, 60%)",
            top: "var(--sy, 20%)",
            opacity: "var(--sun-o, 1)" as unknown as number,
            background:
              "radial-gradient(circle, var(--sun-core, #fff0be) 0 12%, var(--sun-halo, rgba(255,214,130,.6)) 13%, rgba(255,214,130,0) 66%)",
          }}
        />

        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-[1] bg-[linear-gradient(180deg,rgba(8,24,52,.66)_0%,rgba(8,24,52,.3)_45%,rgba(8,24,52,0)_62%)] dark:bg-[linear-gradient(180deg,rgba(3,10,24,.7)_0%,rgba(3,10,24,.32)_45%,rgba(3,10,24,0)_62%)] lg:bg-[linear-gradient(90deg,rgba(8,24,52,.66)_0%,rgba(8,24,52,.4)_36%,rgba(8,24,52,0)_62%)] lg:dark:bg-[linear-gradient(90deg,rgba(3,10,24,.7)_0%,rgba(3,10,24,.42)_36%,rgba(3,10,24,0)_62%)]"
        />

        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 z-[1] h-[16vh] bg-gradient-to-b from-transparent to-background"
        />

        <div ref={mountRef} aria-hidden="true" className="absolute inset-0 z-[2]" />

        <div className="relative z-[3] max-w-[640px] lg:flex lg:max-w-[min(46vw,660px)] lg:flex-1 lg:flex-col lg:justify-center lg:pb-[9vh] lg:pt-0">
          <a href="/" aria-label={`${COPY.brand} home`}>
            <img
              src={isDarkMode ? logo_dark : logo_light}
              alt="logo of Solaris"
              className="h-40 w-40"
            />
          </a>

          <h1
            id="hero-heading"
            className="text-balance text-[clamp(2.45rem,1.3rem+4.4vw,5.2rem)] font-bold leading-[1.03] tracking-[-0.03em] [text-shadow:0_2px_24px_rgba(5,15,34,0.25)]"
          >
            {COPY.headline}
          </h1>

          <p className="mb-8 max-w-[46ch] text-[clamp(1.02rem,0.96rem+0.3vw,1.2rem)] leading-relaxed text-white/85">
            {COPY.lede}
          </p>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => setLoginOpen(true)}
              className="inline-flex h-11 items-center justify-center rounded-full bg-amber-400 px-6 font-semibold text-slate-900 shadow-lg shadow-amber-400/20 transition-colors hover:bg-amber-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent"
            >
              {COPY.primary}
            </button>
          </div>
        </div>

        <div className="min-h-[250px] flex-1 lg:hidden" />

        <ForecastDock
          hud={hud}
          mode={mode}
          playing={playing}
          onMode={setMode}
          onPlaying={setPlaying}
          onTime={setTime}
          className="relative z-[3] mb-6 lg:absolute lg:bottom-[clamp(20px,4vh,44px)] lg:right-[clamp(20px,3.4vw,56px)] lg:mb-0 lg:w-[min(500px,44vw)]"
        />
      </section>

      <LoginModal open={loginOpen} onClose={() => setLoginOpen(false)} />
    </>
  );
}