import { ArrowUpRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Bars, ChartTile, type Datum, Donut, seriesColor, Toggle } from "../components/Charts";
import { ErrorState, LoadingLedger, PageMasthead } from "../components/Workspace";
import { type Retention, type Summary, useReportSummary, useRetention } from "../hooks/useReports";
import { calendarDate, dollars } from "../lib/format";
import "./reports.css";

type ClassName = keyof Retention["classes"];
const CLASSES: [ClassName, string, string][] = [
  ["new", "New", "Gave this period, never before"],
  ["reactivated", "Reactivated", "Back this period after skipping the last one"],
  ["increased", "Increased", "Gave more than the previous period"],
  ["same", "Same", "Gave the same as the previous period"],
  ["decreased", "Decreased", "Gave less than the previous period"],
  ["lapsed", "Lapsed", "Gave in the previous period, not this one"],
];

const NONE = { donors: 0, cents_cur: 0, cents_prev: 0 };

function movement(cents: number) {
  if (cents === 0) return "No change";
  return `${cents > 0 ? "+" : "−"}${dollars(Math.abs(cents))}`;
}

const count = (n: number) => n.toLocaleString();

// Keep at most eight colors; anything past seven programs folds into "Other".
function programData(s: Summary, metric: "gross_cents" | "gift_count"): Datum[] {
  const rows = s.by_program.map((p, i) => ({
    key: p.program,
    label: p.program,
    value: p[metric],
    color: seriesColor(i),
    detail: `${p.gift_count} gifts · ${dollars(p.gross_cents)}`,
  }));
  if (rows.length <= 8) return rows;
  const rest = rows.slice(7);
  return [
    ...rows.slice(0, 7),
    {
      key: "__other",
      label: `Other (${rest.length})`,
      value: rest.reduce((t, d) => t + d.value, 0),
      color: seriesColor(7),
    },
  ];
}

type MemberMetric = "gross_cents" | "donors_owned" | "open_reminders";

function SummaryCharts({
  s,
  program,
  setProgram,
  member,
  setMember,
}: {
  s: Summary;
  program: string | null;
  setProgram: (k: string | null) => void;
  member: string | null;
  setMember: (k: string | null) => void;
}) {
  const [pMetric, setPMetric] = useState<"gross_cents" | "gift_count">("gross_cents");
  const [mMetric, setMMetric] = useState<MemberMetric>("gross_cents");
  const members: Datum[] = s.by_board_member.map((b) => ({
    key: String(b.member.id),
    label: b.member.display_name + (b.member.is_active ? "" : " (inactive)"),
    value: b[mMetric],
    color: "var(--color-forest)",
    detail: `${b.donors_owned} donors · ${dollars(b.gross_cents)} · ${b.open_reminders} reminders`,
  }));
  return (
    <div className="dash-grid">
      <ChartTile
        title="Giving by program"
        note="Last 12 months · click a slice to highlight"
        controls={
          <Toggle
            label="Program measure"
            value={pMetric}
            onChange={setPMetric}
            options={[
              ["gross_cents", "Total"],
              ["gift_count", "Gifts"],
            ]}
          />
        }
      >
        <Donut
          data={programData(s, pMetric)}
          format={pMetric === "gross_cents" ? dollars : count}
          selected={program}
          onSelect={setProgram}
        />
      </ChartTile>
      <ChartTile
        title="Board members"
        note="Donors they steward · click a bar to highlight"
        controls={
          <Toggle
            label="Board member measure"
            value={mMetric}
            onChange={setMMetric}
            options={[
              ["gross_cents", "Giving"],
              ["donors_owned", "Donors"],
              ["open_reminders", "Reminders"],
            ]}
          />
        }
      >
        <Bars
          data={members}
          format={mMetric === "gross_cents" ? dollars : count}
          selected={member}
          onSelect={setMember}
        />
      </ChartTile>
    </div>
  );
}

function SummarySection({ s }: { s: Summary }) {
  const [program, setProgram] = useState<string | null>(null);
  const [member, setMember] = useState<string | null>(null);
  const periods = [
    ["This month", s.this_month],
    ["This quarter", s.this_quarter],
    ["Last 12 months", s.last_12_months],
  ] as const;
  return (
    <section className="report-section" aria-labelledby="summary-heading">
      <header className="queue-heading">
        <div>
          <p className="eyebrow">01 / The ledger at a glance</p>
          <h2 id="summary-heading">Giving summary</h2>
        </div>
        <p>As of {calendarDate(s.as_of)}</p>
      </header>
      <dl className="period-ledger">
        {periods.map(([label, p]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd className="numeric">
              <strong>{dollars(p.gross_cents)}</strong>
              {p.gift_count} gifts · {p.donor_count} donors
            </dd>
          </div>
        ))}
      </dl>
      <p className="report-footnote">
        Totals are organization revenue and include employer matches. Donor counts and board-member
        giving count employee donations only.
      </p>
      <p className="report-callouts">
        <Link to="/">
          {s.open_reminders} open reminders <ArrowUpRight size={14} aria-hidden="true" />
        </Link>
        <Link to="/review">
          {s.unattributed_gifts} anonymous gifts to attribute{" "}
          <ArrowUpRight size={14} aria-hidden="true" />
        </Link>
      </p>
      <SummaryCharts
        s={s}
        program={program}
        setProgram={setProgram}
        member={member}
        setMember={setMember}
      />
      <div className="report-tables">
        <table className="report-table">
          <caption>By program, last 12 months</caption>
          <thead>
            <tr>
              <th scope="col">Program</th>
              <th scope="col">Gifts</th>
              <th scope="col">Total</th>
            </tr>
          </thead>
          <tbody>
            {s.by_program.length ? (
              s.by_program.map((p) => (
                <tr key={p.program} className={program === p.program ? "is-selected" : undefined}>
                  <th scope="row">{p.program}</th>
                  <td className="numeric">{p.gift_count}</td>
                  <td className="numeric">{dollars(p.gross_cents)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3}>No gifts recorded in the last 12 months.</td>
              </tr>
            )}
          </tbody>
        </table>
        <table className="report-table">
          <caption>By board member, donors they steward</caption>
          <thead>
            <tr>
              <th scope="col">Member</th>
              <th scope="col">Donors</th>
              <th scope="col">Giving</th>
              <th scope="col">Open reminders</th>
            </tr>
          </thead>
          <tbody>
            {s.by_board_member.map((b) => (
              <tr
                key={b.member.id}
                className={member === String(b.member.id) ? "is-selected" : undefined}
              >
                <th scope="row">
                  {b.member.display_name}
                  {!b.member.is_active && <small> · inactive</small>}
                </th>
                <td className="numeric">{b.donors_owned}</td>
                <td className="numeric">{dollars(b.gross_cents)}</td>
                <td className="numeric">{b.open_reminders}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RetentionSection() {
  const [basis, setBasis] = useState<Retention["basis"]>("rolling");
  const [asOf, setAsOf] = useState("");
  const [picked, setPicked] = useState<string | null>(null);
  const query = useRetention(basis, asOf);
  const r = query.data;
  const classData = (field: "donors" | "cents_cur"): Datum[] =>
    CLASSES.map(([c, label, help], i) => ({
      key: String(c),
      label,
      value: (r?.classes[c] ?? NONE)[field],
      color: seriesColor(i),
      detail: help,
    }));
  const pick = setPicked;
  const most = r ? Math.max(1, ...CLASSES.map(([c]) => (r.classes[c] ?? NONE).donors)) : 1;
  return (
    <section
      className="report-section"
      aria-labelledby="retention-heading"
      aria-busy={query.isFetching}
    >
      <header className="queue-heading">
        <div>
          <p className="eyebrow">02 / Who stayed, who drifted</p>
          <h2 id="retention-heading">Donor retention</h2>
        </div>
        {r && <p>As of {calendarDate(r.as_of)}</p>}
      </header>
      <div className="retention-controls">
        <div className="segmented-control" role="group" aria-label="Compare">
          <button aria-pressed={basis === "rolling"} onClick={() => setBasis("rolling")}>
            Last 12 months vs previous 12
          </button>
          <button aria-pressed={basis === "calendar"} onClick={() => setBasis("calendar")}>
            Calendar year vs last year
          </button>
        </div>
        <label>
          As of
          <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} />
        </label>
      </div>
      {query.isPending ? (
        <LoadingLedger label="Loading retention" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <div className="dash-grid retention-charts">
            <ChartTile title="Donors by group" note="Click a slice to open that group below">
              <Donut data={classData("donors")} format={count} selected={picked} onSelect={pick} />
            </ChartTile>
            <ChartTile
              title="Giving this period by group"
              note="Shares the selection with the donut"
            >
              <Bars
                data={classData("cents_cur")}
                format={dollars}
                selected={picked}
                onSelect={pick}
              />
            </ChartTile>
          </div>
          <ol className="retention-ledger">
            {CLASSES.map(([c, label, help]) => {
              const k = r!.classes[c] ?? NONE;
              const donors = r!.donors[c] ?? [];
              return (
                <li key={c} className={picked === String(c) ? "is-selected" : undefined}>
                  <details
                    open={picked === String(c)}
                    onToggle={(e) => {
                      const open = e.currentTarget.open;
                      if (open && picked !== String(c)) setPicked(String(c));
                      if (!open && picked === String(c)) setPicked(null);
                    }}
                  >
                    <summary>
                      <span className="retention-name">
                        <strong>{label}</strong>
                        <small>{help}</small>
                      </span>
                      <span className="retention-count numeric">
                        {k.donors} <small>donors</small>
                      </span>
                      <span className="retention-bar" aria-hidden="true">
                        <span style={{ width: `${(k.donors / most) * 100}%` }} />
                      </span>
                      <span className="retention-cents numeric">
                        {dollars(k.cents_cur)}
                        <small>
                          {dollars(k.cents_prev)} before · {movement(k.cents_cur - k.cents_prev)}
                        </small>
                      </span>
                    </summary>
                    {donors.length ? (
                      <ul className="retention-donors">
                        {donors.map((d) => (
                          <li key={d.donor_id}>
                            <Link to={`/donors/${d.donor_id}`}>{d.display_name}</Link>
                            <span className="numeric">
                              {dollars(d.cents_cur)} <small>vs {dollars(d.cents_prev)}</small>
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="retention-empty">No donors in this group.</p>
                    )}
                  </details>
                </li>
              );
            })}
          </ol>
          <p className="report-footnote">
            Employee donations only; employer matches are excluded from retention. Open a group to
            see its donors.
          </p>
        </>
      )}
    </section>
  );
}

export function ReportsPage() {
  const summary = useReportSummary();
  useEffect(() => {
    document.title = "Reports · CIC Compass";
  }, []);
  return (
    <div className="reports-desk">
      <PageMasthead eyebrow="The stewardship ledger / Reports" title="How the circle is holding.">
        Giving, by period, program and steward, and which relationships grew, held or went quiet.
      </PageMasthead>
      {summary.isPending ? (
        <LoadingLedger label="Loading the giving summary" />
      ) : summary.isError ? (
        <ErrorState error={summary.error} retry={() => void summary.refetch()} />
      ) : (
        <SummarySection s={summary.data} />
      )}
      <RetentionSection />
    </div>
  );
}
