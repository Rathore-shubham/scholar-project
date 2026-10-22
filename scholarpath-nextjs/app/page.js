import { Dashboard } from "@/features/scholarpath/dashboard";

export const metadata = {
  title: { absolute: "Student Dashboard — ScholarPath AI" },
  description: "Explore scholarship records that match your profile, your saved opportunities and your application progress with ScholarPath AI.",
};

export default function DashboardPage() {
  return <Dashboard />;
}
