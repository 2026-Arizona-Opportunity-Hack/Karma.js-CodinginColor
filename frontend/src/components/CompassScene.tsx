import { type KeyboardEvent, useEffect, useRef, useState } from "react";

// An original compass (not the CIC logo). Its needle turns toward the pointer anywhere on the
// page; the orbiting points are moments in a donor relationship. Purely decorative for sign-in:
// nothing here touches auth.

const MOMENTS = [
  { r: 150, a: -62, label: "Thank-you approved" },
  { r: 118, a: -8, label: "Gift recorded" },
  { r: 156, a: 38, label: "Quarterly update due" },
  { r: 126, a: 92, label: "Next step: coffee in March" },
  { r: 150, a: 148, label: "Back after a year away" },
  { r: 112, a: 196, label: "Employer match linked" },
  { r: 146, a: 250, label: "A new relationship" },
] as const;
const point = (r: number, a: number) => {
  const rad = (a * Math.PI) / 180;
  return { x: 200 + r * Math.cos(rad), y: 200 + r * Math.sin(rad) };
};
const NODES = MOMENTS.map((m) => ({ ...m, ...point(m.r, m.a) }));
const TICKS = Array.from({ length: 72 }, (_, i) => {
  const long = i % 6 === 0;
  const a = (i * 360) / 72;
  return { outer: point(182, a), inner: point(long ? 168 : 174, a), long };
});
const IDLE = "Every relationship, pointing somewhere. Hover or tap a point.";

export function CompassScene() {
  const svgRef = useRef<SVGSVGElement>(null);
  const [caption, setCaption] = useState(IDLE);
  const [active, setActive] = useState<number | null>(null);
  const [spinning, setSpinning] = useState(false);
  const [tracking, setTracking] = useState(false);

  // Needle follows the pointer: one rAF per frame, only for fine pointers without reduced motion.
  useEffect(() => {
    const svg = svgRef.current;
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!svg || !fine || calm) return;
    let frame = 0;
    let angle = 0;
    let last: PointerEvent | null = null;
    const update = () => {
      frame = 0;
      if (!last) return;
      const box = svg.getBoundingClientRect();
      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      // 0deg is north; keep turning the short way so the needle never whips around.
      const target = (Math.atan2(last.clientY - cy, last.clientX - cx) * 180) / Math.PI + 90;
      angle += ((((target - angle) % 360) + 540) % 360) - 180;
      svg.style.setProperty("--needle", `${angle}deg`);
      svg.style.setProperty("--px", ((last.clientX - cx) / window.innerWidth).toFixed(3));
      svg.style.setProperty("--py", ((last.clientY - cy) / window.innerHeight).toFixed(3));
    };
    const onMove = (e: PointerEvent) => {
      last = e;
      setTracking(true);
      if (!frame) frame = requestAnimationFrame(update);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(frame);
    };
  }, []);

  const show = (i: number) => {
    setActive(i);
    setCaption(MOMENTS[i]?.label ?? IDLE);
  };
  const press = (event: KeyboardEvent, run: () => void) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      run();
    }
  };
  const spin = () => {
    setSpinning(true);
    setCaption("True north: the next person to thank.");
  };

  return (
    <figure className="compass-scene">
      <svg
        ref={svgRef}
        viewBox="0 0 400 400"
        className={tracking ? "compass is-tracking" : "compass"}
        role="group"
        aria-label="Animated compass surrounded by moments in donor relationships"
      >
        <defs>
          <radialGradient id="compass-face" cx="50%" cy="45%" r="60%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.16" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0.02" />
          </radialGradient>
        </defs>
        <g className="layer-back">
          <circle cx="200" cy="200" r="190" className="ring ring-outer" />
          <g className="ticks">
            {TICKS.map((t, i) => (
              <line
                key={i}
                x1={t.outer.x}
                y1={t.outer.y}
                x2={t.inner.x}
                y2={t.inner.y}
                className={t.long ? "tick tick-long" : "tick"}
              />
            ))}
          </g>
          <circle cx="200" cy="200" r="160" fill="url(#compass-face)" className="ring" />
          {(
            [
              ["N", 200, 58],
              ["E", 344, 205],
              ["S", 200, 352],
              ["W", 56, 205],
            ] as const
          ).map(([l, x, y]) => (
            <text key={l} x={x} y={y} className="cardinal" textAnchor="middle">
              {l}
            </text>
          ))}
        </g>
        <g className="layer-front">
          <g className="orbit">
            <polyline
              points={NODES.map((n) => `${n.x},${n.y}`).join(" ")}
              className="constellation"
            />
            {NODES.map((n, i) => (
              <g
                key={n.label}
                className={active === i ? "moment is-active" : "moment"}
                role="button"
                tabIndex={0}
                aria-label={n.label}
                onMouseEnter={() => show(i)}
                onFocus={() => show(i)}
                onClick={() => show(i)}
                onKeyDown={(e) => press(e, () => show(i))}
              >
                <circle cx={n.x} cy={n.y} r="16" className="moment-hit" />
                <circle cx={n.x} cy={n.y} r="9" className="moment-halo" />
                <circle cx={n.x} cy={n.y} r="5" className="moment-dot" />
              </g>
            ))}
          </g>
          <g
            className={spinning ? "needle is-spinning" : "needle"}
            onAnimationEnd={() => setSpinning(false)}
          >
            <polygon points="200,72 214,200 200,214 186,200" className="needle-north" />
            <polygon points="200,328 214,200 200,186 186,200" className="needle-south" />
          </g>
          <g
            className="hub"
            role="button"
            tabIndex={0}
            aria-label="Spin the compass"
            onClick={spin}
            onKeyDown={(e) => press(e, spin)}
          >
            <circle cx="200" cy="200" r="22" className="hub-hit" />
            <circle cx="200" cy="200" r="12" className="hub-ring" />
            <circle cx="200" cy="200" r="4" className="hub-dot" />
          </g>
        </g>
      </svg>
      <figcaption aria-live="polite">{caption}</figcaption>
    </figure>
  );
}
