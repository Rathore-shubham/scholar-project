import { Details } from "@/features/scholarpath/details";

export const metadata = {
  title: "Scholarship details",
  description: "Review a scholarship's criteria, funding, documents, sources and verification status.",
};

export default async function ScholarshipDetailsPage({ params }) {
  const { id } = await params;
  return <Details id={id} />;
}
