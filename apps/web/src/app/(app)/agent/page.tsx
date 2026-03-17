"use client";

import { useState } from "react";

import { AgentAuthorizationPanel } from "@/components/pacifica/agent-authorization-panel";
import { PacificaOnboardingChecklist } from "@/components/pacifica/onboarding-checklist";

export default function AgentDeskPage() {
  const [guideOpen, setGuideOpen] = useState(false);

  return (
    <main className="shell grid gap-8 pb-10 md:pb-12">
      <PacificaOnboardingChecklist
        open={guideOpen}
        onClose={() => setGuideOpen(false)}
        mode="agent"
      />

      <section className="flex flex-wrap items-center justify-between gap-4 rounded-[2rem] border border-[rgba(255,255,255,0.06)] bg-[#16181a] px-6 py-5">
        <div className="grid gap-2">
          <span className="label text-[#dce85d]">Agent Desk</span>
          <p className="max-w-2xl text-sm leading-7 text-neutral-400">
            Bind the delegated Pacifica signer here, then head back to the builder once the runtime is active.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setGuideOpen(true)}
          className="inline-flex items-center rounded-full border border-[rgba(255,255,255,0.12)] px-5 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-300 transition hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          Open setup guide
        </button>
      </section>

      <AgentAuthorizationPanel />
    </main>
  );
}
