import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Applications } from "@/features/scholarpath/applications";
import { Dashboard } from "@/features/scholarpath/dashboard";
import { Details } from "@/features/scholarpath/details";
import { Discovery, Saved } from "@/features/scholarpath/discovery";
import { ProfileForm } from "@/features/scholarpath/profile";
import { routerPush } from "./setup";
import {
  criterionResult,
  detail,
  eligibilityResult,
  errorBody,
  filterOptions,
  isDetail,
  isEligibility,
  isFilters,
  isList,
  jsonResponse,
  listPage,
  mockFetch,
  renderWithStore,
  summary,
} from "./helpers";

const ALPHA = summary({ scholarship_id: "SP-T1", name: "Alpha Merit Scholarship (test fixture)" });
const BETA = summary({ scholarship_id: "SP-T2", name: "Beta State Scholarship (test fixture)", scheme_type: "state" });

function eligibilityFor(body) {
  return { results: JSON.parse(body).scholarship_ids.map((id) => eligibilityResult({ scholarship_id: id })), not_found: [] };
}

function api({ list, detailResponse, check, filters } = {}) {
  const handlers = [
    [isFilters, () => filters ?? filterOptions],
    [isEligibility, (_u, init) => (check ? check(init) : eligibilityFor(init.body))],
    [isDetail, (url) => (detailResponse ? detailResponse(url) : detail())],
    [isList, (url) => (list ? list(url) : listPage([ALPHA, BETA]))],
  ];
  return mockFetch(handlers);
}

const listCalls = (fetchMock) => fetchMock.mock.calls.map(([url]) => String(url)).filter((u) => isList(u) && !isDetail(u));
const lastList = (fetchMock) => new URL(listCalls(fetchMock).at(-1));

describe("Discovery (Find Scholarships)", () => {
  it("shows a loading state, then the scholarships from the API", async () => {
    const fetchMock = api();
    renderWithStore(<Discovery />);
    expect(screen.getByRole("status", { name: "Loading scholarships" })).toBeInTheDocument();
    expect(await screen.findByText("Alpha Merit Scholarship (test fixture)")).toBeInTheDocument();
    expect(screen.getByText("Beta State Scholarship (test fixture)")).toBeInTheDocument();
    expect(screen.getByText(/scholarships found/)).toHaveTextContent("2 scholarships found");
    const url = lastList(fetchMock);
    expect(url.pathname).toBe("/api/v1/scholarships");
    expect(Object.fromEntries(url.searchParams)).toEqual({ page: "1", page_size: "12", sort: "name" });
    expect(screen.getAllByText("Unverified").length).toBeGreaterThanOrEqual(2);
    expect(await screen.findAllByText("Can't Tell Yet", { selector: ".status" })).toHaveLength(2);
    expect(screen.getAllByText("Not available")).toHaveLength(2); // deadlines are unavailable, never made up
  });

  it("asks the API for eligibility of the visible scholarships with the saved profile", async () => {
    window.localStorage.setItem("scholarpath.workspace.v2", JSON.stringify({ profile: { state: "Madhya Pradesh", education: "Class 12", percentage: "70", income: "250000", category: "OBC", gender: "Female", name: "Asha" }, saved: [], applications: {} }));
    const fetchMock = api();
    renderWithStore(<Discovery />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => isEligibility(String(u), i) && JSON.parse(i.body).profile.state === "Madhya Pradesh")).toBe(true));
    const call = fetchMock.mock.calls.map(([u, i]) => [String(u), i]).filter(([u, i]) => isEligibility(u, i)).at(-1);
    expect(JSON.parse(call[1].body)).toEqual({
      profile: { state: "Madhya Pradesh", education_level: "Class 12", percentage: 70, family_income: 250000, category: "OBC", gender: "Female" },
      scholarship_ids: ["SP-T1", "SP-T2"],
    });
  });

  it("explains an empty database instead of showing placeholder records", async () => {
    api({ list: () => listPage([], { total: 0 }) });
    renderWithStore(<Discovery />);
    expect(await screen.findByText("No scholarships on record yet")).toBeInTheDocument();
    expect(screen.getByText(/contains no scholarship records/)).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("reports 'no results' for a search and can clear it", async () => {
    const user = userEvent.setup();
    const fetchMock = api({ list: (url) => (new URL(url).searchParams.get("q") ? listPage([], { total: 0 }) : listPage([ALPHA, BETA])) });
    renderWithStore(<Discovery />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    await user.type(screen.getByLabelText("Search scholarships"), "zzz");
    expect(await screen.findByText("No scholarships found", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(lastList(fetchMock).searchParams.get("q")).toBe("zzz");
    await user.click(screen.getByRole("button", { name: "Clear search and filters" }));
    expect(await screen.findByText("Alpha Merit Scholarship (test fixture)")).toBeInTheDocument();
  });

  it("shows the backend's database-not-configured error with a working retry, and never any scholarship", async () => {
    let calls = 0;
    api({
      list: () => {
        calls += 1;
        return calls === 1 ? jsonResponse(errorBody("database_not_configured", "The database is not configured on the server."), 503) : listPage([ALPHA]);
      },
    });
    const user = userEvent.setup();
    renderWithStore(<Discovery />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/scholarship database is not set up yet/i);
    expect(screen.getByText("Error code: database_not_configured")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Merit Scholarship (test fixture)")).not.toBeInTheDocument();
    expect(screen.getByText("Scholarships could not be loaded")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByText("Alpha Merit Scholarship (test fixture)")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a network error when the backend is not running", async () => {
    mockFetch([[isFilters, () => { throw new TypeError("Failed to fetch"); }], [isList, () => { throw new TypeError("Failed to fetch"); }]]);
    renderWithStore(<Discovery />);
    expect(await screen.findByRole("heading", { name: "Can't reach the ScholarPath API" })).toBeInTheDocument();
    expect(screen.getByText(/uvicorn app.main:app --port 8001/)).toBeInTheDocument();
  });

  it("keeps listing scholarships when only the eligibility call fails", async () => {
    api({ check: () => jsonResponse(errorBody("database_unavailable", "down"), 503) });
    renderWithStore(<Discovery />);
    expect(await screen.findByText("Alpha Merit Scholarship (test fixture)")).toBeInTheDocument();
    expect(await screen.findAllByText("Not checked")).toHaveLength(2);
  });

  it("loads more pages and appends them", async () => {
    const page1 = Array.from({ length: 12 }, (_, i) => summary({ scholarship_id: `SP-A${i}`, name: `Item ${i} (test fixture)` }));
    const page2 = [summary({ scholarship_id: "SP-B1", name: "Item 12 (test fixture)" }), summary({ scholarship_id: "SP-B2", name: "Item 13 (test fixture)" })];
    const fetchMock = api({ list: (url) => (new URL(url).searchParams.get("page") === "2" ? listPage(page2, { total: 14, page: 2 }) : listPage(page1, { total: 14 })) });
    const user = userEvent.setup();
    renderWithStore(<Discovery />);
    await screen.findByText("Item 0 (test fixture)");
    expect(screen.getByRole("button", { name: "Load More (12 of 14)" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Load More (12 of 14)" }));
    expect(await screen.findByText("Item 13 (test fixture)")).toBeInTheDocument();
    expect(screen.getByText("Item 0 (test fixture)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Load More/ })).not.toBeInTheDocument();
    expect(lastList(fetchMock).searchParams.get("page")).toBe("2");
  });

  it("turns the filter form into API parameters", async () => {
    const fetchMock = api();
    const user = userEvent.setup();
    renderWithStore(<Discovery />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    await user.click(screen.getByRole("button", { name: /Filters/ }));
    await waitFor(() => expect(within(screen.getByRole("combobox", { name: /^State/ })).getByText("Madhya Pradesh")).toBeInTheDocument()); // options come from the API
    await user.selectOptions(screen.getByRole("combobox", { name: /^State/ }), "Madhya Pradesh");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Education Level/ }), "UG");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Category/ }), "OBC");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Scheme Level/ }), "state");
    await user.selectOptions(screen.getByRole("combobox", { name: /^Verification/ }), "verified");
    await user.type(screen.getByLabelText("Your Academic Percentage"), "72");
    await user.click(screen.getByRole("button", { name: "Apply Filters" }));
    await waitFor(() => expect(lastList(fetchMock).searchParams.get("state")).toBe("Madhya Pradesh"));
    expect(Object.fromEntries(lastList(fetchMock).searchParams)).toMatchObject({
      state: "Madhya Pradesh", education_level: "UG", category: "OBC", scheme_type: "state", verified_only: "true", student_percentage: "72", page: "1",
    });
    expect(screen.getByRole("button", { name: /Filters \(6\)/ })).toBeInTheDocument();
  });

  it("sorts through the API", async () => {
    const fetchMock = api();
    const user = userEvent.setup();
    renderWithStore(<Discovery />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    await user.selectOptions(screen.getByRole("combobox", { name: /Sort scholarships/ }), "amount_desc");
    await waitFor(() => expect(lastList(fetchMock).searchParams.get("sort")).toBe("amount_desc"));
    await user.selectOptions(screen.getByRole("combobox", { name: /Sort scholarships/ }), "deadline");
    expect(await screen.findByText(/no application deadlines/)).toBeInTheDocument();
  });

  it("starts from the ?q= search term handed over by the dashboard", async () => {
    const fetchMock = api();
    renderWithStore(<Discovery initialQuery="merit" />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    expect(lastList(fetchMock).searchParams.get("q")).toBe("merit");
    expect(screen.getByLabelText("Search scholarships")).toHaveValue("merit");
  });
});

describe("Saved and Applications", () => {
  const seed = (extra) => window.localStorage.setItem("scholarpath.workspace.v2", JSON.stringify({ profile: {}, saved: [], applications: {}, ...extra }));

  it("saved: an empty shortlist makes no API call", () => {
    const fetchMock = api();
    renderWithStore(<Saved />);
    expect(screen.getByText("You haven't saved any scholarships yet.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("saved: fetches the saved ids and reports ones that no longer exist", async () => {
    seed({ saved: ["SP-T1", "SP-GONE"] });
    const fetchMock = api({ list: () => listPage([ALPHA]) });
    const user = userEvent.setup();
    renderWithStore(<Saved />);
    expect(await screen.findByText("Alpha Merit Scholarship (test fixture)")).toBeInTheDocument();
    expect(lastList(fetchMock).searchParams.get("ids")).toBe("SP-T1,SP-GONE");
    expect(screen.getByRole("status")).toHaveTextContent("1 saved scholarship is no longer in the database.");
    await user.click(screen.getByRole("button", { name: "Remove it from my list" }));
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("scholarpath.workspace.v2")).saved).toEqual(["SP-T1"]));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("saved: removing a scholarship asks for confirmation first", async () => {
    seed({ saved: ["SP-T1"] });
    api({ list: () => listPage([ALPHA]) });
    const user = userEvent.setup();
    renderWithStore(<Saved />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    await user.click(screen.getByRole("button", { name: /Remove from Saved/ }));
    expect(screen.getByText("Remove saved scholarship?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("scholarpath.workspace.v2")).saved).toEqual([]));
  });

  it("saved: the eligibility filter works on the API's outcomes", async () => {
    seed({ saved: ["SP-T1"] });
    api({ list: () => listPage([ALPHA]) });
    const user = userEvent.setup();
    renderWithStore(<Saved />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    await screen.findByText(/unverified, so this is not a confirmation/);
    await user.selectOptions(screen.getByRole("combobox", { name: /Eligibility/ }), "eligible");
    expect(screen.getByText("No saved scholarships match these filters.")).toBeInTheDocument();
  });

  it("saved: API errors are shown with a retry", async () => {
    seed({ saved: ["SP-T1"] });
    api({ list: () => jsonResponse(errorBody("database_unavailable", "down"), 503) });
    renderWithStore(<Saved />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/unavailable/i);
    expect(screen.getByRole("button", { name: /Try again/ })).toBeInTheDocument();
  });

  it("applications: empty state when nothing is tracked", () => {
    api();
    renderWithStore(<Applications />);
    expect(screen.getByText("No applications tracked yet")).toBeInTheDocument();
    expect(screen.getByText(/not verified by scholarship providers/)).toBeInTheDocument();
  });

  it("applications: lists tracked scholarships, changes status, and never invents a deadline", async () => {
    seed({ applications: { "SP-T1": { status: "Preparing Documents", updated: "2026-10-09" } } });
    const fetchMock = api({ list: () => listPage([ALPHA]) });
    const user = userEvent.setup();
    renderWithStore(<Applications />);
    expect(await screen.findByRole("link", { name: "Alpha Merit Scholarship (test fixture)" })).toBeInTheDocument();
    expect(lastList(fetchMock).searchParams.get("ids")).toBe("SP-T1");
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("9 Oct 2026")).toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "Application status for Alpha Merit Scholarship (test fixture)" });
    expect(select).toHaveValue("Preparing Documents");
    await user.selectOptions(select, "Applied");
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("scholarpath.workspace.v2")).applications["SP-T1"].status).toBe("Applied"));
  });
});

describe("Details", () => {
  it("renders every section from the API and states what is unavailable", async () => {
    api({ detailResponse: () => detail({ award_amount_min: 12000, award_amount_max: 12000, award_amount_text: "₹12,000 per annum", criteria: [] }) });
    renderWithStore(<Details id="SP-T1" />);
    expect(screen.getByRole("status", { name: "Loading scholarship" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Alpha Merit Scholarship (test fixture)" })).toBeInTheDocument();
    for (const heading of ["Overview", "Eligibility Criteria", "Benefits and Scholarship Amount", "Required Documents", "Application Process", "Important Dates", "Official Source"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    }
    expect(screen.getByRole("note")).toHaveTextContent(/Unverified: this record was extracted from source data and has not been reviewed/);
    expect(screen.getByText(/does not list required documents/)).toBeInTheDocument();
    expect(screen.getByText(/does not describe the application steps/)).toBeInTheDocument();
    expect(screen.getByText(/No application dates are recorded/)).toBeInTheDocument();
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("Unverified (pending review)")).toBeInTheDocument();
    expect(screen.getByText("Not recorded (extracted from a local data file)")).toBeInTheDocument();
    expect(screen.getByText(/from fixture.xlsx · Sheet1 · row 2/)).toBeInTheDocument();
    expect(screen.getByText("Minimum percentage (as stated in source): MP BOARD-60")).toBeInTheDocument();
    expect(await screen.findByText("Required: Resident of: Madhya Pradesh")).toBeInTheDocument();
    expect(screen.getAllByText("Unreviewed rule", { exact: false }).length).toBeGreaterThan(0);
  });

  it("shows a clear not-found page without a retry loop", async () => {
    mockFetch([[isDetail, () => jsonResponse(errorBody("scholarship_not_found", "No scholarship with id 'SP-X'."), 404)], [isEligibility, () => ({ results: [], not_found: ["SP-X"] })]]);
    renderWithStore(<Details id="SP-X" />);
    expect(await screen.findByRole("heading", { name: "Scholarship not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Find Scholarships" })).toHaveAttribute("href", "/scholarships");
    expect(screen.queryByRole("button", { name: /Try again/ })).not.toBeInTheDocument();
  });

  it("shows API errors with retry", async () => {
    let calls = 0;
    api({ detailResponse: () => (++calls === 1 ? jsonResponse(errorBody("database_not_migrated", "tables missing"), 503) : detail()) });
    const user = userEvent.setup();
    renderWithStore(<Details id="SP-T1" />);
    expect(await screen.findByRole("heading", { name: /database has no tables yet/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByRole("heading", { name: "Alpha Merit Scholarship (test fixture)" })).toBeInTheDocument();
  });

  it("still shows the scholarship when only the eligibility check fails", async () => {
    api({ check: () => jsonResponse(errorBody("database_unavailable", "down"), 503), detailResponse: () => detail({ criteria: [{ criterion_type: "state", label: "State of residence", operator: "in", required_value: { values: ["Madhya Pradesh"] }, is_mandatory: true, review_status: "unreviewed", evidence_text: null, evidence_url: null, source_ref: null }] }) });
    renderWithStore(<Details id="SP-T1" />);
    expect(await screen.findByRole("heading", { name: "Alpha Merit Scholarship (test fixture)" })).toBeInTheDocument();
    expect(await screen.findByText("Eligibility could not be checked")).toBeInTheDocument();
    expect(screen.getByText(/State of residence: Madhya Pradesh/)).toBeInTheDocument();
  });

  it("requires confirmation before sending the user to the official site, and warns when unverified", async () => {
    api();
    const user = userEvent.setup();
    renderWithStore(<Details id="SP-T1" />);
    await user.click(await screen.findByRole("button", { name: /Apply on Official Website/ }));
    expect(screen.getByText("You are leaving ScholarPath AI")).toBeInTheDocument();
    expect(screen.getByText(/This opens scholarships.gov.in in a new tab/)).toBeInTheDocument();
    expect(screen.getByText(/This record is unverified/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Continue to official website/ });
    expect(link).toHaveAttribute("href", "https://scholarships.gov.in");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("disables the apply button and says why when no official URL is on record", async () => {
    api({ detailResponse: () => detail({ official_url: null }) });
    renderWithStore(<Details id="SP-T1" />);
    expect(await screen.findByRole("button", { name: /Apply on Official Website/ })).toBeDisabled();
    expect(screen.getByText("No official website is on record for this scholarship.")).toBeInTheDocument();
  });

  it("saves and tracks the scholarship (stored in this browser)", async () => {
    api();
    const user = userEvent.setup();
    renderWithStore(<Details id="SP-T1" />);
    await user.click(await screen.findByRole("button", { name: "Save Scholarship" }));
    expect(screen.getByRole("button", { name: "Saved Scholarship" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Track Application" }));
    expect(screen.getByRole("button", { name: "Application Tracked" })).toBeDisabled();
    await waitFor(() => {
      const stored = JSON.parse(window.localStorage.getItem("scholarpath.workspace.v2"));
      expect(stored.saved).toEqual(["SP-T1"]);
      expect(stored.applications["SP-T1"].status).toBe("Interested");
    });
  });

  it("shows a verified record's status without the unverified notice", async () => {
    api({ detailResponse: () => detail({ verification_status: "verified", is_verified: true, data_notice: null, last_verified_at: "2026-10-01" }), check: (init) => ({ results: [eligibilityResult({ outcome: "eligible", summary: "Eligible: every mandatory criterion on record is met, reviewed and supported by evidence.", basis: { verification_status: "verified", mandatory_criteria: 1, reviewed_mandatory_criteria: 1, supported_mandatory_criteria: 1, rules_reliable: true }, limitations: [], criteria: [criterionResult({ reliable: true, review_status: "reviewed", evidence: { text: "Official notification s.3", url: null, source_ref: null } })] })], not_found: [] }) });
    renderWithStore(<Details id="SP-T1" />);
    await screen.findByRole("heading", { name: "Alpha Merit Scholarship (test fixture)" });
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Eligible" })).toBeInTheDocument();
    expect(screen.getByText("1 Oct 2026", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText(/Source: Official notification s.3/)).toBeInTheDocument();
  });
});

describe("Eligibility checker", () => {
  it("lets the user pick a scholarship, sends only eligibility facts, and shows the backend's explanation", async () => {
    const fetchMock = api();
    const user = userEvent.setup();
    renderWithStore(<ProfileForm checker />);
    const picker = await screen.findByRole("combobox", { name: /Select a scholarship/ });
    expect(within(picker).getByText("Beta State Scholarship (test fixture) (unverified)")).toBeInTheDocument();
    await user.selectOptions(picker, "SP-T2");
    await user.selectOptions(screen.getByRole("combobox", { name: /State of residence/ }), "Madhya Pradesh");
    await user.selectOptions(screen.getByRole("combobox", { name: /Education level/ }), "Undergraduate");
    await user.type(screen.getByLabelText(/Full name/), "Asha Verma");
    await user.type(screen.getByLabelText(/Academic percentage/), "72");
    await user.click(screen.getByRole("button", { name: "Check Eligibility" }));
    expect(await screen.findByRole("heading", { name: "Can't Tell Yet" })).toBeInTheDocument();
    const posts = fetchMock.mock.calls.map(([u, i]) => [String(u), i]).filter(([u, i]) => isEligibility(u, i));
    const body = JSON.parse(posts.at(-1)[1].body);
    expect(body.scholarship_ids).toEqual(["SP-T2"]);
    expect(body.profile).toEqual({ state: "Madhya Pradesh", education_level: "Undergraduate", percentage: 72 }); // no name, no DOB, no institution
    expect(screen.getByText("Required: Resident of: Madhya Pradesh")).toBeInTheDocument();
    expect(screen.getByText("Meets requirement")).toBeInTheDocument();
    expect(screen.getByText(/Rule-based check by the ScholarPath API/)).toBeInTheDocument();
    expect(screen.getByText(/Checked against/)).toHaveTextContent("Beta State Scholarship (test fixture)");
  });

  it("works with a partly filled form: missing details come back as 'information missing'", async () => {
    api({ check: () => ({ results: [eligibilityResult({ missing_information: ["family_income"], criteria: [criterionResult({ status: "missing", student_value: null, explanation: "Add your annual family income to check this requirement." })] })], not_found: [] }) });
    const user = userEvent.setup();
    renderWithStore(<ProfileForm checker />);
    await screen.findByRole("combobox", { name: /Select a scholarship/ });
    await user.click(screen.getByRole("button", { name: "Check Eligibility" }));
    expect(await screen.findByText("Information missing")).toBeInTheDocument();
    expect(screen.getByText(/add: family income/)).toBeInTheDocument();
  });

  it("shows API failures for the check with a retry", async () => {
    let calls = 0;
    api({ check: () => (++calls === 1 ? jsonResponse(errorBody("database_unavailable", "down"), 503) : { results: [eligibilityResult()], not_found: [] }) });
    const user = userEvent.setup();
    renderWithStore(<ProfileForm checker />);
    await screen.findByRole("combobox", { name: /Select a scholarship/ });
    await user.click(screen.getByRole("button", { name: "Check Eligibility" }));
    expect(await screen.findByText("Eligibility could not be checked")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    expect(await screen.findByRole("heading", { name: "Can't Tell Yet" })).toBeInTheDocument();
  });

  it("explains when there are no scholarships to check, or the list cannot be loaded", async () => {
    api({ list: () => listPage([], { total: 0 }) });
    const { unmount } = renderWithStore(<ProfileForm checker />);
    expect(await screen.findByText(/no scholarships on record to check yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check Eligibility" })).toBeDisabled();
    unmount();
    api({ list: () => jsonResponse(errorBody("database_not_configured", "x"), 503) });
    renderWithStore(<ProfileForm checker />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/not set up yet/i);
  });
});

describe("Profile form", () => {
  it("validates input with inline messages and saves a valid profile locally", async () => {
    api();
    const user = userEvent.setup();
    renderWithStore(<ProfileForm />);
    expect(screen.getByText("0% complete")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save Profile" }));
    expect(await screen.findByText("Enter your full name")).toBeInTheDocument();
    expect(screen.getByText("Enter your academic percentage")).toBeInTheDocument();
    expect(screen.getByText("Enter your annual family income")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Full name/), "Asha Verma");
    await user.type(screen.getByLabelText(/Date of birth/), "2005-06-15");
    await user.selectOptions(screen.getByRole("combobox", { name: /State of residence/ }), "Maharashtra");
    await user.selectOptions(screen.getByRole("combobox", { name: /Education level/ }), "Undergraduate");
    await user.type(screen.getByLabelText(/Current course/), "B.Sc Physics");
    await user.type(screen.getByLabelText(/Institution/), "University of Mumbai");
    await user.type(screen.getByLabelText(/Academic percentage/), "86");
    await user.type(screen.getByLabelText(/Annual family income/), "280000");
    await user.click(screen.getByRole("button", { name: "Save Profile" }));
    await waitFor(() => expect(JSON.parse(window.localStorage.getItem("scholarpath.workspace.v2")).profile).toMatchObject({ name: "Asha Verma", state: "Maharashtra", percentage: 86, income: 280000 }));
  });

  it("rejects out-of-range values", async () => {
    api();
    const user = userEvent.setup();
    renderWithStore(<ProfileForm />);
    await user.type(screen.getByLabelText(/Academic percentage/), "101");
    await user.click(screen.getByRole("button", { name: "Save Profile" }));
    expect(await screen.findByText("Percentage must be between 0 and 100")).toBeInTheDocument();
  });

  it("offers every state and the education levels found in the data", () => {
    api();
    renderWithStore(<ProfileForm />);
    const state = screen.getByRole("combobox", { name: /State of residence/ });
    expect(within(state).getAllByRole("option").length).toBe(37); // placeholder + 28 states + 8 union territories
    const level = screen.getByRole("combobox", { name: /Education level/ });
    for (const label of ["Class 8", "Class 9", "Class 11", "Diploma", "Postgraduate"]) expect(within(level).getByText(label)).toBeInTheDocument();
  });
});

describe("Dashboard", () => {
  it("shows live counts and clearly says verified records are the minority", async () => {
    api({ filters: { ...filterOptions, total_scholarships: 34, verified_scholarships: 0 } });
    renderWithStore(<Dashboard />);
    expect(await screen.findByText("34 records")).toBeInTheDocument();
    expect(screen.getByText("0 of 34")).toBeInTheDocument();
    expect(await screen.findByText("Alpha Merit Scholarship (test fixture)")).toBeInTheDocument();
    expect(screen.getByText(/no application dates, so no deadlines can be listed/)).toBeInTheDocument();
    expect(screen.getByText("Complete your profile · 0%")).toBeInTheDocument();
  });

  it("asks for recommendations using the profile and the preferred scheme level", async () => {
    window.localStorage.setItem("scholarpath.workspace.v2", JSON.stringify({ profile: { state: "Bihar", education: "Class 12", percentage: "65", income: "200000", category: "SC", gender: "Male", preference: "Central" }, saved: [], applications: {} }));
    const fetchMock = api();
    renderWithStore(<Dashboard />);
    await screen.findByText("Alpha Merit Scholarship (test fixture)");
    await waitFor(() => expect(lastList(fetchMock).searchParams.get("state")).toBe("Bihar"));
    expect(Object.fromEntries(lastList(fetchMock).searchParams)).toMatchObject({
      state: "Bihar", education_level: "Class 12", category: "SC", gender: "Male", student_percentage: "65", student_income: "200000", scheme_type: "central", page_size: "3",
    });
  });

  it("reports API problems instead of showing sample scholarships", async () => {
    mockFetch([[isFilters, () => jsonResponse(errorBody("database_not_configured", "x"), 503)], [isList, () => jsonResponse(errorBody("database_not_configured", "x"), 503)]]);
    renderWithStore(<Dashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/scholarship database is not set up yet/i);
    expect(screen.getAllByText("Unavailable").length).toBe(2);
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("hands the dashboard search to the directory", async () => {
    api();
    const user = userEvent.setup();
    renderWithStore(<Dashboard />);
    await user.type(screen.getByLabelText("Search scholarships"), "post matric");
    await user.click(screen.getByRole("button", { name: /Search Scholarships/ }));
    expect(routerPush).toHaveBeenCalledWith("/scholarships?q=post%20matric");
  });
});
