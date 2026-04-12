"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { DashboardPage } from "@/components/dashboard/dashboard-page";
import { useClashxAuth } from "@/lib/clashx-auth";
import { hasCompletedOnboardingForWallet } from "@/lib/onboarding-state";

export default function DashboardRoute() {
  const router = useRouter();
  const { ready, walletAddress } = useClashxAuth();
  const allowed = ready && hasCompletedOnboardingForWallet(walletAddress);

  useEffect(() => {
    if (ready && !allowed) {
      router.replace("/onboarding");
    }
  }, [allowed, ready, router]);

  if (!ready || !allowed) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center px-6 text-sm text-neutral-400">
        Checking launch access...
      </div>
    );
  }

  return <DashboardPage />;
}
