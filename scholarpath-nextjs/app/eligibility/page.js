import { ProfileForm } from "@/features/scholarpath/profile";

export const metadata = {
  title: "Eligibility Checker",
  description: "Compare your details with a scholarship's listed requirements, with criterion-by-criterion explanations.",
};

export default function EligibilityPage() {
  return <ProfileForm checker />;
}
