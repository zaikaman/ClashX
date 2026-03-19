"use client";

import { CheckCircle2, X } from "lucide-react";
import { useEffect, useState } from "react";

import {
  BuilderGraphStudio,
  type BuilderNoticePayload,
} from "@/components/builder/builder-graph-studio";
import {
  PacificaOnboardingChecklist,
  type PacificaOnboardingStatus,
} from "@/components/pacifica/onboarding-checklist";

export function BuilderStudio() {
  const [notice, setNotice] = useState<(BuilderNoticePayload & { id: number }) | null>(null);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [builderWalletAddress, setBuilderWalletAddress] = useState("");
  const [onboardingStatus, setOnboardingStatus] = useState<PacificaOnboardingStatus>({
    ready: false,
    blocker: "Sign in with your trading wallet before you deploy.",
    fundingVerified: false,
    appAccessVerified: false,
    agentAuthorized: false,
  });

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => {
      setNotice((current) => current?.id === notice.id ? null : current);
    }, 4200);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  function handleNotice(nextNotice: BuilderNoticePayload) {
    setNotice({ id: Date.now(), ...nextNotice });
  }

  return (
    <div className="relative flex h-full min-h-0 flex-1 flex-col">
      <PacificaOnboardingChecklist
        open={onboardingOpen}
        onClose={() => setOnboardingOpen(false)}
        mode="builder"
        onStatusChange={setOnboardingStatus}
        walletAddressOverride={builderWalletAddress}
      />
      {notice ? (
        <div className="absolute right-4 top-4 z-20">
          <div className="w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[rgba(220,232,93,0.22)] bg-[linear-gradient(180deg,rgba(18,20,18,0.96),rgba(9,10,10,0.98))] shadow-[0_18px_40px_rgba(0,0,0,0.38)]">
            <div className="flex items-start gap-3 border-b border-[rgba(255,255,255,0.05)] px-4 py-3">
              <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-2xl border border-[rgba(220,232,93,0.16)] bg-[rgba(220,232,93,0.08)] text-[#dce85d]">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[0.62rem] font-semibold uppercase tracking-[0.22em] text-[#dce85d]/80">
                  {notice.eyebrow}
                </div>
                <div className="mt-1 text-sm font-semibold text-neutral-50">{notice.title}</div>
                <div className="mt-1 text-xs leading-5 text-neutral-400">{notice.detail}</div>
              </div>
              <button
                type="button"
                onClick={() => setNotice(null)}
                aria-label="Dismiss notification"
                className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.03)] text-neutral-500 transition hover:border-[rgba(255,255,255,0.14)] hover:bg-[rgba(255,255,255,0.06)] hover:text-neutral-200"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <div className="h-1 w-full bg-[rgba(255,255,255,0.04)]">
              <div className="h-full w-full origin-left animate-[builder-toast-shrink_4.2s_linear_forwards] bg-[#dce85d]" />
            </div>
          </div>
        </div>
      ) : null}
      <BuilderGraphStudio
        onNotice={handleNotice}
        onboardingStatus={onboardingStatus}
        onOpenOnboardingGuide={() => setOnboardingOpen(true)}
        onWalletAddressChange={setBuilderWalletAddress}
      />
    </div>
  );
}
