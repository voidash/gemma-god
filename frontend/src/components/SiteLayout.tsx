import type { ReactNode } from "react";
import { SiteHeader } from "@/components/SiteHeader";

export function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <SiteHeader />
      <main className="flex-1">{children}</main>
    </div>
  );
}
