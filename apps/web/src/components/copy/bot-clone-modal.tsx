"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useClashxAuth } from "@/lib/clashx-auth";

type RuntimeRow = {
  runtime_id: string;
  bot_name: string;
};

type CloneResponse = {
  clone_id: string;
  source_runtime_id: string;
  source_bot_definition_id: string;
  new_bot_definition_id: string;
  created_by_user_id: string;
  created_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function BotCloneModal({
  runtime,
  open,
  onClose,
  onCloned,
}: {
  runtime: RuntimeRow | null;
  open: boolean;
  onClose: () => void;
  onCloned?: (botDefinitionId: string) => void;
}) {
  const { authenticated, login, walletAddress: authenticatedWallet, getAuthHeaders } = useClashxAuth();
  const [walletAddress, setWalletAddress] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("Cloned draft for custom edits");
  const [visibility, setVisibility] = useState<"private" | "unlisted" | "public">("private");
  const [status, setStatus] = useState<"idle" | "creating">("idle");
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<CloneResponse | null>(null);

  useEffect(() => {
    if (authenticatedWallet) {
      setWalletAddress(authenticatedWallet);
    }
  }, [authenticatedWallet]);

  useEffect(() => {
    if (!runtime) {
      setName("");
      setCreated(null);
      return;
    }
    setName(`${runtime.bot_name} Clone`);
  }, [runtime]);

  if (!open || !runtime) {
    return null;
  }

  const activeRuntime = runtime;

  async function createClone() {
    if (!authenticated) {
      login();
      return;
    }
    setStatus("creating");
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/bot-copy/clone`, {
        method: "POST",
        headers: await getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          source_runtime_id: activeRuntime.runtime_id,
          wallet_address: walletAddress,
          name,
          description,
          visibility,
        }),
      });
      const payload = (await response.json()) as CloneResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Clone creation failed" : "Clone creation failed");
      }
      const clonePayload = payload as CloneResponse;
      setCreated(clonePayload);
      onCloned?.(clonePayload.new_bot_definition_id);
    } catch (cloneError) {
      setError(cloneError instanceof Error ? cloneError.message : "Clone creation failed");
    } finally {
      setStatus("idle");
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid overflow-y-auto bg-[color:var(--bg-overlay)] p-4 backdrop-blur-sm md:p-8">
      <div className="m-auto grid w-full max-w-2xl gap-0 border border-[rgba(255,255,255,0.12)] bg-[#090a0a]">
        <div className="flex items-start justify-between gap-4 border-b border-[rgba(255,255,255,0.06)] p-6 md:p-8">
          <div className="grid gap-2">
            <span className="label text-[#74b97f]">clone flow</span>
            <h2 className="font-mono text-[clamp(1.4rem,4vw,2.4rem)] font-extrabold uppercase tracking-tight">Create editable draft</h2>
            <p className="text-sm leading-6 text-neutral-400">Fork the source bot into your own definition, then tune rules and runtime risk in your bot desk.</p>
          </div>
          <button type="button" onClick={onClose} className="label transition hover:text-neutral-50">✕</button>
        </div>

        <div className="grid gap-6 p-6 md:p-8">
          <div className="grid gap-3 bg-[#16181a] p-4 text-sm text-neutral-400">
            <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400">source summary</span>
            <p className="font-mono text-xl font-bold uppercase tracking-tight text-neutral-50">{activeRuntime.bot_name}</p>
            <p>Runtime ID: {activeRuntime.runtime_id}</p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Wallet
              <input
                value={walletAddress}
                onChange={(event) => setWalletAddress(event.target.value)}
                readOnly={Boolean(authenticatedWallet)}
              />
            </label>
            <label className="grid gap-1.5 text-sm text-neutral-400">
              Visibility
              <select
                value={visibility}
                onChange={(event) => setVisibility(event.target.value as "private" | "unlisted" | "public")}
                className="border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2.5 text-neutral-50"
              >
                <option value="private">private</option>
                <option value="unlisted">unlisted</option>
                <option value="public">public</option>
              </select>
            </label>
          </div>

          <label className="grid gap-1.5 text-sm text-neutral-400">
            Draft name
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>

          <label className="grid gap-1.5 text-sm text-neutral-400">
            Description
            <input value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>

          {error ? <p className="text-sm text-[#dce85d]">{error}</p> : null}

          {created ? (
            <div className="grid gap-2 bg-[#16181a] p-4 text-sm text-neutral-400">
              <span className="label text-[#74b97f]">clone created</span>
              <p>Draft bot definition ID: {created.new_bot_definition_id}</p>
              <Link
                href={`/bots/${created.new_bot_definition_id}`}
                className="w-fit rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2 text-[0.6rem] font-semibold uppercase tracking-wider transition hover:border-[#74b97f] hover:text-[#74b97f]"
              >
                open draft runtime
              </Link>
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => void createClone()}
              disabled={status === "creating"}
              className="bg-[#dce85d] px-6 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-[#090a0a] transition hover:bg-[#e8f06d] disabled:opacity-50"
            >
              {status === "creating" ? "creating clone" : "create clone"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-[rgba(255,255,255,0.12)] px-6 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
            >
              close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
