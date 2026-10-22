"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Bookmark, CalendarDays, ExternalLink, FileText, Info, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { NOT_AVAILABLE, awardNumeric, dateLabel, hostOf, joinList } from "@/lib/format";
import { useApiQuery, useEligibility } from "@/lib/use-api";
import { schemeTypeLabels } from "./data";
import { CriteriaTable, EligibilityResultPanel } from "./profile";
import { useScholar } from "./store";
import { DataNotice, EligibilityBadge, ErrorState, LoadingList, ProviderIcon, SourceNote, VerificationBadge } from "./ui";

function Unavailable({ children = "Not available in the source data." }) {
  return <p className="unavailable">{children}</p>;
}

export function Details({ id }) {
  const { profile, saved, toggleSave, applications, setStatus } = useScholar();
  const [external, setExternal] = useState(false);
  const detail = useApiQuery((signal) => api.getScholarship(id, { signal }), [id]);
  const eligibility = useEligibility(profile, [id]);
  const result = eligibility.byId[id];

  if (detail.status === "loading" || detail.status === "idle") return <LoadingList count={2} label="Loading scholarship" />;
  if (detail.status === "error") {
    if (detail.error.code === "scholarship_not_found") {
      return (
        <div className="empty-state">
          <h1>Scholarship not found</h1>
          <p>No scholarship with this id is on record. It may have been removed or the link may be wrong.</p>
          <Button asChild>
            <Link href="/scholarships">Find Scholarships</Link>
          </Button>
        </div>
      );
    }
    return <ErrorState error={detail.error} onRetry={detail.reload} />;
  }

  const s = detail.data;
  const isSaved = saved.includes(s.scholarship_id);
  const tracked = !!applications[s.scholarship_id];
  const numeric = awardNumeric(s);
  const p = s.provenance;

  return (
    <>
      <Link href="/scholarships" className="back-link">
        <ArrowLeft size={16} />
        Back to scholarships
      </Link>
      <div className="detail-header">
        <div className="flex items-start gap-4">
          <ProviderIcon schemeType={s.scheme_type} />
          <div className="min-w-0">
            <span className="provider-label">
              {schemeTypeLabels[s.scheme_type] || "Scholarship"} · {s.is_verified ? "Verified" : "Unverified source data"}
            </span>
            <h1>{s.name}</h1>
            <p>{s.provider_name || "Provider not specified"}</p>
          </div>
        </div>
        <div className="detail-key-facts">
          <div>
            <span>Scholarship amount</span>
            <strong>{numeric || "Amount not specified"}</strong>
          </div>
          <div>
            <span>Application deadline</span>
            <strong>{dateLabel(s.application_deadline)}</strong>
          </div>
          <div>
            <span>Eligibility</span>
            {eligibility.status === "loading" ? <span className="text-muted-foreground">Checking…</span> : <EligibilityBadge outcome={result?.outcome} />}
          </div>
          <div>
            <span>Verification</span>
            <VerificationBadge status={s.verification_status} />
          </div>
        </div>
        <DataNotice notice={s.data_notice} />
        <div className="detail-actions">
          <Button variant="outline" onClick={() => toggleSave(s.scholarship_id)}>
            <Bookmark fill={isSaved ? "currentColor" : "none"} />
            {isSaved ? "Saved Scholarship" : "Save Scholarship"}
          </Button>
          <Button variant="outline" onClick={() => setStatus(s.scholarship_id, "Interested")} disabled={tracked}>
            <Plus />
            {tracked ? "Application Tracked" : "Track Application"}
          </Button>
          <Button onClick={() => setExternal(true)} disabled={!s.official_url}>
            Apply on Official Website <ExternalLink />
          </Button>
        </div>
        {!s.official_url && (
          <p className="external-note">
            <ExternalLink size={13} />
            No official website is on record for this scholarship.
          </p>
        )}
      </div>

      <div className="detail-content">
        <section>
          <h2>Overview</h2>
          <dl className="fact-list">
            <div><dt>Provider</dt><dd>{s.provider_name || NOT_AVAILABLE}</dd></div>
            <div><dt>Scheme level</dt><dd>{schemeTypeLabels[s.scheme_type] || NOT_AVAILABLE}{s.government_level ? ` (${s.government_level})` : ""}</dd></div>
            <div><dt>Education levels</dt><dd>{joinList(s.education_level_labels)}</dd></div>
            <div><dt>States</dt><dd>{joinList(s.eligible_states.map((x) => (x === "ALL" ? "All states" : x)))}</dd></div>
            <div><dt>Categories</dt><dd>{joinList(s.eligible_categories.map((x) => (x === "ALL" ? "All categories" : x)))}</dd></div>
            <div><dt>Courses</dt><dd>{joinList(s.eligible_courses.map((x) => (x === "ALL" ? "All courses" : x)))}</dd></div>
            <div><dt>Academic year</dt><dd>{s.academic_year || NOT_AVAILABLE}</dd></div>
          </dl>
          <p className="inline-note">Taken as written from the source record. No description text is available.</p>
        </section>

        <section>
          <div className="section-heading">
            <div>
              <h2>Eligibility Criteria</h2>
              <p>Your profile compared with this scholarship's listed criteria.</p>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link href="/eligibility">
                Check Eligibility <ArrowLeft className="rotate-180" />
              </Link>
            </Button>
          </div>
          {eligibility.status === "loading" && <LoadingList count={1} label="Checking eligibility" />}
          {eligibility.status === "error" && (
            <>
              <ErrorState error={eligibility.error} onRetry={eligibility.reload} title="Eligibility could not be checked" />
              <p className="inline-note">The criteria below are shown without a comparison.</p>
              <ul className="document-list">
                {s.criteria.map((c, i) => (
                  <li key={i}>
                    <Info size={16} />
                    {c.label}: {c.required_value.text || joinList(c.required_value.values || [String(c.required_value.value ?? "")])}
                  </li>
                ))}
              </ul>
            </>
          )}
          {result && (
            <>
              <EligibilityResultPanel result={result} />
            </>
          )}
          {eligibility.status === "success" && !result && <CriteriaTable criteria={[]} />}
        </section>

        <section>
          <h2>Benefits and Scholarship Amount</h2>
          {s.award_amount_text || numeric ? (
            <>
              {numeric && <p><strong>{numeric}</strong> (as recorded; the source text below states the period and conditions).</p>}
              {s.award_amount_text && <p>{s.award_amount_text}</p>}
            </>
          ) : (
            <Unavailable />
          )}
        </section>

        <section>
          <h2>Required Documents</h2>
          {s.required_documents.length ? (
            <ul className="document-list">
              {s.required_documents.map((d) => (
                <li key={d}>
                  <FileText size={16} />
                  {d}
                </li>
              ))}
            </ul>
          ) : (
            <Unavailable>The source data does not list required documents. Check the official website.</Unavailable>
          )}
        </section>

        <section>
          <h2>Application Process</h2>
          {s.application_procedure ? <p>{s.application_procedure}</p> : <Unavailable>The source data does not describe the application steps. Use the official website.</Unavailable>}
        </section>

        <section>
          <h2>Important Dates</h2>
          <div className="date-fact">
            <CalendarDays size={18} />
            <span>Application opens</span>
            <strong>{dateLabel(s.application_open_date)}</strong>
          </div>
          <div className="date-fact">
            <CalendarDays size={18} />
            <span>Application deadline</span>
            <strong>{dateLabel(s.application_deadline)}</strong>
          </div>
          {!s.application_deadline && <p className="inline-note">No application dates are recorded for this scholarship. Check the official website.</p>}
        </section>

        <section>
          <h2>Official Source</h2>
          <dl className="fact-list">
            <div>
              <dt>Official website</dt>
              <dd>
                {s.official_url ? (
                  <a href={s.official_url} target="_blank" rel="noopener noreferrer">
                    {s.official_url}
                  </a>
                ) : (
                  NOT_AVAILABLE
                )}
              </dd>
            </div>
            <div>
              <dt>Source page URL</dt>
              <dd>{s.source_url || "Not recorded (extracted from a local data file)"}</dd>
            </div>
            <div>
              <dt>Verification status</dt>
              <dd>{s.is_verified ? "Verified" : s.verification_status === "needs_review" ? "Needs review" : "Unverified (pending review)"}</dd>
            </div>
            <div>
              <dt>Last verification date</dt>
              <dd>{s.last_verified_at ? dateLabel(s.last_verified_at) : "Not verified"}</dd>
            </div>
            <div>
              <dt>Extracted</dt>
              <dd>
                {s.extracted_at ? dateLabel(s.extracted_at.slice(0, 10)) : NOT_AVAILABLE}
                {p.source_file ? ` from ${p.source_file}${p.source_sheet ? ` · ${p.source_sheet}` : ""}${p.source_row != null ? ` · row ${p.source_row}` : ""}` : ""}
              </dd>
            </div>
            {s.review_notes && (
              <div>
                <dt>Review notes</dt>
                <dd>{s.review_notes}</dd>
              </div>
            )}
          </dl>
          {s.eligibility_rules.length > 0 && (
            <>
              <h3 className="sub-heading">Conditions stored as text</h3>
              <ul className="document-list">
                {s.eligibility_rules.map((rule) => (
                  <li key={rule}>
                    <Info size={16} />
                    {rule}
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
      </div>
      <SourceNote />

      <Dialog open={external} onOpenChange={setExternal}>
        <DialogContent>
          <DialogTitle>You are leaving ScholarPath AI</DialogTitle>
          <DialogDescription>
            This opens {s.official_url ? hostOf(s.official_url) : "the official website"} in a new tab.
          </DialogDescription>
          {!s.is_verified && (
            <p className="text-sm text-muted-foreground">
              This record is unverified. Confirm that the scheme exists, is open, and what its dates and requirements are on the official site before you rely on it.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setExternal(false)}>
              Cancel
            </Button>
            {s.official_url && (
              <Button asChild>
                <a href={s.official_url} target="_blank" rel="noopener noreferrer" onClick={() => setExternal(false)}>
                  Continue to official website <ExternalLink />
                </a>
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
