const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const date = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "America/Phoenix",
});

export function dollars(cents: number) {
  return money.format(cents / 100);
}

export function calendarDate(value?: string | null, fallback = "Not recorded") {
  if (!value) return fallback;
  // Date-only values represent a Phoenix business date, not UTC midnight.
  const parsed = new Date(value.length === 10 ? `${value}T12:00:00-07:00` : value);
  return Number.isNaN(parsed.valueOf()) ? fallback : date.format(parsed);
}

export function initials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("");
}
