import { useEffect } from "react";

// Stand-in for screens built in later phases (see docs/PLAN.md).
export function PlaceholderPage({ title, phase }: { title: string; phase: string }) {
  useEffect(() => {
    document.title = `${title} · CIC Compass`;
  }, [title]);
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title" className="text-2xl font-semibold">
        {title}
      </h1>
      <p className="mt-2 text-slate-700">Coming in {phase}.</p>
    </section>
  );
}
