"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function RouteError({ error, reset }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="api-error" role="alert">
      <h3>This page didn't load</h3>
      <p>Something went wrong while rendering this page. You can try again or go back to the dashboard.</p>
      <div className="flex flex-wrap justify-center gap-2">
        <Button onClick={() => reset()}>Try again</Button>
        <Button variant="outline" asChild>
          <a href="/">Go to dashboard</a>
        </Button>
      </div>
    </div>
  );
}
