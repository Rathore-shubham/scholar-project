import { describe, expect, it } from "vitest";

import { NOT_AVAILABLE, awardNumeric, dateLabel, eligibilityHint, hostOf, joinList, money, truncate } from "@/lib/format";
import { profileCompletion } from "@/features/scholarpath/data";

describe("format helpers", () => {
  it("formats rupees with Indian digit grouping", () => {
    expect(money(450000)).toBe("₹4,50,000");
    expect(money(12000)).toBe("₹12,000");
  });

  it("shows a numeric award only when the source gave one", () => {
    expect(awardNumeric({ award_amount_min: null, award_amount_max: null })).toBeNull();
    expect(awardNumeric({ award_amount_min: 50000, award_amount_max: 50000 })).toBe("₹50,000");
    expect(awardNumeric({ award_amount_min: 20000, award_amount_max: 80000 })).toBe("₹20,000 – ₹80,000");
  });

  it("reports missing dates as unavailable, never as a made-up date", () => {
    expect(dateLabel(null)).toBe(NOT_AVAILABLE);
    expect(dateLabel("")).toBe(NOT_AVAILABLE);
    expect(dateLabel("not a date")).toBe(NOT_AVAILABLE);
    expect(dateLabel("2026-10-25")).toBe("25 Oct 2026");
  });

  it("truncates long text and lists values", () => {
    expect(truncate("x".repeat(200), 20)).toHaveLength(20);
    expect(truncate("short", 20)).toBe("short");
    expect(joinList(["a", "b"])).toBe("a, b");
    expect(joinList([])).toBe(NOT_AVAILABLE);
    expect(hostOf("https://scholarships.gov.in/path")).toBe("scholarships.gov.in");
  });

  it("card hints never claim eligibility from unverified rules", () => {
    expect(eligibilityHint(undefined)).toMatch(/Checking/);
    expect(eligibilityHint({ outcome: "cant_tell_yet", indicative: "all_listed_criteria_met" })).toMatch(/unverified, so this is not a confirmation/);
    expect(eligibilityHint({ outcome: "cant_tell_yet", indicative: "some_criteria_not_met" })).toMatch(/does not match/);
    expect(eligibilityHint({ outcome: "eligible" })).toMatch(/reviewed requirement/);
  });

  it("profile completion counts only the eight core fields", () => {
    expect(profileCompletion({})).toBe(0);
    expect(profileCompletion({ name: "A", dob: "2000-01-01", state: "Goa", education: "Class 12" })).toBe(50);
    expect(profileCompletion({ name: " ", preference: "Central" })).toBe(0);
  });
});
