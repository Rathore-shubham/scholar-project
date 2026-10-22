"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { z } from "zod";

import {
  SCHOLARSHIP_ID_PATTERN,
  applicationStatuses,
  emptyProfile,
  profileSchema,
  storedProfileSchema,
} from "./data";

// Profile, saved scholarships and self-reported application statuses live only in this browser (no accounts yet).
// Starts EMPTY: no demo student and no pre-saved scholarships. Versioned key: v1 belonged to the mock prototype.
const STORAGE_KEY = "scholarpath.workspace.v2";

const storageSchema = z.object({
  profile: storedProfileSchema,
  saved: z.array(z.string().regex(SCHOLARSHIP_ID_PATTERN)).max(100),
  applications: z.record(
    z.string().regex(SCHOLARSHIP_ID_PATTERN),
    z.object({ status: z.enum(applicationStatuses), updated: z.string().max(30) }),
  ),
});

const Context = createContext(null);

export function ScholarProvider({ children }) {
  const [profile, setProfile] = useState(emptyProfile);
  const [saved, setSaved] = useState([]);
  const [applications, setApplications] = useState({});
  const [ready, setReady] = useState(false);
  const [notice, notify] = useState("");

  // Hydrate after mount so the server-rendered markup and the first client render match.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const result = storageSchema.safeParse(JSON.parse(raw));
        if (result.success) {
          setProfile({ ...emptyProfile, ...result.data.profile });
          setSaved(result.data.saved);
          setApplications(result.data.applications);
        }
      }
    } catch {
      notify("Your saved data could not be loaded from this browser.");
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ profile, saved, applications }));
    } catch {
      notify("Changes could not be saved on this device.");
    }
  }, [profile, saved, applications, ready]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => notify(""), 4500);
    return () => clearTimeout(timer);
  }, [notice]);

  const value = useMemo(
    () => ({
      profile,
      ready,
      saveProfile: (next) => {
        const parsed = profileSchema.safeParse(next);
        if (parsed.success) {
          setProfile({ ...emptyProfile, ...parsed.data });
          notify("Profile saved on this device.");
        }
      },
      saved,
      toggleSave: (id) => {
        if (!SCHOLARSHIP_ID_PATTERN.test(id)) return;
        setSaved((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
      },
      removeSaved: (ids) => setSaved((prev) => prev.filter((id) => !ids.includes(id))),
      applications,
      setStatus: (id, status) => {
        if (!SCHOLARSHIP_ID_PATTERN.test(id) || !applicationStatuses.includes(status)) return;
        setApplications((prev) => ({ ...prev, [id]: { status, updated: new Date().toISOString().slice(0, 10) } }));
        notify("Application status updated.");
      },
      removeApplications: (ids) =>
        setApplications((prev) => Object.fromEntries(Object.entries(prev).filter(([id]) => !ids.includes(id)))),
      notice,
      notify,
    }),
    [profile, ready, saved, applications, notice],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useScholar() {
  const context = useContext(Context);
  if (!context) throw new Error("ScholarProvider is required");
  return context;
}
