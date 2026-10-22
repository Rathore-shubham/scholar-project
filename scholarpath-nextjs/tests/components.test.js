import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { CriteriaTable, EligibilityResultPanel } from "@/features/scholarpath/profile";
import { ScholarProvider, useScholar } from "@/features/scholarpath/store";
import { ErrorState, EligibilityBadge, LoadingList, ScholarshipCard, VerificationBadge } from "@/features/scholarpath/ui";
import { criterionResult, eligibilityResult, renderWithStore, summary } from "./helpers";

describe("ScholarshipCard", () => {
  it("labels a pending record as unverified and shows unavailable information as unavailable", () => {
    renderWithStore(<ScholarshipCard scholarship={summary()} eligibility={eligibilityResult()} />);
    expect(screen.getByRole("heading", { name: "Alpha Merit Scholarship (test fixture)" })).toBeInTheDocument();
    expect(screen.getByText("Central scheme · Unverified source data")).toBeInTheDocument();
    expect(screen.getAllByText("Unverified").length).toBeGreaterThan(0);
    expect(screen.getByText("Not available")).toBeInTheDocument(); // no deadline in the data: never invented
    expect(screen.getByText("Amount not specified")).toBeInTheDocument();
    expect(screen.getByText("Class 12, Undergraduate")).toBeInTheDocument();
    expect(screen.getByText(/Can't Tell Yet/)).toBeInTheDocument();
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });

  it("links to the detail page by the stable scholarship id", () => {
    renderWithStore(<ScholarshipCard scholarship={summary({ scholarship_id: "SP-ABC123" })} />);
    expect(screen.getByRole("link", { name: "Alpha Merit Scholarship (test fixture)" })).toHaveAttribute("href", "/scholarships/SP-ABC123");
    expect(screen.getByRole("link", { name: /View Details/ })).toHaveAttribute("href", "/scholarships/SP-ABC123");
  });

  it("shows the numeric award and the source's benefit text when both exist", () => {
    renderWithStore(<ScholarshipCard scholarship={summary({ award_amount_min: 12000, award_amount_max: 12000, award_amount_text: "₹12,000 per annum from Class 9 to 12" })} />);
    expect(screen.getByText("₹12,000", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("₹12,000 per annum from Class 9 to 12")).toBeInTheDocument();
  });

  it("uses a deadline only when the API supplies one", () => {
    renderWithStore(<ScholarshipCard scholarship={summary({ application_deadline: "2026-12-01" })} />);
    expect(screen.getByText("1 Dec 2026")).toBeInTheDocument();
    expect(screen.queryByText("Not available")).not.toBeInTheDocument();
  });

  it("marks a verified record as verified", () => {
    renderWithStore(<ScholarshipCard scholarship={summary({ verification_status: "verified", is_verified: true })} />);
    expect(screen.getByText("Central scheme · Verified")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
  });

  it("explains an eligibility failure without breaking the card", () => {
    renderWithStore(<ScholarshipCard scholarship={summary()} eligibilityFailed />);
    expect(screen.getByText("Not checked")).toBeInTheDocument();
    expect(screen.getByText(/could not be checked right now/)).toBeInTheDocument();
  });

  it("saves and unsaves, and persists the choice in this browser only", async () => {
    const user = userEvent.setup();
    renderWithStore(<ScholarshipCard scholarship={summary({ scholarship_id: "SP-S1" })} />);
    await user.click(screen.getByRole("button", { name: /^Save Alpha Merit/ }));
    expect(screen.getByRole("button", { name: /^Unsave Alpha Merit/ })).toBeInTheDocument();
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("scholarpath.workspace.v2")).saved).toEqual(["SP-S1"]));
    await user.click(screen.getByRole("button", { name: /^Unsave Alpha Merit/ }));
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("scholarpath.workspace.v2")).saved).toEqual([]));
  });
});

describe("state components", () => {
  it("LoadingList is an accessible status with placeholders only", () => {
    render(<LoadingList count={3} label="Loading scholarships" />);
    const region = screen.getByRole("status", { name: "Loading scholarships" });
    expect(region.querySelectorAll(".skeleton-card")).toHaveLength(3);
  });

  it.each([
    ["database_not_configured", /scholarship database is not set up yet/i, /Configure PostgreSQL Later/],
    ["database_unavailable", /scholarship database is unavailable/i, /PostgreSQL/],
    ["database_not_migrated", /database has no tables yet/i, /alembic upgrade head/],
    ["network_error", /Can't reach the ScholarPath API/, /127\.0\.0\.1:8001/],
  ])("ErrorState explains %s and offers a retry", async (code, title, message) => {
    const retry = vi.fn();
    render(<ErrorState error={new ApiError({ status: 503, code, message: "technical" })} onRetry={retry} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.getByText(`Error code: ${code}`)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: /Try again/ }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("ErrorState offers no retry for a not-found error", () => {
    render(<ErrorState error={new ApiError({ status: 404, code: "scholarship_not_found", message: "gone" })} onRetry={() => {}} />);
    expect(screen.queryByRole("button", { name: /Try again/ })).not.toBeInTheDocument();
  });

  it("badges use words, not only colour", () => {
    render(
      <>
        <EligibilityBadge outcome="eligible" />
        <EligibilityBadge outcome="not_eligible" />
        <EligibilityBadge outcome="cant_tell_yet" />
        <VerificationBadge status="pending" />
        <VerificationBadge status="needs_review" />
      </>,
    );
    for (const label of ["Eligible", "Not Eligible", "Can't Tell Yet", "Unverified", "Needs review"]) expect(screen.getByText(label)).toBeInTheDocument();
  });
});

describe("eligibility result display", () => {
  it("shows every criterion with required value, your value, status, explanation and source", () => {
    const criteria = [
      criterionResult(),
      criterionResult({ criterion_type: "category", criterion: "Category", required: "Category: SC, ST", student_value: "General", status: "fail", explanation: "Your category (General) is not among the listed categories (SC, ST)." }),
      criterionResult({ criterion_type: "minimum_percentage", criterion: "Minimum academic percentage", required: "At least 60%", student_value: null, status: "missing", explanation: "Add your academic percentage to check this requirement." }),
      criterionResult({ criterion_type: "other_rule", criterion: "Other condition (as stated in source)", required: "As stated in the source: x", student_value: null, status: "unable_to_verify", explanation: "The source states this condition only as text.", is_mandatory: false }),
      criterionResult({ criterion: "Reviewed one", reliable: true, review_status: "reviewed", evidence: { text: null, url: "https://example.gov.in/notice", source_ref: null } }),
    ];
    render(<CriteriaTable criteria={criteria} />);
    expect(screen.getAllByText("Meets requirement")).toHaveLength(2);
    expect(screen.getByText("Does not meet requirement")).toBeInTheDocument();
    expect(screen.getByText("Information missing")).toBeInTheDocument();
    expect(screen.getByText("Unable to verify")).toBeInTheDocument();
    expect(screen.getByText("Required: Category: SC, ST")).toBeInTheDocument();
    expect(screen.getByText("Your value: General")).toBeInTheDocument();
    expect(screen.getAllByText("Your value: Not provided")).toHaveLength(2);
    expect(screen.getByText("Your category (General) is not among the listed categories (SC, ST).")).toBeInTheDocument();
    expect(screen.getByText("(optional)")).toBeInTheDocument();
    expect(screen.getAllByText(/Unreviewed rule/)).toHaveLength(4);
    expect(screen.getByText(/Reviewed rule/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Source/ })).toHaveAttribute("href", "https://example.gov.in/notice");
    expect(screen.getAllByText(/Extracted from fixture.xlsx \/ Sheet1 \/ row 2; no source citation on record/).length).toBeGreaterThan(0);
  });

  it("an empty criteria list says so instead of implying a pass", () => {
    render(<CriteriaTable criteria={[]} />);
    expect(screen.getByText(/No eligibility criteria are on record/)).toBeInTheDocument();
  });

  it("cant_tell_yet panel states the limitation and what to add", () => {
    render(<EligibilityResultPanel result={eligibilityResult({ missing_information: ["family_income", "percentage"] })} />);
    expect(screen.getByRole("heading", { name: "Can't Tell Yet" })).toBeInTheDocument();
    expect(screen.getByText(/This record has not been verified/)).toBeInTheDocument();
    expect(screen.getByText(/add: family income, percentage/)).toBeInTheDocument();
    expect(screen.getByText(/not an official eligibility decision/)).toBeInTheDocument();
  });

  it("renders eligible and not_eligible outcomes from the backend faithfully", () => {
    const reliable = { verification_status: "verified", mandatory_criteria: 1, reviewed_mandatory_criteria: 1, supported_mandatory_criteria: 1, rules_reliable: true };
    const { rerender } = render(<EligibilityResultPanel result={eligibilityResult({ outcome: "eligible", summary: "Eligible: every mandatory criterion on record is met, reviewed and supported by evidence.", basis: reliable, limitations: [] })} />);
    expect(screen.getByRole("heading", { name: "Eligible" })).toBeInTheDocument();
    expect(screen.getByText(/Every mandatory rule is reviewed and backed by evidence/)).toBeInTheDocument();
    expect(screen.queryByText(/not an official eligibility decision/)).not.toBeInTheDocument();
    rerender(<EligibilityResultPanel result={eligibilityResult({ outcome: "not_eligible", summary: "Not eligible: a reviewed mandatory criterion is not met (Category).", basis: reliable, limitations: [] })} />);
    expect(screen.getByRole("heading", { name: "Not Eligible" })).toBeInTheDocument();
    expect(screen.getByText(/reviewed mandatory criterion is not met/)).toBeInTheDocument();
  });
});

function StoreProbe() {
  const { profile, saved, applications, toggleSave, setStatus, saveProfile, ready } = useScholar();
  return (
    <div>
      <span data-testid="ready">{String(ready)}</span>
      <span data-testid="name">{profile.name}</span>
      <span data-testid="saved">{JSON.stringify(saved)}</span>
      <span data-testid="apps">{JSON.stringify(applications)}</span>
      <button onClick={() => toggleSave("SP-1")}>save good</button>
      <button onClick={() => toggleSave("bad id!")}>save bad</button>
      <button onClick={() => setStatus("SP-1", "Applied")}>apply good</button>
      <button onClick={() => setStatus("SP-1", "Hacked")}>apply bad</button>
      <button onClick={() => saveProfile({ name: "A" })}>save invalid profile</button>
    </div>
  );
}

describe("browser store", () => {
  it("starts empty: no demo student, no pre-saved or pre-tracked scholarships", async () => {
    render(<ScholarProvider><StoreProbe /></ScholarProvider>);
    await waitFor(() => expect(screen.getByTestId("ready")).toHaveTextContent("true"));
    expect(screen.getByTestId("name")).toHaveTextContent("");
    expect(screen.getByTestId("saved")).toHaveTextContent("[]");
    expect(screen.getByTestId("apps")).toHaveTextContent("{}");
  });

  it("restores valid saved data and ignores corrupt or tampered data", async () => {
    window.localStorage.setItem("scholarpath.workspace.v2", JSON.stringify({ profile: { name: "Asha" }, saved: ["SP-9"], applications: { "SP-9": { status: "Applied", updated: "2026-10-01" } } }));
    const { unmount } = render(<ScholarProvider><StoreProbe /></ScholarProvider>);
    await waitFor(() => expect(screen.getByTestId("name")).toHaveTextContent("Asha"));
    expect(screen.getByTestId("saved")).toHaveTextContent('["SP-9"]');
    unmount();

    window.localStorage.setItem("scholarpath.workspace.v2", JSON.stringify({ profile: {}, saved: ["<script>"], applications: {} }));
    render(<ScholarProvider><StoreProbe /></ScholarProvider>);
    await waitFor(() => expect(screen.getByTestId("ready")).toHaveTextContent("true"));
    expect(screen.getByTestId("saved")).toHaveTextContent("[]");
  });

  it("ignores the old prototype's storage key (v1 held mock scholarship ids)", async () => {
    window.localStorage.setItem("scholarpath.prototype.v1", JSON.stringify({ saved: ["national-merit"] }));
    render(<ScholarProvider><StoreProbe /></ScholarProvider>);
    await waitFor(() => expect(screen.getByTestId("ready")).toHaveTextContent("true"));
    expect(screen.getByTestId("saved")).toHaveTextContent("[]");
  });

  it("validates ids, statuses and profiles before storing them", async () => {
    const user = userEvent.setup();
    render(<ScholarProvider><StoreProbe /></ScholarProvider>);
    await user.click(screen.getByText("save bad"));
    await user.click(screen.getByText("apply bad"));
    await user.click(screen.getByText("save invalid profile"));
    expect(screen.getByTestId("saved")).toHaveTextContent("[]");
    expect(screen.getByTestId("apps")).toHaveTextContent("{}");
    expect(screen.getByTestId("name")).toHaveTextContent("");
    await user.click(screen.getByText("save good"));
    await user.click(screen.getByText("apply good"));
    expect(screen.getByTestId("saved")).toHaveTextContent('["SP-1"]');
    expect(within(screen.getByTestId("apps")).getByText(/"status":"Applied"/)).toBeInTheDocument();
  });
});
