import { Link } from "react-router-dom";

export type TopItem = { key: string; label: string; sub?: string; value: number; href?: string };

/** A ranked top-N list with an inline magnitude bar, for the Reports page leaderboards. */
export function TopList({
  title,
  items,
  format,
  empty = "Nothing here yet.",
}: {
  title: string;
  items: TopItem[];
  format: (n: number) => string;
  empty?: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <figure className="chart-tile top-tile">
      <figcaption>
        <span>
          <strong>{title}</strong>
          <small>Last 12 months</small>
        </span>
      </figcaption>
      {items.length ? (
        <ol className="top-list">
          {items.map((i, n) => (
            <li key={i.key}>
              <span className="top-rank numeric" aria-hidden="true">
                {n + 1}
              </span>
              <span className="top-name">
                {i.href ? <Link to={i.href}>{i.label}</Link> : i.label}
                {i.sub && <small>{i.sub}</small>}
              </span>
              <span className="top-value numeric">{format(i.value)}</span>
              <span className="top-bar" aria-hidden="true">
                <span style={{ width: `${(i.value / max) * 100}%` }} />
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="chart-empty">{empty}</p>
      )}
    </figure>
  );
}
