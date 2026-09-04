/** Indian digit grouping (##,##,###), matching the backend's own
 * `measurement.report.format_inr_whole` exactly -- never `Number()`/float
 * conversion, since these strings can carry more precision than a JS
 * double should be trusted with. */
export function formatInr(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const [whole, ] = String(value).split(".");
  const negative = whole.startsWith("-");
  const digits = negative ? whole.slice(1) : whole;
  let grouped: string;
  if (digits.length <= 3) {
    grouped = digits;
  } else {
    const last3 = digits.slice(-3);
    let rest = digits.slice(0, -3);
    const parts: string[] = [];
    while (rest.length > 2) {
      parts.unshift(rest.slice(-2));
      rest = rest.slice(0, -2);
    }
    if (rest) parts.unshift(rest);
    grouped = [...parts, last3].join(",");
  }
  return `₹ ${negative ? "-" : ""}${grouped}`;
}

/** Decimal division (e.g. cost per rupee recovered) can carry far more
 * digits than are meaningful to show -- round for display only, never for
 * anything that feeds back into a computation. */
export function formatRatio(value: string | null | undefined, digits = 4): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

const _ACRONYMS: Record<string, string> = {
  sms: "SMS",
  otp: "OTP",
  upi: "UPI",
  ev: "EV",
  ptp: "PTP",
  b2b: "B2B",
  cuped: "CUPED",
  llm: "LLM",
  api: "API",
  sla: "SLA",
  id: "ID",
};

/** Domain enums travel the wire as snake_case (`card_expired_or_invalid`,
 * `sure_thing`, `whatsapp`) -- fine for logs and code, not for a screen.
 * Title-cases each word and upper-cases known channel/protocol acronyms. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .split("_")
    .map((word) => _ACRONYMS[word.toLowerCase()] ?? word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
