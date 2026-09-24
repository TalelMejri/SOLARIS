import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import logo_dark from "@/assets/logo/logo_dark.png";
import { useAuth } from "@/contexts/AuthContext";


interface LoginModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  redirectTo?: string;
}

export function LoginModal({
  open,
  onClose,
  onSuccess,
  redirectTo = "/dashboard",
}: LoginModalProps) {
  const { login, isLoading } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState<{ email?: boolean; password?: boolean }>({});

  const emailId = useId();
  const passwordId = useId();
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setError(null);
      setTouched({});
      setEmail("");
      setPassword("");
      const id = setTimeout(() => emailRef.current?.focus(), 80);
      return () => clearTimeout(id);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  const emailError =
    touched.email && !/^\S+@\S+\.\S+$/.test(email)
      ? "Enter a valid email address"
      : null;
  const passwordError =
    touched.password && password.length < 6
      ? "Password must be at least 6 characters"
      : null;

  const canSubmit =
    !isLoading && /^\S+@\S+\.\S+$/.test(email) && password.length >= 6;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched({ email: true, password: true });
    setError(null);
    if (!canSubmit) return;

    try {
      await login({ email, password });
      onSuccess?.();
      onClose();
      navigate(redirectTo, { replace: true });
    } catch (err: any) {
      const msg =
        err?.response?.data?.message ??
        err?.response?.data?.errors?.email?.[0] ??
        "Invalid email or password. Please try again.";
      setError(msg);
    }
  };

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="login-title"
    >
      <button
        aria-label="Close login dialog"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-slate-950/70 backdrop-blur-md motion-safe:animate-[fadeIn_.2s_ease-out]"
      />

      <div
        className={cn(
          "relative z-[1] w-full max-w-[420px] overflow-hidden rounded-2xl",
          "border border-white/10 bg-[#0a1730] text-white shadow-[0_30px_80px_-20px_rgba(0,0,0,0.6)]",
          "motion-safe:animate-[modalIn_.28s_cubic-bezier(0.16,1,0.3,1)]",
        )}
      >
        <div className="h-1 w-full bg-gradient-to-r from-amber-300 via-amber-400 to-amber-500" />

        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute right-3 top-4 z-[2] rounded-full p-2 text-white/60 transition-colors hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M5 5l10 10M15 5L5 15" />
          </svg>
        </button>

        <div className="p-6 sm:p-7">
          <div className="mb-6 flex flex-col items-center text-center">
            <img src={logo_dark} alt="Solaris" className="mb-4 h-12 w-auto drop-shadow-[0_4px_20px_rgba(255,182,39,0.35)]" />
            <h2 id="login-title" className="text-lg font-semibold tracking-tight">
              Administration Portal
            </h2>
            <p className="mt-1 text-sm text-white/60">
              Sign in to access the Solaris dashboard
            </p>
          </div>

          {error && (
            <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-red-400/30 bg-red-500/10 px-3 py-2.5 text-sm text-red-200 motion-safe:animate-[fadeIn_.2s_ease-out]">
              <svg viewBox="0 0 20 20" className="mt-0.5 h-4 w-4 shrink-0" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v4a1 1 0 102 0V7zm-1 7a1 1 0 100 2 1 1 0 000-2z" clipRule="evenodd" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            <div>
              <label htmlFor={emailId} className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-white/60">
                Email
              </label>
              <input
                ref={emailRef}
                id={emailId}
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, email: true }))}
                placeholder="you@solaris.tn"
                aria-invalid={!!emailError}
                aria-describedby={emailError ? `${emailId}-err` : undefined}
                className={cn(
                  "h-11 w-full rounded-lg border bg-white/5 px-3.5 text-[0.95rem] text-white placeholder:text-white/30",
                  "transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-amber-400/60",
                  emailError
                    ? "border-red-400/60 focus:ring-red-400/60"
                    : "border-white/15 hover:border-white/25 focus:border-amber-400/60",
                )}
              />
              {emailError && <p id={`${emailId}-err`} className="mt-1.5 text-xs text-red-300">{emailError}</p>}
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label htmlFor={passwordId} className="text-xs font-medium uppercase tracking-wider text-white/60">
                  Password
                </label>
                <a href="#forgot" className="text-xs font-medium text-amber-300/90 transition-colors hover:text-amber-200">
                  Forgot?
                </a>
              </div>
              <input
                id={passwordId}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, password: true }))}
                placeholder="••••••••"
                aria-invalid={!!passwordError}
                aria-describedby={passwordError ? `${passwordId}-err` : undefined}
                className={cn(
                  "h-11 w-full rounded-lg border bg-white/5 px-3.5 text-[0.95rem] text-white placeholder:text-white/30",
                  "transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-amber-400/60",
                  passwordError
                    ? "border-red-400/60 focus:ring-red-400/60"
                    : "border-white/15 hover:border-white/25 focus:border-amber-400/60",
                )}
              />
              {passwordError && <p id={`${passwordId}-err`} className="mt-1.5 text-xs text-red-300">{passwordError}</p>}
            </div>

            <button
              type="submit"
              disabled={!canSubmit}
              className={cn(
                "mt-2 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg",
                "bg-amber-400 font-semibold text-slate-900 shadow-lg shadow-amber-400/20",
                "transition-all duration-200",
                "hover:-translate-y-0.5 hover:bg-amber-300 hover:shadow-xl hover:shadow-amber-300/30",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a1730]",
                "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0",
              )}
            >
              {isLoading ? (
                <>
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
                    <path d="M22 12a10 10 0 00-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                  Signing in…
                </>
              ) : (
                "Sign in"
              )}
            </button>
          </form>

          <p className="mt-5 text-center text-xs text-white/40">
            Access is restricted to authorized administrators.
          </p>
        </div>
      </div>
    </div>,
    document.body,
  );
}