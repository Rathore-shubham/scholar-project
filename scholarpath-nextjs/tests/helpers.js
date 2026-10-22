// Test helpers: a routable fetch mock and synthetic API payloads.
// Every record below is a labelled TEST FIXTURE; the app itself contains no scholarship data.

import { render } from "@testing-library/react";
import { vi } from "vitest";

import { ScholarProvider } from "@/features/scholarpath/store";

export function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/**
 * Install a fetch mock. `handlers` is an array of [predicate(url, init), responder(url, init)] pairs;
 * the first matching handler answers. Unmatched calls fail the test loudly.
 * Returns the vi.fn so tests can inspect calls (calls[i] = [url, init]).
 */
export function mockFetch(handlers) {
  const fn = vi.fn(async (url, init = {}) => {
    const target = String(url);
    for (const [matches, respond] of handlers) {
      if (matches(target, init)) {
        const out = await respond(target, init);
        return out instanceof Response ? out : jsonResponse(out);
      }
    }
    throw new Error(`Unexpected fetch in test: ${init.method || "GET"} ${target}`);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export const isList = (url) => /\/api\/v1\/scholarships(\?|$)/.test(url) && !/\/api\/v1\/scholarships\/[^?]/.test(url);
export const isDetail = (url) => /\/api\/v1\/scholarships\/[^?]/.test(url);
export const isFilters = (url) => url.includes("/api/v1/meta/filters");
export const isEligibility = (url, init) => url.includes("/api/v1/eligibility/check") && init.method === "POST";

export function summary(overrides = {}) {
  return {
    scholarship_id: "SP-T1",
    name: "Alpha Merit Scholarship (test fixture)",
    provider_name: "Test Department of Education",
    scheme_type: "central",
    government_level: "CENTRAL",
    education_levels: ["12", "UG"],
    education_level_labels: ["Class 12", "Undergraduate"],
    eligible_states: ["ALL"],
    eligible_categories: ["SC", "ST"],
    award_amount_min: null,
    award_amount_max: null,
    award_amount_text: null,
    application_deadline: null,
    official_url: "https://scholarships.gov.in",
    verification_status: "pending",
    is_verified: false,
    last_verified_at: null,
    data_notice: "Unverified: this record was extracted from source data and has not been reviewed.",
    ...overrides,
  };
}

export function listPage(items, { total = items.length, page = 1, pageSize = 12 } = {}) {
  return { items, total, page, page_size: pageSize, pages: total ? Math.ceil(total / pageSize) : 0 };
}

export function detail(overrides = {}) {
  return {
    ...summary(),
    academic_year: null,
    eligible_courses: ["ALL"],
    eligible_genders: ["MALE", "FEMALE", "OTHERS"],
    minimum_percentage: 60,
    maximum_family_income: 450000,
    income_comparator: "<",
    application_open_date: null,
    application_procedure: null,
    required_documents: [],
    eligibility_rules: ["Minimum percentage (as stated in source): MP BOARD-60"],
    source_url: null,
    source_name: "fixture.xlsx",
    source_type: "local_excel",
    extracted_at: "2026-10-12T05:03:39Z",
    review_notes: null,
    provenance: { source_file: "fixture.xlsx", source_sheet: "Sheet1", source_row: 2, source_record_id: null, duplicate_group_id: null, etl_validation_status: "warning", etl_issue_codes: ["missing_academic_year"] },
    extra_attributes: {},
    criteria: [],
    ...overrides,
  };
}

export function criterionResult(overrides = {}) {
  return {
    criterion_type: "state",
    criterion: "State of residence",
    required: "Resident of: Madhya Pradesh",
    student_value: "Madhya Pradesh",
    status: "pass",
    explanation: "Your state (Madhya Pradesh) is one of the listed states.",
    is_mandatory: true,
    review_status: "unreviewed",
    reliable: false,
    evidence: { text: null, url: null, source_ref: "fixture.xlsx / Sheet1 / row 2" },
    ...overrides,
  };
}

export function eligibilityResult(overrides = {}) {
  return {
    scholarship_id: "SP-T1",
    scholarship_name: "Alpha Merit Scholarship (test fixture)",
    outcome: "cant_tell_yet",
    summary: "Can't tell yet: the scholarship's rules are unverified.",
    indicative: "all_listed_criteria_met",
    basis: { verification_status: "pending", mandatory_criteria: 1, reviewed_mandatory_criteria: 0, supported_mandatory_criteria: 0, rules_reliable: false },
    missing_information: [],
    limitations: ["This record has not been verified (status: pending)."],
    criteria: [criterionResult()],
    ...overrides,
  };
}

export const filterOptions = {
  states: ["Madhya Pradesh"],
  education_levels: [{ value: "12", label: "Class 12" }, { value: "UG", label: "Undergraduate" }],
  categories: ["SC"], genders: ["FEMALE"], scheme_types: ["central"], total_scholarships: 2, verified_scholarships: 0,
};

export const errorBody = (code, detail) => ({ detail, code });

export function renderWithStore(ui) {
  return render(<ScholarProvider>{ui}</ScholarProvider>);
}
