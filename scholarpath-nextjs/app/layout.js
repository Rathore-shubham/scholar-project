import "./globals.css";
import { Providers } from "@/components/providers";

export const metadata = {
  title: { default: "ScholarPath AI", template: "%s — ScholarPath AI" },
  description: "Scholarship discovery and eligibility for Indian students.",
  openGraph: {
    title: "ScholarPath AI",
    description: "Scholarship discovery and eligibility for Indian students.",
    type: "website",
  },
  twitter: { card: "summary_large_image" },
};

export const viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        {/* Same web fonts as the original Lovable app. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;450;500;550;600;650;700;750&display=swap"
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
