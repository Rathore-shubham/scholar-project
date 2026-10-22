import { z } from "zod";

// ---------------------------------------------------------------------------------------------------------------
// Reference lists for the forms. These are fixed vocabularies (states, levels), NOT scholarship data:
// every scholarship shown anywhere in the app comes from the API.
// ---------------------------------------------------------------------------------------------------------------

export const educationLevels = [
  "Class 8", "Class 9", "Class 10", "Class 11", "Class 12", "Diploma", "Undergraduate", "Postgraduate",
];

export const states = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
  "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
  "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal",
  "Andaman and Nicobar Islands", "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
  "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
];

export const categories = ["General", "OBC", "SC", "ST", "EWS", "EBC", "SBC", "Prefer not to say"];
export const genders = ["Male", "Female", "Other", "Prefer not to say"];
export const schemePreferences = ["All schemes", "Central", "State"];
export const schemeTypeLabels = { central: "Central scheme", state: "State scheme", other: "Other scheme" };

export const applicationStatuses = [
  "Interested", "Preparing Documents", "Ready to Apply", "Applied", "Awarded", "Not Selected",
];

export const OUTCOME_LABELS = { eligible: "Eligible", not_eligible: "Not Eligible", cant_tell_yet: "Can't Tell Yet" };
export const CRITERION_STATUS_LABELS = {
  pass: "Meets requirement",
  fail: "Does not meet requirement",
  missing: "Information missing",
  unable_to_verify: "Unable to verify",
};
export const VERIFICATION_LABELS = { verified: "Verified", pending: "Unverified", needs_review: "Needs review", rejected: "Rejected" };

// ---------------------------------------------------------------------------------------------------------------
// Student profile (stored only in this browser; sent to the API only when a check is requested)
// ---------------------------------------------------------------------------------------------------------------

export const profileSchema = z.object({
  name: z.string().trim().min(2, "Enter your full name").max(100),
  dob: z
    .string()
    .refine((v) => !!v && v >= "1900-01-01" && v <= new Date().toISOString().slice(0, 10), "Enter a valid date of birth"),
  state: z.string().min(1, "Select your state").max(60),
  education: z.enum(educationLevels, { errorMap: () => ({ message: "Select your education level" }) }),
  course: z.string().trim().min(2, "Enter your current course").max(100),
  institution: z.string().trim().min(2, "Enter your institution").max(150),
  percentage: z.coerce.number().min(0).max(100, "Percentage must be between 0 and 100"),
  income: z.coerce.number().min(0).max(100000000),
  category: z.string().max(60),
  gender: z.string().max(40),
  preference: z.string().max(60),
});

// What is allowed back out of localStorage: a partial profile (every field optional), so an unfinished profile persists.
export const storedProfileSchema = z
  .object({
    name: z.string().max(100), dob: z.string().max(10), state: z.string().max(60), education: z.string().max(40),
    course: z.string().max(100), institution: z.string().max(150),
    percentage: z.union([z.string().max(10), z.number()]), income: z.union([z.string().max(15), z.number()]),
    category: z.string().max(60), gender: z.string().max(40), preference: z.string().max(60),
  })
  .partial();

export const emptyProfile = {
  name: "", dob: "", state: "", education: "", course: "", institution: "",
  percentage: "", income: "", category: "", gender: "", preference: "",
};

export const profileCompletionFields = ["name", "dob", "state", "education", "course", "institution", "percentage", "income"];

export function profileCompletion(profile) {
  const filled = profileCompletionFields.filter((k) => String(profile[k] ?? "").trim() !== "").length;
  return Math.round((filled / profileCompletionFields.length) * 100);
}

// Scholarship ids are opaque strings from the API (e.g. "SP-E7F4708E55").
export const SCHOLARSHIP_ID_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;
