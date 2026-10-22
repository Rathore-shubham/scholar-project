"use client";

import { useState } from "react";
import { CheckCircle2, CircleHelp, ExternalLink, RotateCcw, Save, ShieldCheck, XCircle } from "lucide-react";

import { api } from "@/lib/api";
import { useApiQuery } from "@/lib/use-api";
import { hostOf } from "@/lib/format";
import {
  CRITERION_STATUS_LABELS,
  OUTCOME_LABELS,
  categories,
  educationLevels,
  emptyProfile,
  genders,
  profileCompletion,
  profileSchema,
  schemePreferences,
  states,
} from "./data";
import { useScholar } from "./store";
import { Button, ConfirmDialog, EligibilityBadge, ErrorState, LoadingList, PageHeading, SourceNote } from "./ui";

/** Criterion-by-criterion explanation returned by POST /eligibility/check. */
export function CriteriaTable({ criteria }) {
  if (!criteria || criteria.length === 0) {
    return <p className="inline-note">No eligibility criteria are on record for this scholarship.</p>;
  }
  return (
    <div className="criteria-table">
      {criteria.map((r, index) => {
        const cls = r.status === "pass" ? "criterion-success" : r.status === "fail" ? "criterion-fail" : "criterion-missing";
        const Icon = r.status === "pass" ? CheckCircle2 : r.status === "fail" ? XCircle : CircleHelp;
        const evidence = r.evidence;
        return (
          <div className="criterion-row" key={`${r.criterion_type}-${index}`}>
            <div>
              <strong>
                {r.criterion}
                {!r.is_mandatory && <small> (optional)</small>}
              </strong>
              <p>Required: {r.required}</p>
              <p>Your value: {r.student_value ?? "Not provided"}</p>
              <p className="criterion-explanation">{r.explanation}</p>
              <p className="criterion-source">
                {r.reliable ? "Reviewed rule" : "Unreviewed rule"} ·{" "}
                {evidence?.url ? (
                  <a href={evidence.url} target="_blank" rel="noopener noreferrer">
                    Source <ExternalLink size={11} />
                  </a>
                ) : evidence?.text ? (
                  <>Source: {evidence.text}</>
                ) : evidence?.source_ref ? (
                  <>Extracted from {evidence.source_ref}; no source citation on record</>
                ) : (
                  <>No source on record</>
                )}
              </p>
            </div>
            <span className={cls}>
              <Icon size={16} /> {CRITERION_STATUS_LABELS[r.status]}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** The outcome panel for one eligibility result (also used on the details page). */
export function EligibilityResultPanel({ result, kicker = "RULE-BASED RESULT" }) {
  return (
    <section className="eligibility-result" aria-live="polite">
      <div className="result-heading">
        <div>
          <span className="provider-label">{kicker}</span>
          <h2>{OUTCOME_LABELS[result.outcome]}</h2>
          <p>{result.summary}</p>
        </div>
        <EligibilityBadge outcome={result.outcome} />
      </div>
      {result.limitations.length > 0 && (
        <ul className="limitation-list">
          {result.limitations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {result.missing_information.length > 0 && (
        <p className="inline-note">
          To get a clearer answer, add: {result.missing_information.map((f) => f.replace("_", " ")).join(", ")}.
        </p>
      )}
      <CriteriaTable criteria={result.criteria} />
      <p className="inline-note">
        Rule-based check by the ScholarPath API (no scoring, no AI). Verification status: {result.basis.verification_status}.{" "}
        {result.basis.rules_reliable
          ? "Every mandatory rule is reviewed and backed by evidence."
          : "The rules are not reviewed, so this is not an official eligibility decision. Confirm on the provider's official website."}
      </p>
    </section>
  );
}

export function ProfileForm({ checker = false }) {
  const { profile, saveProfile } = useScholar();
  const [values, setValues] = useState(() => Object.fromEntries(Object.entries({ ...emptyProfile, ...profile }).map(([k, v]) => [k, String(v)])));
  const [errors, setErrors] = useState({});
  const [submitted, setSubmitted] = useState(null); // the profile that was checked
  const [chosen, setChosen] = useState("");
  const [reset, setReset] = useState(false);

  const scholarships = useApiQuery(
    (signal) => api.listScholarships({ page_size: 50, sort: "name" }, { signal }),
    [],
    { enabled: checker },
  );
  const options = scholarships.data ? scholarships.data.items : [];
  const selectedId = chosen || options[0]?.scholarship_id || "";
  const selected = options.find((s) => s.scholarship_id === selectedId);

  const check = useApiQuery(
    (signal) => api.checkEligibility(submitted.profile, [selectedId], { signal }),
    [JSON.stringify(submitted), selectedId],
    { enabled: checker && !!submitted && !!selectedId },
  );
  const result = check.data?.results?.[0];

  const completion = profileCompletion(values);

  function set(key, value) {
    setValues((p) => ({ ...p, [key]: value }));
    setErrors((e) => ({ ...e, [key]: "" }));
    setSubmitted(null);
  }

  function validate() {
    const normalized = {
      ...values,
      percentage: values.percentage === "" ? undefined : values.percentage,
      income: values.income === "" ? undefined : values.income,
    };
    const parsed = profileSchema.safeParse(normalized);
    if (!parsed.success) {
      const next = {};
      parsed.error.issues.forEach((i) => {
        const key = String(i.path[0]);
        next[key] =
          key === "income" && !values.income
            ? "Enter your annual family income"
            : key === "percentage" && !values.percentage
              ? "Enter your academic percentage"
              : i.message;
      });
      setErrors(next);
      return null;
    }
    setErrors({});
    return parsed.data;
  }

  function submit(save) {
    const data = validate();
    if (!data) {
      // The checker may run with whatever is valid so far; missing details come back as "information missing".
      if (!save) {
        const partial = {};
        if (educationLevels.includes(values.education)) partial.education = values.education;
        if (values.state) partial.state = values.state;
        if (values.gender) partial.gender = values.gender;
        if (values.category) partial.category = values.category;
        if (values.percentage !== "" && Number(values.percentage) >= 0 && Number(values.percentage) <= 100) partial.percentage = values.percentage;
        if (values.income !== "" && Number(values.income) >= 0 && Number(values.income) <= 100000000) partial.income = values.income;
        setSubmitted({ profile: partial });
      }
      return;
    }
    if (save) saveProfile(data);
    else setSubmitted({ profile: data });
  }

  function field(key, label, type = "text", fieldOptions, optional = false) {
    const error = errors[key];
    return (
      <label className="form-field" htmlFor={`profile-${key}`}>
        <span>
          {label}
          {optional ? <small> (optional)</small> : <span className="required"> *</span>}
        </span>
        {fieldOptions ? (
          <select
            id={`profile-${key}`}
            value={values[key] ?? ""}
            onChange={(e) => set(key, e.target.value)}
            aria-invalid={!!error}
            aria-describedby={error ? `${key}-error` : undefined}
          >
            <option value="">Select {label.toLowerCase()}</option>
            {fieldOptions.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        ) : (
          <input
            id={`profile-${key}`}
            value={values[key] ?? ""}
            type={type}
            min={type === "number" ? 0 : type === "date" ? "1900-01-01" : undefined}
            max={key === "percentage" ? 100 : key === "dob" ? new Date().toISOString().slice(0, 10) : undefined}
            maxLength={key === "institution" ? 150 : 100}
            onChange={(e) => set(key, e.target.value)}
            aria-invalid={!!error}
            aria-describedby={error ? `${key}-error` : undefined}
          />
        )}{" "}
        {error && (
          <span className="field-error" id={`${key}-error`}>
            {error}
          </span>
        )}
      </label>
    );
  }

  return (
    <>
      <PageHeading
        title={checker ? "Eligibility Checker" : "My Profile"}
        description={
          checker
            ? "See how your details compare with a scholarship's listed requirements, criterion by criterion."
            : "A few details today can open up more opportunities tomorrow."
        }
      />
      {!checker && (
        <div className="profile-progress">
          <div>
            <strong>Profile completion</strong>
            <span>{completion}% complete</span>
          </div>
          <progress value={completion} max={100} />
          <p>{completion === 100 ? "Looking good! Keep your information up to date." : "Complete your profile to discover scholarships that match your eligibility."}</p>
        </div>
      )}
      {checker && (
        <>
          {scholarships.status === "loading" && <LoadingList count={1} label="Loading scholarships" />}
          {scholarships.status === "error" && <ErrorState error={scholarships.error} onRetry={scholarships.reload} />}
          {scholarships.status === "success" && options.length === 0 && (
            <p className="inline-note">There are no scholarships on record to check yet. Import the ScholarPath data first.</p>
          )}
          {options.length > 0 && (
            <label className="form-field scholarship-select">
              <span>Select a scholarship</span>
              <select
                value={selectedId}
                onChange={(e) => {
                  setChosen(e.target.value);
                  setSubmitted(null);
                }}
              >
                {options.map((s) => (
                  <option value={s.scholarship_id} key={s.scholarship_id}>
                    {s.name}
                    {s.is_verified ? "" : " (unverified)"}
                  </option>
                ))}
              </select>
              {scholarships.data && scholarships.data.total > options.length && (
                <small>Showing the first {options.length} of {scholarships.data.total} scholarships.</small>
              )}
            </label>
          )}
        </>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(!checker);
        }}
        noValidate
      >
        <section className="form-section">
          <div className="form-section-heading">
            <h2>Personal Information</h2>
            <p>Your basic details, nothing more.</p>
          </div>
          <div className="profile-form-grid">
            {field("name", "Full name")}
            {field("dob", "Date of birth", "date")}
            {field("state", "State of residence", "text", states)}
            {field("gender", "Gender", "text", genders, true)}
          </div>
        </section>
        <section className="form-section">
          <div className="form-section-heading">
            <h2>Education Details</h2>
            <p>Tell us about your current studies.</p>
          </div>
          <div className="profile-form-grid">
            {field("education", "Education level", "text", educationLevels)}
            {field("course", "Current course")}
            {field("institution", "Institution")}
            {field("percentage", "Academic percentage", "number")}
          </div>
        </section>
        <section className="form-section">
          <div className="form-section-heading">
            <h2>Family Income</h2>
            <p>Used only for income-based requirements.</p>
          </div>
          <div className="profile-form-grid">{field("income", "Annual family income (₹)", "number")}</div>
        </section>
        <section className="form-section">
          <div className="form-section-heading">
            <h2>Eligibility Information</h2>
            <p>Optional details for scheme-specific requirements.</p>
          </div>
          <div className="profile-form-grid">{field("category", "Applicable category", "text", categories, true)}</div>
        </section>
        {!checker && (
          <section className="form-section">
            <div className="form-section-heading">
              <h2>Preferences</h2>
              <p>Choose the opportunities you’d like to explore.</p>
            </div>
            <div className="profile-form-grid">{field("preference", "Preferred scheme level", "text", schemePreferences, true)}</div>
          </section>
        )}
        <p className="privacy-note">
          <ShieldCheck size={18} />
          Your profile is used to match scholarships and check eligibility. It is saved only in this browser, and is sent to the ScholarPath API only when you check
          eligibility (it is not stored there). Please don't enter Aadhaar numbers or bank details.
        </p>
        <div className="form-actions">
          {checker && (
            <Button type="submit" disabled={!selectedId}>
              <CheckCircle2 />
              Check Eligibility
            </Button>
          )}
          <Button type={checker ? "button" : "submit"} variant={checker ? "outline" : "default"} onClick={checker ? () => submit(true) : undefined}>
            <Save />
            Save Profile
          </Button>
          <Button type="button" variant="ghost" onClick={() => setReset(true)}>
            <RotateCcw />
            Reset Form
          </Button>
        </div>
      </form>

      {checker && submitted && check.status === "loading" && <LoadingList count={1} label="Checking eligibility" />}
      {checker && submitted && check.status === "error" && <ErrorState error={check.error} onRetry={check.reload} title="Eligibility could not be checked" />}
      {checker && submitted && check.status === "success" && !result && (
        <p className="inline-note">This scholarship is no longer available. Pick another one.</p>
      )}
      {checker && result && selected && (
        <>
          <p className="inline-note">
            Checked against <strong>{selected.name}</strong>
            {selected.official_url && (
              <>
                {" "}
                · official site:{" "}
                <a href={selected.official_url} target="_blank" rel="noopener noreferrer">
                  {hostOf(selected.official_url)}
                </a>
              </>
            )}
          </p>
          <EligibilityResultPanel result={result} />
        </>
      )}
      <SourceNote />
      <ConfirmDialog
        open={reset}
        onClose={() => setReset(false)}
        title="Reset this form?"
        description="Unsaved changes will be cleared. Your saved profile will not be deleted."
        onConfirm={() => {
          setValues(Object.fromEntries(Object.keys(emptyProfile).map((k) => [k, ""])));
          setErrors({});
          setSubmitted(null);
        }}
      />
    </>
  );
}
