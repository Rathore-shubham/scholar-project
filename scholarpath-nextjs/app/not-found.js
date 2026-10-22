import Link from "next/link";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="empty-state">
      <h1 className="text-4xl font-semibold">404</h1>
      <h2 className="text-lg font-semibold">Page not found</h2>
      <p>The page you're looking for doesn't exist or has been moved.</p>
      <Link
        href="/"
        className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
      >
        Go to dashboard
      </Link>
    </div>
  );
}
