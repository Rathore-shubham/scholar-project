"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Bookmark,
  Building2,
  CalendarDays,
  Check,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  Info,
  Landmark,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { describeError } from "@/lib/api";
import { NOT_AVAILABLE, awardNumeric, dateLabel, eligibilityHint, joinList, truncate, verificationLabel } from "@/lib/format";
import { OUTCOME_LABELS, schemeTypeLabels } from "./data";
import { useScholar } from "./store";

export { Button };

export function EligibilityBadge({ outcome }) {
  const cls = outcome === "eligible" ? "status-success" : outcome === "not_eligible" ? "status-neutral" : "status-warning";
  return (
    <span className={`status ${cls}`}>
      {outcome === "eligible" ? <Check size={12} /> : <CircleHelp size={12} />} {OUTCOME_LABELS[outcome] || "Not checked"}
    </span>
  );
}

/** Verified / Unverified / Needs review. "Unverified" is shown for every pending record. */
export function VerificationBadge({ status }) {
  const cls = status === "verified" ? "status-success" : "status-warning";
  return (
    <span className={`status ${cls}`}>
      {status === "verified" ? <CircleCheck size={12} /> : <ShieldAlert size={12} />} {verificationLabel(status)}
    </span>
  );
}

export function DataNotice({ notice }) {
  if (!notice) return null;
  return (
    <p className="data-notice" role="note">
      <Info size={15} />
      <span>{notice}</span>
    </p>
  );
}

export function Deadline({ date }) {
  return (
    <span className="text-muted-foreground">
      <CalendarDays size={14} />
      {dateLabel(date)}
    </span>
  );
}

export function ProviderIcon({ schemeType }) {
  const symbol = schemeType === "central" ? "landmark" : schemeType === "state" ? "building" : "book";
  const Icon = symbol === "landmark" ? Landmark : symbol === "building" ? Building2 : BookOpen;
  return (
    <div className={`provider-icon provider-${symbol}`}>
      <Icon size={22} />
    </div>
  );
}

/** One scholarship from the API. `eligibility` is that scholarship's result from POST /eligibility/check (or undefined). */
export function ScholarshipCard({ scholarship: s, eligibility, eligibilityFailed = false, layout = "card" }) {
  const { saved, toggleSave } = useScholar();
  const isSaved = saved.includes(s.scholarship_id);
  const numeric = awardNumeric(s);
  const href = `/scholarships/${encodeURIComponent(s.scholarship_id)}`;
  return (
    <article className={`scholarship-card scholarship-${layout}`}>
      <div className="scholarship-title-group">
        <div className="flex min-w-0 gap-3">
          <ProviderIcon schemeType={s.scheme_type} />
          <div className="min-w-0">
            <p className="provider-label">
              {schemeTypeLabels[s.scheme_type] || "Scholarship"} · {s.is_verified ? "Verified" : "Unverified source data"}
            </p>
            <h3>
              <Link href={href}>{s.name}</Link>
            </h3>
            <p className="provider-name">{s.provider_name || "Provider not specified"}</p>
          </div>
        </div>
        <Button
          size="icon"
          variant="ghost"
          title={isSaved ? "Unsave scholarship" : "Save scholarship"}
          aria-label={`${isSaved ? "Unsave" : "Save"} ${s.name}`}
          onClick={() => toggleSave(s.scholarship_id)}
          className={isSaved ? "text-primary" : "text-muted-foreground"}
        >
          <Bookmark fill={isSaved ? "currentColor" : "none"} />
        </Button>
      </div>
      <div className="scholarship-facts">
        <div className="scholarship-funding">
          <span>Funding</span>
          <strong>{numeric || "Amount not specified"}</strong>
          {s.award_amount_text && <small className="funding-text">{truncate(s.award_amount_text, 110)}</small>}
        </div>
        <div>
          <span>Education level</span>
          <p>{joinList(s.education_level_labels)}</p>
        </div>
        <div className="card-deadline">
          <span>Deadline</span>
          <Deadline date={s.application_deadline} />
        </div>
      </div>
      <div className="eligibility-summary">
        {eligibilityFailed ? (
          <>
            <span className="status status-neutral">
              <CircleHelp size={12} /> Not checked
            </span>
            <p>Eligibility could not be checked right now. Open the details to try again.</p>
          </>
        ) : (
          <>
            <EligibilityBadge outcome={eligibility ? eligibility.outcome : undefined} />
            <p>{eligibilityHint(eligibility)}</p>
          </>
        )}
      </div>
      <div className="card-footer">
        <VerificationBadge status={s.verification_status} />
        <Button variant="outline" size="sm" asChild>
          <Link href={href}>
            View Details <ArrowRight size={14} />
          </Link>
        </Button>
      </div>
    </article>
  );
}

export function EmptyState({ title, description, action = true }) {
  return (
    <div className="empty-state">
      <Bookmark size={28} />
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && (
        <Button asChild>
          <Link href="/scholarships">
            Explore Scholarships <ArrowRight />
          </Link>
        </Button>
      )}
    </div>
  );
}

/** Placeholder cards while the API call is in flight. */
export function LoadingList({ count = 3, label = "Loading scholarships" }) {
  return (
    <div className="api-loading" role="status" aria-live="polite" aria-label={label}>
      {Array.from({ length: count }, (_, i) => (
        <div className="skeleton-card" key={i} aria-hidden="true">
          <div className="skeleton-line skeleton-title" />
          <div className="skeleton-line" />
          <div className="skeleton-line skeleton-short" />
        </div>
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

/** Honest failure display with a retry. Never shows placeholder scholarships. */
export function ErrorState({ error, onRetry, title }) {
  const info = describeError(error);
  return (
    <div className="api-error" role="alert">
      <CircleAlert size={26} />
      <h3>{title || info.title}</h3>
      <p>{info.message}</p>
      {onRetry && info.retryable && (
        <Button variant="outline" onClick={onRetry}>
          <RefreshCw /> Try again
        </Button>
      )}
      <small>Error code: {info.code}</small>
    </div>
  );
}

export function PageHeading({ title, description, children }) {
  return (
    <div className="page-heading grid grid-cols-[minmax(0,1fr)_auto] gap-4 sm:flex sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </div>
  );
}

/** Replaces the prototype's "illustrative sample" banner: states what the data is. */
export function SourceNote() {
  return (
    <p className="prototype-note">
      <Info size={14} /> Scholarship records come from the ScholarPath data pipeline. Records marked “Unverified” have not been reviewed;
      always confirm requirements and dates with the official provider.
    </p>
  );
}

export function ConfirmDialog({ open, onClose, onConfirm, title, description }) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              onConfirm();
              onClose();
            }}
          >
            Confirm
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export { NOT_AVAILABLE };
