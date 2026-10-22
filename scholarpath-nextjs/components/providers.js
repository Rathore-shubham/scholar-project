"use client";

import { AppShell } from "@/features/scholarpath/shell";
import { ScholarProvider } from "@/features/scholarpath/store";

/** Client-side providers and the application shell, wrapped around every route by app/layout.js. */
export function Providers({ children }) {
  return (
    <ScholarProvider>
      <AppShell>{children}</AppShell>
    </ScholarProvider>
  );
}
