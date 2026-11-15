import { type PointerEvent, type ReactNode, useRef, useState } from "react";

import "./charts.css";

export type Datum = { key: string; label: string; value: number; color: string; detail?: string };

// Validated categorical order (dataviz reference palette, light mode). Color follows the
// entity's position in the source list, never its rank, so toggles never repaint a slice.
export const SERIES = [
  "#2a78d6",
  "#eb6834",
  "#1baf7a",
  "#eda100",
  "#e87ba4",
  "#008300",
  "#6250d6",
  "#e34948",
];

/** Fixed-order hue for the i-th entity; past eight it reuses the last slot ("Other"). */
export const seriesColor = (i: number) => SERIES[Math.min(i, SERIES.length - 1)]!;

type Tip = { x: number; y: number; d: Datum } | null;
type Select = { selected: string | null; onSelect: (key: string | null) => void };

function useTip() {
  const box = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip>(null);
  const move = (d: Datum) => (e: PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    setTip({ x: e.clientX - r.left, y: e.clientY - r.top, d });
  };
  return { box, tip, move, hide: () => setTip(null) };
}

function Tooltip({
  tip,
  format,
  total,
}: {
  tip: Tip;
  format: (n: number) => string;
  total: number;
}) {
  if (!tip) return null;
  return (
    <div className="chart-tip" style={{ left: tip.x, top: tip.y }} role="presentation">
      <strong>{tip.d.label}</strong>
      <span className="numeric">
        {format(tip.d.value)}
        {total > 0 && ` · ${Math.round((tip.d.value / total) * 100)}%`}
      </span>
      {tip.d.detail && <small>{tip.d.detail}</small>}
    </div>
  );
}

export function ChartTile(props: {
  title: string;
  note?: string;
  controls?: ReactNode;
  children: ReactNode;
}) {
  return (
    <figure className="chart-tile">
      <figcaption>
        <span>
          <strong>{props.title}</strong>
          {props.note && <small>{props.note}</small>}
        </span>
        {props.controls}
      </figcaption>
      {props.children}
    </figure>
  );
}

export function Toggle<T extends string>(props: {
  label: string;
  value: T;
  options: [T, string][];
  onChange: (v: T) => void;
}) {
  return (
    <div className="chart-toggle" role="group" aria-label={props.label}>
      {props.options.map(([v, text]) => (
        <button key={v} aria-pressed={props.value === v} onClick={() => props.onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  );
}

const C = 100;
const R = 92;
const r = 58;

function arc(a0: number, a1: number) {
  const end = Math.min(a1, a0 + 2 * Math.PI - 0.0001);
  const large = end - a0 > Math.PI ? 1 : 0;
  const p = (rad: number, a: number) => `${C + rad * Math.cos(a)} ${C + rad * Math.sin(a)}`;
  return `M${p(R, a0)} A${R} ${R} 0 ${large} 1 ${p(R, end)} L${p(r, end)} A${r} ${r} 0 ${large} 0 ${p(r, a0)}Z`;
}

/** Donut with a clickable legend; the legend is the keyboard and screen-reader path. */
export function Donut({
  data,
  format,
  selected,
  onSelect,
}: { data: Datum[]; format: (n: number) => string } & Select) {
  const { box, tip, move, hide } = useTip();
  const [hover, setHover] = useState<string | null>(null);
  const total = data.reduce((s, d) => s + d.value, 0);
  const focus = hover ?? selected;
  const shown = data.find((d) => d.key === focus);
  const toggle = (k: string) => onSelect(selected === k ? null : k);
  const slices: { d: Datum; path: string }[] = [];
  for (let k = 0, a = -Math.PI / 2; k < data.length; k++) {
    const d = data[k]!;
    if (d.value <= 0) continue;
    const a1 = a + (d.value / total) * 2 * Math.PI;
    slices.push({ d, path: arc(a, a1) });
    a = a1;
  }
  return (
    <div className="donut">
      <div className="donut-plot" ref={box} onPointerLeave={hide}>
        <svg viewBox="0 0 200 200" aria-hidden="true">
          {total === 0 && <circle cx={C} cy={C} r={(R + r) / 2} className="donut-empty" />}
          {slices.map(({ d, path }) => (
            <path
              key={d.key}
              d={path}
              fill={d.color}
              className={focus && focus !== d.key ? "dim" : undefined}
              onPointerMove={move(d)}
              onPointerEnter={() => setHover(d.key)}
              onPointerLeave={() => setHover(null)}
              onClick={() => toggle(d.key)}
            />
          ))}
        </svg>
        <div className="donut-center">
          <strong className="numeric">{format(shown ? shown.value : total)}</strong>
          <small>{shown ? shown.label : "Total"}</small>
        </div>
        <Tooltip tip={tip} format={format} total={total} />
      </div>
      <ul className="chart-legend">
        {data.map((d) => (
          <li key={d.key}>
            <button
              aria-pressed={selected === d.key}
              className={focus && focus !== d.key ? "dim" : undefined}
              onClick={() => toggle(d.key)}
              onPointerEnter={() => setHover(d.key)}
              onPointerLeave={() => setHover(null)}
            >
              <span className="swatch" style={{ background: d.color }} />
              <span className="legend-label">{d.label}</span>
              <span className="numeric">
                {format(d.value)}
                <small>{total ? Math.round((d.value / total) * 100) : 0}%</small>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Ranked horizontal bars; each row is a button so it works by keyboard too. */
export function Bars({
  data,
  format,
  selected,
  onSelect,
}: { data: Datum[]; format: (n: number) => string } & Select) {
  const { box, tip, move, hide } = useTip();
  const max = Math.max(1, ...data.map((d) => d.value));
  const total = data.reduce((s, d) => s + d.value, 0);
  const rows = [...data].sort((x, y) => y.value - x.value);
  return (
    <div className="bars" ref={box} onPointerLeave={hide}>
      {rows.map((d) => (
        <button
          key={d.key}
          className={selected && selected !== d.key ? "bar-row dim" : "bar-row"}
          aria-pressed={selected === d.key}
          aria-label={`${d.label}: ${format(d.value)}${d.detail ? `, ${d.detail}` : ""}`}
          onClick={() => onSelect(selected === d.key ? null : d.key)}
          onPointerMove={move(d)}
        >
          <span className="bar-label">{d.label}</span>
          <span className="bar-track" aria-hidden="true">
            <span style={{ width: `${(d.value / max) * 100}%`, background: d.color }} />
          </span>
          <span className="bar-value numeric">{format(d.value)}</span>
        </button>
      ))}
      {!rows.length && <p className="chart-empty">Nothing to chart yet.</p>}
      <Tooltip tip={tip} format={format} total={total} />
    </div>
  );
}
