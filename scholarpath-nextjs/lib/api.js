// Reusable client for the ScholarPath FastAPI backend.
//
// * The base URL comes from NEXT_PUBLIC_API_URL (see .env.example). Only that public URL is used here; database
//   credentials exist only in the backend's own environment.
// * Every failure becomes an ApiError; callers show it, they never fall back to made-up data.

export const DEFAULT_API_URL = "http://127.0.0.1:8001";
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/+$/, "");
const DEFAULT_TIMEOUT_MS = 15000;
const ELIGIBILITY_BATCH = 50; // the API accepts at most 50 ids per eligibility request

export class ApiError extends Error {
  /**
   * @param {{status: number, code: string, message: string, details?: unknown}} info
   *   status 0 = the request never got an HTTP response (network error / timeout).
   */
  constructor({ status, code, message, details }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

function messageFromPayload(status, payload) {
  const detail = payload && payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const where = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body" && p !== "query").join(".") : "";
        return where ? `${where}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `The server returned an error (HTTP ${status}).`;
}

function codeFromResponse(status, payload) {
  if (payload && typeof payload.code === "string") return payload.code;
  if (status === 422) return "validation_error";
  if (status === 404) return "not_found";
  return status >= 500 ? "server_error" : "http_error";
}

export async function request(path, { method = "GET", params, body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const forwardAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", forwardAbort, { once: true });
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}${buildQuery(params)}`, {
      method,
      headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (error) {
    if (signal && signal.aborted) throw error; // the caller cancelled (navigation, new search): not an error to show
    if (timedOut) {
      throw new ApiError({ status: 0, code: "timeout", message: "The ScholarPath API took too long to respond." });
    }
    throw new ApiError({ status: 0, code: "network_error", message: "Could not reach the ScholarPath API." });
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", forwardAbort);
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      code: codeFromResponse(response.status, payload),
      message: messageFromPayload(response.status, payload),
      details: payload,
    });
  }
  if (payload === null) {
    throw new ApiError({ status: response.status, code: "invalid_response", message: "The API returned an unreadable response." });
  }
  return payload;
}

/** Convert the form's profile (strings from inputs) into the API's StudentProfile; blanks are omitted. */
export function toApiProfile(profile) {
  const out = {};
  const text = (key) => String(profile?.[key] ?? "").trim();
  const number = (key) => {
    const raw = text(key);
    if (raw === "") return undefined;
    const n = Number(raw);
    return Number.isFinite(n) ? n : undefined;
  };
  if (text("state")) out.state = text("state");
  if (text("education")) out.education_level = text("education");
  if (number("percentage") !== undefined) out.percentage = number("percentage");
  if (number("income") !== undefined) out.family_income = number("income");
  if (text("category")) out.category = text("category");
  if (text("gender")) out.gender = text("gender");
  if (text("course")) out.course = text("course");
  return out;
}

export const api = {
  health: (options) => request("/health", options),
  listScholarships: (params, options) => request("/api/v1/scholarships", { ...options, params }),
  getScholarship: (id, options) => request(`/api/v1/scholarships/${encodeURIComponent(id)}`, options),
  filterOptions: (options) => request("/api/v1/meta/filters", options),

  /** Rule-based eligibility for any number of ids (split into API-sized batches, results merged in order). */
  async checkEligibility(profile, scholarshipIds, options) {
    const apiProfile = toApiProfile(profile);
    const ids = [...new Set(scholarshipIds)];
    const results = [];
    const notFound = [];
    for (let start = 0; start < ids.length; start += ELIGIBILITY_BATCH) {
      const page = await request("/api/v1/eligibility/check", {
        ...options,
        method: "POST",
        body: { profile: apiProfile, scholarship_ids: ids.slice(start, start + ELIGIBILITY_BATCH) },
      });
      results.push(...page.results);
      notFound.push(...page.not_found);
    }
    return { results, not_found: notFound };
  },
};

const FRIENDLY = {
  network_error: {
    title: "Can't reach the ScholarPath API",
    message: `The backend did not respond at ${API_BASE_URL}. Check that it is running (uvicorn app.main:app --port 8001) and try again.`,
  },
  timeout: { title: "The API is taking too long", message: "The server did not answer in time. Please try again." },
  database_not_configured: {
    title: "The scholarship database is not set up yet",
    message:
      "The backend is running, but PostgreSQL has not been configured, so there are no scholarship records to show. " +
      "See the backend README, section 'Configure PostgreSQL Later'.",
  },
  database_unavailable: {
    title: "The scholarship database is unavailable",
    message: "The backend could not reach PostgreSQL. Check that the database service is running, then try again.",
  },
  database_not_migrated: {
    title: "The database has no tables yet",
    message: "PostgreSQL is reachable, but the schema has not been created. Run the migrations (alembic upgrade head) and import the data.",
  },
  validation_error: { title: "Some input was not accepted", message: null },
  server_error: { title: "Something went wrong on the server", message: "Please try again. If it keeps happening, check the backend logs." },
  invalid_response: { title: "Unexpected response from the API", message: null },
};

/** Friendly, non-sensitive text for any error (ApiError or not). */
export function describeError(error) {
  const code = error instanceof ApiError ? error.code : "unknown";
  const known = FRIENDLY[code];
  return {
    code,
    title: known ? known.title : "Something went wrong",
    message: (known && known.message) || (error && error.message) || "An unexpected error occurred.",
    retryable: code !== "scholarship_not_found" && code !== "not_found",
  };
}

export function toApiError(error) {
  return error instanceof ApiError
    ? error
    : new ApiError({ status: 0, code: "unknown", message: (error && error.message) || "Unexpected error." });
}
