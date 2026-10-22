"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowDownWideNarrow, Search, SlidersHorizontal, X } from "lucide-react";

import { api } from "@/lib/api";
import { useApiQuery, useEligibility, useScholarshipSearch } from "@/lib/use-api";
import { categories, educationLevels, genders, schemeTypeLabels, states } from "./data";
import { useScholar } from "./store";
import { Button, ConfirmDialog, EmptyState, ErrorState, LoadingList, PageHeading, ScholarshipCard, SourceNote } from "./ui";

const PAGE_SIZE = 12;
const SORTS = [
  { value: "name", label: "Name (A–Z)" },
  { value: "amount_desc", label: "Scholarship Amount: Highest First" },
  { value: "deadline", label: "Deadline: Earliest First" },
  { value: "recently_verified", label: "Recently Verified" },
];
const emptyFilters = {
  education: "", state: "", scheme: "", marks: "", income: "", amount: "", gender: "", category: "", verified: "",
};

export function SelectField({ label, value, onChange, options, placeholder = "All", id }) {
  return (
    <label className="form-field" htmlFor={id}>
      <span>{label}</span>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{placeholder}</option>
        {options.map((o) => {
          const option = typeof o === "string" ? { value: o, label: o } : o;
          return (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          );
        })}
      </select>
    </label>
  );
}

/** Translate the filter form into API query parameters. Blank values are dropped by the API client. */
export function filtersToParams(query, filters, sort) {
  return {
    q: query.trim() || undefined,
    education_level: filters.education || undefined,
    state: filters.state || undefined,
    scheme_type: filters.scheme || undefined,
    student_percentage: filters.marks === "" ? undefined : filters.marks,
    student_income: filters.income === "" ? undefined : filters.income,
    min_award: filters.amount || undefined,
    gender: filters.gender || undefined,
    category: filters.category || undefined,
    verified_only: filters.verified === "verified" ? "true" : undefined,
    sort,
  };
}

export function Discovery({ initialQuery = "" }) {
  const { profile } = useScholar();
  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);
  const [sort, setSort] = useState("name");
  const [draft, setDraft] = useState(emptyFilters);
  const [filters, setFilters] = useState(emptyFilters);
  const [filterOpen, setFilterOpen] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQuery(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const options = useApiQuery((signal) => api.filterOptions({ signal }), []);
  const params = useMemo(() => filtersToParams(debouncedQuery, filters, sort), [debouncedQuery, filters, sort]);
  const search = useScholarshipSearch(params, PAGE_SIZE);

  const ids = useMemo(() => search.items.map((s) => s.scholarship_id), [search.items]);
  const eligibility = useEligibility(profile, ids);

  const education = options.data ? options.data.education_levels : educationLevels.map((l) => ({ value: l, label: l }));
  const filterCount = Object.values(filters).filter(Boolean).length;
  const update = (key, value) => setDraft((p) => ({ ...p, [key]: value }));
  const clearAll = () => {
    setQuery("");
    setDebouncedQuery("");
    setFilters(emptyFilters);
    setDraft(emptyFilters);
  };

  return (
    <>
      <PageHeading title="Find Scholarships" description="Discover opportunities that match your education, eligibility, and ambitions." />
      <div className="search-row">
        <div className="search-input">
          <Search size={19} />
          <input
            aria-label="Search scholarships"
            maxLength={200}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search scholarships by name, provider, course, or keyword..."
          />
          {query && (
            <Button variant="ghost" size="icon" aria-label="Clear search" onClick={() => setQuery("")}>
              <X />
            </Button>
          )}
        </div>
        <Button variant="outline" onClick={() => setFilterOpen(!filterOpen)}>
          <SlidersHorizontal />
          Filters {filterCount > 0 && `(${filterCount})`}
        </Button>
      </div>

      {filterOpen && (
        <section className="filter-panel" aria-label="Scholarship filters">
          <div className="filter-grid">
            <SelectField label="Education Level" value={draft.education} onChange={(v) => update("education", v)} options={education} />
            <SelectField label="State" value={draft.state} onChange={(v) => update("state", v)} options={options.data ? options.data.states : states} />
            <SelectField
              label="Scheme Level"
              value={draft.scheme}
              onChange={(v) => update("scheme", v)}
              options={[{ value: "central", label: schemeTypeLabels.central }, { value: "state", label: schemeTypeLabels.state }]}
            />
            <label className="form-field">
              <span>Your Academic Percentage</span>
              <input type="number" min={0} max={100} value={draft.marks} onChange={(e) => update("marks", e.target.value)} placeholder="e.g. 80" />
            </label>
            <label className="form-field">
              <span>Your Annual Family Income (₹)</span>
              <input type="number" min={0} value={draft.income} onChange={(e) => update("income", e.target.value)} placeholder="e.g. 300000" />
            </label>
            <label className="form-field">
              <span>Minimum Scholarship Amount (₹)</span>
              <input type="number" min={0} value={draft.amount} onChange={(e) => update("amount", e.target.value)} placeholder="Amount known and at least…" />
            </label>
            <SelectField label="Gender" value={draft.gender} onChange={(v) => update("gender", v)} options={genders.filter((g) => g !== "Prefer not to say")} />
            <SelectField label="Category" value={draft.category} onChange={(v) => update("category", v)} options={categories.filter((c) => c !== "Prefer not to say")} />
            <SelectField
              label="Verification"
              value={draft.verified}
              onChange={(v) => update("verified", v)}
              options={[{ value: "verified", label: "Verified records only" }]}
              placeholder="All records"
            />
          </div>
          <p className="inline-note">
            Percentage and income filters keep scholarships whose limit is unknown or satisfied. Filters match records that list the value or are open to all.
          </p>
          <div className="filter-actions">
            <Button variant="ghost" onClick={() => { setDraft(emptyFilters); setFilters(emptyFilters); }}>
              Clear Filters
            </Button>
            <Button onClick={() => { setFilters(draft); setFilterOpen(false); }}>Apply Filters</Button>
          </div>
        </section>
      )}

      <div className="results-bar">
        <p aria-live="polite">
          {search.status === "success" ? (
            <>
              <strong>{search.total}</strong> scholarships found
            </>
          ) : search.status === "error" ? (
            <>Scholarships could not be loaded</>
          ) : (
            <>Searching scholarships…</>
          )}
        </p>
        <label className="sort-select">
          <ArrowDownWideNarrow size={16} />
          <span className="sr-only">Sort scholarships</span>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {sort === "recently_verified" && (
        <p className="inline-note">No record has been verified yet, so there is no verification ranking; records are ordered by name.</p>
      )}
      {sort === "deadline" && (
        <p className="inline-note">The current data has no application deadlines, so records are ordered by name.</p>
      )}

      {search.status === "loading" && <LoadingList count={4} />}
      {search.status === "error" && <ErrorState error={search.error} onRetry={search.reload} />}
      {search.status === "success" && search.items.length === 0 && (
        <div className="empty-state">
          <Search size={28} />
          <h3>{search.total === 0 && filterCount === 0 && !debouncedQuery ? "No scholarships on record yet" : "No scholarships found"}</h3>
          <p>
            {search.total === 0 && filterCount === 0 && !debouncedQuery
              ? "The database is connected but contains no scholarship records. Import the ScholarPath data to see them here."
              : "Try another keyword or adjust your filters."}
          </p>
          {(filterCount > 0 || debouncedQuery) && (
            <Button variant="outline" onClick={clearAll}>
              Clear search and filters
            </Button>
          )}
        </div>
      )}
      {search.status === "success" && search.items.length > 0 && (
        <div className="discovery-grid directory-list">
          {search.items.map((s) => (
            <ScholarshipCard
              key={s.scholarship_id}
              scholarship={s}
              layout="row"
              eligibility={eligibility.byId[s.scholarship_id]}
              eligibilityFailed={eligibility.status === "error"}
            />
          ))}
        </div>
      )}
      {search.loadMoreError && <ErrorState error={search.loadMoreError} title="Couldn't load more scholarships" onRetry={search.loadMore} />}
      {search.hasMore && (
        <div className="load-more">
          <Button variant="outline" onClick={search.loadMore} disabled={search.loadingMore}>
            {search.loadingMore ? "Loading…" : `Load More (${search.items.length} of ${search.total})`}
          </Button>
        </div>
      )}
      <SourceNote />
    </>
  );
}

export function Saved() {
  const { saved, removeSaved, toggleSave, profile } = useScholar();
  const [status, setStatus] = useState("");
  const [remove, setRemove] = useState(null);
  const ids = useMemo(() => saved.slice(0, 50), [saved]);
  const list = useApiQuery(
    (signal) => api.listScholarships({ ids: ids.join(","), page_size: 50 }, { signal }),
    [ids.join(",")],
    { enabled: ids.length > 0 },
  );
  const items = list.data ? list.data.items : [];
  const foundIds = items.map((s) => s.scholarship_id);
  const eligibility = useEligibility(profile, foundIds);
  const unavailable = list.status === "success" ? ids.filter((id) => !foundIds.includes(id)) : [];
  const results = items.filter((s) => !status || eligibility.byId[s.scholarship_id]?.outcome === status);

  return (
    <>
      <PageHeading title="Saved Scholarships" description="Your shortlist of opportunities, all in one place." />
      <div className="saved-filters">
        <SelectField
          label="Eligibility"
          value={status}
          onChange={setStatus}
          options={[{ value: "eligible", label: "Eligible" }, { value: "not_eligible", label: "Not Eligible" }, { value: "cant_tell_yet", label: "Can't Tell Yet" }]}
        />
        <span>{ids.length === 0 ? "0 saved scholarships" : list.status === "success" ? `${results.length} saved scholarships` : "Loading…"}</span>
      </div>
      {unavailable.length > 0 && (
        <p className="inline-note" role="status">
          {unavailable.length} saved scholarship{unavailable.length === 1 ? " is" : "s are"} no longer in the database.{" "}
          <button type="button" className="text-link" onClick={() => removeSaved(unavailable)}>
            Remove {unavailable.length === 1 ? "it" : "them"} from my list
          </button>
        </p>
      )}
      {ids.length === 0 && <EmptyState title="You haven't saved any scholarships yet." />}
      {ids.length > 0 && list.status === "loading" && <LoadingList count={Math.min(ids.length, 3)} label="Loading saved scholarships" />}
      {list.status === "error" && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.status === "success" && results.length === 0 && items.length > 0 && <EmptyState title="No saved scholarships match these filters." action={false} />}
      {list.status === "success" && results.length > 0 && (
        <div className="discovery-grid">
          {results.map((s) => (
            <div key={s.scholarship_id}>
              <ScholarshipCard
                scholarship={s}
                eligibility={eligibility.byId[s.scholarship_id]}
                eligibilityFailed={eligibility.status === "error"}
              />
              <Button variant="ghost" size="sm" className="remove-saved" onClick={() => setRemove(s)}>
                <X />
                Remove from Saved
              </Button>
            </div>
          ))}
        </div>
      )}
      <SourceNote />
      <ConfirmDialog
        open={!!remove}
        onClose={() => setRemove(null)}
        onConfirm={() => {
          if (remove) toggleSave(remove.scholarship_id);
        }}
        title="Remove saved scholarship?"
        description={`${remove?.name || "This scholarship"} will be removed from your shortlist.`}
      />
    </>
  );
}

