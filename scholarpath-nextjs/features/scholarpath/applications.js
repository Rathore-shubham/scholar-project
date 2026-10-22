"use client";

import { useMemo } from "react";
import Link from "next/link";
import { ArrowUpRight, Info } from "lucide-react";

import { api } from "@/lib/api";
import { dateLabel } from "@/lib/format";
import { useApiQuery } from "@/lib/use-api";
import { applicationStatuses } from "./data";
import { useScholar } from "./store";
import { Button, EmptyState, ErrorState, LoadingList, PageHeading, SourceNote } from "./ui";

export function Applications() {
  const { applications, setStatus, removeApplications } = useScholar();
  const trackedIds = useMemo(() => Object.keys(applications).slice(0, 50), [applications]);
  const list = useApiQuery(
    (signal) => api.listScholarships({ ids: trackedIds.join(","), page_size: 50 }, { signal }),
    [trackedIds.join(",")],
    { enabled: trackedIds.length > 0 },
  );
  const rows = list.data ? list.data.items : [];
  const unavailable = list.status === "success" ? trackedIds.filter((id) => !rows.some((s) => s.scholarship_id === id)) : [];

  return (
    <>
      <PageHeading title="My Applications" description="Keep track of your progress, from your first shortlist to your next milestone." />
      <div className="tracking-note">
        <Info size={17} />
        <p>Statuses are maintained by you and are not verified by scholarship providers.</p>
      </div>
      {unavailable.length > 0 && (
        <p className="inline-note" role="status">
          {unavailable.length} tracked scholarship{unavailable.length === 1 ? " is" : "s are"} no longer in the database.{" "}
          <button type="button" className="text-link" onClick={() => removeApplications(unavailable)}>
            Remove {unavailable.length === 1 ? "it" : "them"} from my tracker
          </button>
        </p>
      )}
      {trackedIds.length === 0 && <EmptyState title="No applications tracked yet" description="Explore a scholarship and add it to your application tracker." />}
      {trackedIds.length > 0 && list.status === "loading" && <LoadingList count={Math.min(trackedIds.length, 3)} label="Loading your applications" />}
      {list.status === "error" && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.status === "success" && rows.length > 0 && (
        <div className="applications-table">
          <div className="application-table-head">
            <span>Scholarship Name</span>
            <span>Application Deadline</span>
            <span>Application Status</span>
            <span>Last Updated</span>
            <span>Actions</span>
          </div>
          {rows.map((s) => {
            const tracked = applications[s.scholarship_id];
            const status = tracked?.status || "Interested";
            const href = `/scholarships/${encodeURIComponent(s.scholarship_id)}`;
            return (
              <div className="application-row" key={s.scholarship_id}>
                <div>
                  <Link href={href} className="application-name">
                    {s.name}
                  </Link>
                  <p>{s.provider_name || "Provider not specified"}</p>
                </div>
                <div data-label="Deadline">{dateLabel(s.application_deadline)}</div>
                <div data-label="Status">
                  <select
                    aria-label={`Application status for ${s.name}`}
                    value={status}
                    className={`application-status ${status === "Applied" ? "status-applied" : ""}`}
                    onChange={(e) => setStatus(s.scholarship_id, e.target.value)}
                  >
                    {applicationStatuses.map((option) => (
                      <option key={option}>{option}</option>
                    ))}
                  </select>
                </div>
                <div data-label="Last updated">{tracked?.updated ? dateLabel(tracked.updated) : "Not available"}</div>
                <Button variant="ghost" size="icon" asChild title="View details">
                  <Link href={href} aria-label={`View ${s.name}`}>
                    <ArrowUpRight />
                  </Link>
                </Button>
              </div>
            );
          })}
        </div>
      )}
      <SourceNote />
    </>
  );
}
