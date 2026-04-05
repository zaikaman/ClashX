import { Suspense } from "react";

import { BuilderStudio } from "@/components/builder/builder-studio";

export default function BuilderPage() {
  return (
    <main className="flex h-[calc(100vh-64px)] w-full flex-1 flex-col overflow-hidden">
      <Suspense fallback={<div className="flex flex-1 items-center justify-center text-sm text-neutral-400">Loading builder...</div>}>
        <BuilderStudio />
      </Suspense>
    </main>
  );
}
