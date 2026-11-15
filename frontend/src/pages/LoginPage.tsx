import {
  ArrowDown,
  ArrowRight,
  Compass,
  FileUp,
  ListChecks,
  LoaderCircle,
  Mail,
  PieChart,
  ShieldCheck,
} from "lucide-react";
import {
  type CSSProperties,
  type FormEvent,
  type RefObject,
  useEffect,
  useRef,
  useState,
} from "react";
import { Navigate, useLocation } from "react-router-dom";

import { CompassScene } from "../components/CompassScene";
import { useLogin, useMe } from "../hooks/useAuth";
import "./landing.css";

const FEATURES = [
  {
    icon: FileUp,
    title: "Bring every gift into one ledger",
    body: "Upload the donor spreadsheet, Zeffy and Benevity exports. Possible duplicates wait for a person to review; uploading the same file twice adds nothing twice.",
  },
  {
    icon: ListChecks,
    title: "Know who to thank next",
    body: "Each board member gets a to-do list of thank-yous, quarterly updates and next steps, most urgent first.",
  },
  {
    icon: Mail,
    title: "Words worth sending",
    body: "Compass drafts thank-yous and updates from shared templates. A board member reads, edits and approves before anything is sent.",
  },
  {
    icon: PieChart,
    title: "See who stayed and who drifted",
    body: "Giving by month, quarter and program, plus donor retention, with employer matches counted the way Coding in Color counts them.",
  },
  {
    icon: ShieldCheck,
    title: "Private by design",
    body: "Contact details stay with the board member who cares for that relationship, and every change is recorded.",
  },
] as const;

const STEPS = [
  ["Import", "Bring in the files you already have."],
  ["Follow up", "Thank, update and plan the next conversation."],
  ["Report", "Share what the support made possible."],
] as const;

// Adds `is-visible` as sections scroll in. Without IntersectionObserver everything shows at once.
function useReveal(root: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const items = el.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) {
      items.forEach((i) => i.classList.add("is-visible"));
      return;
    }
    el.classList.add("reveal-ready");
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("is-visible");
            io.unobserve(e.target);
          }
        }),
      { threshold: 0.15 },
    );
    items.forEach((i) => io.observe(i));
    return () => io.disconnect();
  }, [root]);
}

// Ambient loops stop while the tab is hidden.
function usePauseWhenHidden(root: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const sync = () => root.current?.toggleAttribute("data-paused", document.hidden);
    document.addEventListener("visibilitychange", sync);
    return () => document.removeEventListener("visibilitychange", sync);
  }, [root]);
}

export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const root = useRef<HTMLDivElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  useReveal(root);
  usePauseWhenHidden(root);
  useEffect(() => {
    document.title = "Sign in · CIC Compass";
  }, []);

  if (me.data) return <Navigate to={from} replace />;

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    login.mutate({ email, password });
  }

  const toSignIn = () => {
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    emailRef.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "center" });
    emailRef.current?.focus({ preventScroll: true });
  };

  return (
    <div className="landing" ref={root}>
      <main>
        <div className="landing-hero">
          <div className="hero-backdrop" aria-hidden="true" />
          <div className="hero-intro">
            <p className="landing-brand">
              <Compass size={28} strokeWidth={1.5} aria-hidden="true" />
              <span>
                CIC Compass
                <small>Coding in Color</small>
              </span>
            </p>
            <h1 className="hero-title">
              <span>Every donor relationship,</span> <span>carried forward.</span>
            </h1>
            <p className="hero-lede">
              One shared place for Coding in Color’s donors, gifts and follow-ups, so every board
              member knows who to thank next.
            </p>
            <div className="hero-actions">
              <button type="button" className="hero-cta" onClick={toSignIn}>
                Sign in to your workspace
                <ArrowRight size={20} aria-hidden="true" />
              </button>
              <a className="hero-link" href="#landing-features">
                See what’s inside
                <ArrowDown size={16} aria-hidden="true" />
              </a>
            </div>
          </div>

          <section className="signin-panel" aria-labelledby="signin-title">
            <div className="signin-card">
              <p className="signin-eyebrow">Board members</p>
              <h2 id="signin-title">Welcome back</h2>
              <p className="signin-note">Sign in with your board member account.</p>
              <form onSubmit={onSubmit} noValidate>
                <div className="field">
                  <label htmlFor="email">Email</label>
                  <input
                    ref={emailRef}
                    id="email"
                    type="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="password">Password</label>
                  <div className="password-row">
                    <input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                    <button
                      type="button"
                      className="reveal-password"
                      aria-pressed={showPassword}
                      aria-controls="password"
                      onClick={() => setShowPassword((v) => !v)}
                    >
                      {showPassword ? "Hide" : "Show"}
                      <span className="sr-only"> password</span>
                    </button>
                  </div>
                </div>
                {login.error && (
                  <p role="alert" className="signin-error" key={login.submittedAt}>
                    {login.error.message}
                  </p>
                )}
                <button type="submit" className="signin-submit" disabled={login.isPending}>
                  {login.isPending ? (
                    <>
                      <LoaderCircle className="spinner" size={18} aria-hidden="true" />
                      Signing in…
                    </>
                  ) : (
                    <>
                      Sign in
                      <ArrowRight size={18} aria-hidden="true" />
                    </>
                  )}
                </button>
              </form>
              <p className="signin-help">
                New board member? Use the invitation link a member sent you.
              </p>
            </div>
          </section>

          <div className="hero-visual">
            <CompassScene />
          </div>
        </div>

        <section
          id="landing-features"
          className="landing-features"
          aria-labelledby="features-title"
        >
          <div className="section-head reveal">
            <p className="landing-eyebrow">What Compass does</p>
            <h2 id="features-title">Care that doesn’t fall through the cracks.</h2>
          </div>
          <ul className="feature-grid">
            {FEATURES.map(({ icon: Icon, title, body }, i) => (
              <li key={title} className="feature reveal" style={{ "--i": i } as CSSProperties}>
                <span className="feature-icon" aria-hidden="true">
                  <Icon size={22} strokeWidth={1.8} />
                </span>
                <h3>{title}</h3>
                <p>{body}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="landing-steps" aria-labelledby="steps-title">
          <div className="section-head reveal">
            <p className="landing-eyebrow">How it works</p>
            <h2 id="steps-title">Three steps, one shared story.</h2>
          </div>
          <ol className="step-track reveal">
            {STEPS.map(([title, body], i) => (
              <li key={title} style={{ "--i": i } as CSSProperties}>
                <span className="step-number" aria-hidden="true">
                  {i + 1}
                </span>
                <h3>{title}</h3>
                <p>{body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-final reveal" aria-labelledby="final-title">
          <h2 id="final-title">Your next thank-you is waiting.</h2>
          <p>Pick up where the board left off.</p>
          <button type="button" className="hero-cta" onClick={toSignIn}>
            Sign in
            <ArrowRight size={20} aria-hidden="true" />
          </button>
        </section>
      </main>

      <footer className="landing-footer">
        <span>CIC Compass for Coding in Color</span>
        <span>Built by team Karma.js · Opportunity Hack 2026 · Open source (MIT)</span>
      </footer>
    </div>
  );
}
