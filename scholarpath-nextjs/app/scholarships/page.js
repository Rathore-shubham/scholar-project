import { Discovery } from "@/features/scholarpath/discovery";

export const metadata = {
  title: "Find Scholarships",
  description: "Search and filter scholarship opportunities for Indian students by state, education level, category and more.",
};

export default async function ScholarshipsPage({ searchParams }) {
  const params = await searchParams;
  const q = typeof params?.q === "string" ? params.q.slice(0, 200) : "";
  // key: a new ?q= from the dashboard search box restarts the page state
  return <Discovery key={q} initialQuery={q} />;
}
