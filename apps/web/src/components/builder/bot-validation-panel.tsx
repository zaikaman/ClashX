"use client";

import { useState } from "react";

type ValidationResult = {
  valid: boolean;
  issues: string[];
};

type SimulationResult = {
  valid: boolean;
  triggered: boolean;
  evaluated_conditions: number;
  planned_actions: number;
  market_context: Record<string, unknown>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function BotValidationPanel({
  authoringMode,
  visibility,
  rulesVersion,
  rulesJson,
}: {
  authoringMode: "visual";
  visibility: string;
  rulesVersion: number;
  rulesJson: Record<string, unknown>;
}) {
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [status, setStatus] = useState<"idle" | "validating" | "simulating">("idle");
  const [error, setError] = useState<string | null>(null);

  async function runValidation() {
    setStatus("validating");
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/bots/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          authoring_mode: authoringMode,
          visibility,
          rules_version: rulesVersion,
          rules_json: rulesJson,
        }),
      });
      const payload = (await response.json()) as ValidationResult | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Validation failed" : "Validation failed");
      }
      setValidation(payload as ValidationResult);
    } catch (validationError) {
      setError(validationError instanceof Error ? validationError.message : "Validation failed");
    } finally {
      setStatus("idle");
    }
  }

  async function runSimulation() {
    setStatus("simulating");
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/builder/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rules_json: rulesJson }),
      });
      const payload = (await response.json()) as SimulationResult | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Simulation failed" : "Simulation failed");
      }
      setSimulation(payload as SimulationResult);
    } catch (simulationError) {
      setError(simulationError instanceof Error ? simulationError.message : "Simulation failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <section className="grid gap-6 rounded-3xl border border-[rgba(255,255,255,0.06)] bg-[#16181a] p-6 md:p-8 xl:grid-cols-[0.92fr_1.08fr] xl:items-start">
      <div className="grid self-start gap-4">
        <div className="grid gap-2">
          <span className="label text-[#74b97f]">Flight check</span>
          <p className="font-mono text-[clamp(1.5rem,3vw,2.4rem)] font-bold uppercase leading-[0.94] tracking-[-0.03em] text-neutral-50">
            Test the draft before you launch it.
          </p>
          <p className="text-sm leading-7 text-neutral-400">
            Run schema validation to catch blockers, then simulate the draft so you know whether the rules are likely to trigger the way you expect.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={runValidation}
            disabled={status !== "idle"}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d] disabled:opacity-60"
          >
            {status === "validating" ? "Checking schema..." : "Run schema check"}
          </button>
          <button
            type="button"
            onClick={runSimulation}
            disabled={status !== "idle"}
            className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#74b97f] hover:text-[#74b97f] disabled:opacity-60"
          >
            {status === "simulating" ? "Simulating..." : "Preview behavior"}
          </button>
        </div>

        {error ? (
          <div className="rounded-2xl border border-[#dce85d]/30 bg-[rgba(220,232,93,0.1)] px-4 py-4 text-sm leading-7 text-neutral-50">
            {error}
          </div>
        ) : null}
      </div>

      <div className="grid self-start gap-4 md:grid-cols-2">
        <article className="grid gap-3 rounded-2xl bg-[#090a0a] p-5">
          <span className="label text-[#dce85d]">Schema check</span>
          <div
            className={`font-mono text-2xl font-bold uppercase ${validation?.valid ? "text-[#74b97f]" : validation ? "text-[#dce85d]" : "text-neutral-50"}`}
          >
            {validation ? (validation.valid ? "Ready" : "Blocked") : "Waiting"}
          </div>

          {validation?.issues.length ? (
            <div className="grid gap-2 text-sm leading-6 text-neutral-400">
              {validation.issues.map((issue) => (
                <p key={issue}>{issue}</p>
              ))}
            </div>
          ) : (
            <p className="text-sm leading-6 text-neutral-400">
              {validation ? "No blocking schema issues were reported." : "Run this first to catch deploy blockers before saving the draft."}
            </p>
          )}
        </article>

        <article className="grid gap-3 rounded-2xl bg-[#090a0a] p-5">
          <span className="label text-[#74b97f]">Behavior preview</span>
          <div className="font-mono text-2xl font-bold uppercase text-neutral-50">
            {simulation ? (simulation.triggered ? "Triggered" : "Standby") : "Waiting"}
          </div>
          <p className="text-sm leading-6 text-neutral-400">
            {simulation
              ? `${simulation.evaluated_conditions} condition(s) checked and ${simulation.planned_actions} action(s) prepared.`
              : "Run the preview to see whether the current draft would fire and how many actions it plans to take."}
          </p>
        </article>
      </div>
    </section>
  );
}
