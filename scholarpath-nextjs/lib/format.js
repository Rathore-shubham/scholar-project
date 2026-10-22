// Display helpers. Anything the API reports as unavailable stays visibly unavailable: nothing is invented.

import { VERIFICATION_LABELS } from "@/features/scholarpath/data";

export const NOT_AVAILABLE = "Not available";

export function money(n) {
  return "₹" + Number(n).toLocaleString("en-IN");
}

/** Numeric award (single value or range) when the source gave one, else null. */
export function awardNumeric(s) {
  const { award_amount_min: min, award_amount_max: max } = s;
  if (min == null && max == null) return null;
  if (min != null && max != null && min !== max) return `${money(min)} – ${money(max)}`;
  return money(min ?? max);
}

export function truncate(text, length) {
  if (!text) return text;
  return text.length > length ? `${text.slice(0, length - 1).trimEnd()}…` : text;
}

/** "2026-10-25" -> "25 Oct 2026"; null/invalid -> "Not available". */
export function dateLabel(value) {
  if (!value) return NOT_AVAILABLE;
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return NOT_AVAILABLE;
  return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function verificationLabel(status) {
  return VERIFICATION_LABELS[status] || status;
}

export function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function joinList(values, empty = NOT_AVAILABLE) {
  return values && values.length ? values.join(", ") : empty;
}

/** One-sentence summary for a card from the API's indicative hint (never claims eligibility). */
export function eligibilityHint(result) {
  if (!result) return "Checking your details against this scholarship…";
  if (result.outcome === "eligible") return "Your details meet every reviewed requirement on record.";
  if (result.outcome === "not_eligible") return "A reviewed requirement does not match your details.";
  switch (result.indicative) {
    case "all_listed_criteria_met":
      return "Your details match the listed criteria, but they are unverified, so this is not a confirmation.";
    case "some_criteria_not_met":
      return "A listed criterion does not match your details (unverified). Open the details to see which.";
    case "no_criteria_listed":
      return "No eligibility criteria are on record for this scholarship.";
    default:
      return "Add or review your details, and check the official source, to learn more.";
  }
}
