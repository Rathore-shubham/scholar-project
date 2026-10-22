"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CalendarDays, CircleCheck, FileText, Info, Search } from "lucide-react";

import { api, toApiProfile } from "@/lib/api";
import { useApiQuery, useEligibility } from "@/lib/use-api";
import { profileCompletion } from "./data";
import { useScholar } from "./store";
import { Button, ErrorState, LoadingList, ScholarshipCard, SourceNote } from "./ui";

export function Dashboard() {
  const { profile, saved } = useScholar();
  const router = useRouter();
  const [search, setSearch] = useState("");
  const completion = profileCompletion(profile);

  const options = useApiQuery((signal) => api.filterOptions({ signal }), []);

  // "Opportunities for you": records matching the profile's own filters (unknown requirements are kept, never treated as 0).
  const apiProfile = toApiProfile(profile);
  const scheme = profile.preference === "Central" ? "central" : profile.preference === "State" ? "state" : undefined;
  const params = useMemo(
    () => ({
      education_level: apiProfile.education_level,
      state: apiProfile.state,
      category: apiProfile.category,
      gender: apiProfile.gender,
      student_percentage: apiProfile.percentage,
      student_income: apiProfile.family_income,
      scheme_type: scheme,
      page_size: 3,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(apiProfile), scheme],
  );
  const recommended = useApiQuery((signal) => api.listScholarships(params, { signal }), [JSON.stringify(params)]);
  const items = recommended.data ? recommended.data.items : [];
  const eligibility = useEligibility(profile, items.map((s) => s.scholarship_id));

  const total = options.data ? options.data.total_scholarships : null;
  const verified = options.data ? options.data.verified_scholarships : null;

  return (
    <>
      <div className="dashboard-intro">
        <div className="dashboard-kicker">SCHOLARPATH / INTELLIGENCE WORKSPACE</div>
        <div className="welcome-heading">
          <div>
            <h1>
              Your ambition deserves
              <br className="desktop-break" /> an opportunity.
            </h1>
            <p>Discover scholarships that fit your education, your circumstances, and your goals.</p>
          </div>
        </div>
        <form
          className="dashboard-search"
          onSubmit={(e) => {
            e.preventDefault();
            const q = search.trim();
            router.push(q ? `/scholarships?q=${encodeURIComponent(q)}` : "/scholarships");
          }}
        >
          <Search size={19} />
          <input aria-label="Search scholarships" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by scholarship, course, or provider..." />
          <Button type="submit">
            Search Scholarships <ArrowRight />
          </Button>
        </form>
      </div>

      <section className="opportunity-summary" aria-label="Your opportunity summary">
        <div>
          <span>Education level</span>
          <strong>{profile.education || "Complete your profile"}</strong>
        </div>
        <div>
          <span>Scholarships on record</span>
          <strong>{total === null ? (options.status === "error" ? "Unavailable" : "…") : `${total} records`}</strong>
        </div>
        <div>
          <span>Saved for later</span>
          <strong>{saved.length} scholarships</strong>
        </div>
        <div>
          <span>Verified records</span>
          <strong>{verified === null ? (options.status === "error" ? "Unavailable" : "…") : `${verified} of ${total}`}</strong>
        </div>
      </section>

      <div className={`profile-banner ${completion < 100 ? "profile-banner-incomplete" : ""}`}>
        <span className="profile-banner-icon">{completion === 100 ? <CircleCheck size={22} /> : <Info size={22} />}</span>
        <div className="min-w-0">
          <strong>{completion === 100 ? "Your profile is ready for matching." : `Complete your profile · ${completion}%`}</strong>
          <p>
            {completion === 100
              ? "Review your education and income details to keep matches accurate."
              : "Add your education and income details so more criteria can be compared with your profile."}
          </p>
        </div>
        <Button variant="link" asChild>
          <Link href="/profile">
            {completion === 100 ? "View Profile" : "Complete Profile"} <ArrowRight size={16} />
          </Link>
        </Button>
      </div>

      <div className="dashboard-columns">
        <section className="recommendations">
          <div className="section-heading">
            <div>
              <div className="section-kicker">A STARTING POINT</div>
              <h2>
                Opportunities for you{" "}
                {recommended.status === "success" && <span className="count-label">{recommended.data.total} on record match</span>}
              </h2>
              <p>Records that list your details or are open to all. Unverified records are labelled and are not confirmations.</p>
            </div>
            <Link href="/scholarships" className="text-link">
              Browse directory <ArrowRight size={14} />
            </Link>
          </div>
          <div className="recommended-grid dashboard-opportunity-list">
            {recommended.status === "loading" && <LoadingList count={3} />}
            {recommended.status === "error" && <ErrorState error={recommended.error} onRetry={recommended.reload} />}
            {recommended.status === "success" && items.length === 0 && (
              <p className="dashboard-no-match">
                {recommended.data.total === 0 && Object.keys(params).length <= 1
                  ? "No scholarships are on record yet. Import the ScholarPath data to see opportunities here."
                  : "No records match your current profile. Review your details or browse the full directory."}
              </p>
            )}
            {recommended.status === "success" &&
              items.map((s) => (
                <ScholarshipCard
                  key={s.scholarship_id}
                  scholarship={s}
                  layout="row"
                  eligibility={eligibility.byId[s.scholarship_id]}
                  eligibilityFailed={eligibility.status === "error"}
                />
              ))}
          </div>
          <SourceNote />
          <div className="next-step">
            <div className="next-step-icon">
              <FileText size={24} />
            </div>
            <div className="min-w-0">
              <h3>Application tracker</h3>
              <p>Keep your application progress in one place.</p>
            </div>
            <Button variant="outline" asChild>
              <Link href="/applications">
                My Applications <ArrowRight />
              </Link>
            </Button>
          </div>
        </section>
        <aside className="deadline-section">
          <div className="section-heading">
            <div>
              <h2>Upcoming Deadlines</h2>
              <p>Application dates.</p>
            </div>
            <CalendarDays size={19} className="text-muted-foreground" />
          </div>
          <p className="inline-note">
            The current scholarship data has no application dates, so no deadlines can be listed. Open a scholarship's official website to find its dates.
          </p>
          <Link href="/scholarships" className="deadline-view-all">
            Explore all scholarships <ArrowRight size={15} />
          </Link>
          <div className="quick-tip">
            <span>
              <Info size={17} /> Good to know
            </span>
            <p>Every scholarship has its own requirements. Review the criteria before you apply.</p>
            <Link href="/eligibility" className="text-link">
              Check your eligibility <ArrowRight size={14} />
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}
