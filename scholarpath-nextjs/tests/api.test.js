import { describe, expect, it, vi } from "vitest";

import { API_BASE_URL, ApiError, api, buildQuery, describeError, request, toApiProfile } from "@/lib/api";
import { errorBody, eligibilityResult, jsonResponse, mockFetch } from "./helpers";

describe("configuration", () => {
  it("uses NEXT_PUBLIC_API_URL (set to the backend on port 8001) without a trailing slash", () => {
    expect(API_BASE_URL).toBe("http://127.0.0.1:8001");
  });
});

describe("buildQuery", () => {
  it("skips blank values and encodes the rest", () => {
    expect(buildQuery({ q: "post matric", state: "", page: 2, x: undefined, y: null, verified_only: "true" })).toBe(
      "?q=post+matric&page=2&verified_only=true",
    );
    expect(buildQuery({})).toBe("");
    expect(buildQuery(undefined)).toBe("");
  });
});

describe("toApiProfile", () => {
  it("maps form fields to the API profile and omits blanks", () => {
    expect(
      toApiProfile({ state: "Bihar", education: "Undergraduate", percentage: "72.5", income: 300000, category: "OBC", gender: "Female", course: " B.Sc ", name: "ignored", dob: "2005-01-01" }),
    ).toEqual({ state: "Bihar", education_level: "Undergraduate", percentage: 72.5, family_income: 300000, category: "OBC", gender: "Female", course: "B.Sc" });
    expect(toApiProfile({ state: "", education: "", percentage: "", income: "" })).toEqual({});
    expect(toApiProfile(undefined)).toEqual({});
  });

  it("keeps a real zero but drops non-numeric text", () => {
    expect(toApiProfile({ income: "0", percentage: "0" })).toEqual({ percentage: 0, family_income: 0 });
    expect(toApiProfile({ income: "abc" })).toEqual({});
  });

  it("never sends personal identifiers (name, date of birth, institution)", () => {
    const sent = toApiProfile({ name: "Asha", dob: "2004-02-02", institution: "X University", state: "Goa" });
    expect(Object.keys(sent)).toEqual(["state"]);
  });
});

describe("request", () => {
  it("returns parsed JSON and calls the configured base URL", async () => {
    const fetchMock = mockFetch([[() => true, () => ({ status: "ok" })]]);
    expect(await request("/health")).toEqual({ status: "ok" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8001/health");
    expect(init.method).toBe("GET");
    expect(init.headers.Accept).toBe("application/json");
    expect(init.cache).toBe("no-store");
  });

  it("sends JSON bodies with a content type", async () => {
    const fetchMock = mockFetch([[() => true, () => ({})]]);
    await request("/x", { method: "POST", body: { a: 1 } });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"a":1}');
  });

  it("maps the backend's structured 503 to an ApiError with its code", async () => {
    mockFetch([[() => true, () => jsonResponse(errorBody("database_not_configured", "The database is not configured."), 503)]]);
    await expect(request("/api/v1/scholarships")).rejects.toMatchObject({ name: "ApiError", status: 503, code: "database_not_configured", message: "The database is not configured." });
  });

  it("flattens FastAPI validation errors (422)", async () => {
    mockFetch([[() => true, () => jsonResponse({ detail: [{ loc: ["body", "profile", "percentage"], msg: "Input should be less than or equal to 100" }] }, 422)]]);
    await expect(request("/x")).rejects.toMatchObject({ status: 422, code: "validation_error", message: "profile.percentage: Input should be less than or equal to 100" });
  });

  it("recognises 404 and unknown 5xx bodies", async () => {
    mockFetch([[(u) => u.includes("/a"), () => jsonResponse(errorBody("scholarship_not_found", "No scholarship"), 404)], [(u) => u.includes("/b"), () => new Response("<html>Bad gateway</html>", { status: 502 })]]);
    await expect(request("/a")).rejects.toMatchObject({ status: 404, code: "scholarship_not_found" });
    await expect(request("/b")).rejects.toMatchObject({ status: 502, code: "server_error" });
  });

  it("reports a network failure as network_error without leaking the cause", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(request("/health")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("times out", async () => {
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))))));
    await expect(request("/slow", { timeoutMs: 20 })).rejects.toMatchObject({ code: "timeout" });
  });

  it("rethrows a caller-initiated abort untouched (so UIs can ignore it)", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))))));
    const pending = request("/x", { signal: controller.signal });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("rejects an unreadable success body", async () => {
    mockFetch([[() => true, () => new Response("not json", { status: 200 })]]);
    await expect(request("/x")).rejects.toMatchObject({ code: "invalid_response" });
  });
});

describe("api helpers", () => {
  it("encodes scholarship ids in the detail URL", async () => {
    const fetchMock = mockFetch([[() => true, () => ({})]]);
    await api.getScholarship("SP A/1");
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8001/api/v1/scholarships/SP%20A%2F1");
  });

  it("checkEligibility posts the API profile and ids", async () => {
    const fetchMock = mockFetch([[() => true, () => ({ results: [eligibilityResult()], not_found: [] })]]);
    const out = await api.checkEligibility({ state: "Bihar", education: "Class 12", percentage: "70" }, ["SP-T1", "SP-T1"]);
    expect(out.results).toHaveLength(1);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toEqual({ profile: { state: "Bihar", education_level: "Class 12", percentage: 70 }, scholarship_ids: ["SP-T1"] });
  });

  it("splits large eligibility requests into batches of 50 and merges the answers in order", async () => {
    const fetchMock = mockFetch([
      [(u, i) => isCheck(u, i), (_u, init) => {
        const ids = JSON.parse(init.body).scholarship_ids;
        return { results: ids.map((id) => eligibilityResult({ scholarship_id: id })), not_found: [] };
      }],
    ]);
    const ids = Array.from({ length: 120 }, (_, i) => `SP-${i}`);
    const out = await api.checkEligibility({}, ids);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(out.results.map((r) => r.scholarship_id)).toEqual(ids);
  });
});

function isCheck(url, init) {
  return url.includes("/api/v1/eligibility/check") && init.method === "POST";
}

describe("describeError", () => {
  it("gives clear, specific guidance for each backend condition", () => {
    const make = (code) => new ApiError({ status: 503, code, message: "technical detail" });
    expect(describeError(make("database_not_configured"))).toMatchObject({ title: "The scholarship database is not set up yet", retryable: true });
    expect(describeError(make("database_not_configured")).message).toContain("Configure PostgreSQL Later");
    expect(describeError(make("database_unavailable")).title).toMatch(/unavailable/);
    expect(describeError(make("database_not_migrated")).message).toMatch(/alembic upgrade head/);
    expect(describeError(new ApiError({ status: 0, code: "network_error", message: "x" })).message).toContain("http://127.0.0.1:8001");
  });

  it("does not offer a retry for not-found and falls back gracefully for unknown errors", () => {
    expect(describeError(new ApiError({ status: 404, code: "scholarship_not_found", message: "gone" })).retryable).toBe(false);
    expect(describeError(new Error("boom"))).toMatchObject({ code: "unknown", title: "Something went wrong", message: "boom" });
  });
});
