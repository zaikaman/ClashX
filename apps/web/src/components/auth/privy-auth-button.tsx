"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { useClashxAuth } from "@/lib/clashx-auth";

function shortAddress(value: string | null) {
  if (!value) {
    return "No wallet connected";
  }
  return `${value.slice(0, 4)}...${value.slice(-4)}`;
}

function isWalletPromptCancelled(error: unknown) {
  if (!(error instanceof Error)) {
    return false;
  }

  const message = error.message.toLowerCase();
  return (
    message.includes("user rejected") ||
    message.includes("user declined") ||
    message.includes("user cancelled") ||
    message.includes("user canceled") ||
    message.includes("request aborted") ||
    message.includes("closed")
  );
}

export function PrivyAuthButton() {
  const { ready, authenticated, login, logout, walletAddress, availableWallets, connectWallet } = useClashxAuth();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [portalRoot, setPortalRoot] = useState<HTMLElement | null>(null);
  const [pendingWalletId, setPendingWalletId] = useState<string | null>(null);
  const [pickerError, setPickerError] = useState<string | null>(null);

  useEffect(() => {
    setPortalRoot(document.body);
  }, []);

  if (!ready) {
    return <div className="text-xs uppercase tracking-[0.16em] text-neutral-500">Checking wallet</div>;
  }

  if (!authenticated) {
    return (
      <>
        <button
          type="button"
          onClick={() => {
            if (availableWallets.length > 0) {
              setPickerError(null);
              setPickerOpen(true);
              return;
            }
            login();
          }}
          className="rounded-full border border-[rgba(255,255,255,0.12)] px-4 py-2.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition-all duration-200 hover:border-[#dce85d] hover:text-[#dce85d]"
        >
          Connect wallet
        </button>

        {pickerOpen && portalRoot
          ? createPortal(
              <div className="fixed inset-0 z-[200] flex items-center justify-center bg-[rgba(5,7,9,0.76)] px-4 backdrop-blur-sm">
                <button
                  type="button"
                  aria-label="Close wallet picker"
                  onClick={() => setPickerOpen(false)}
                  className="absolute inset-0"
                />
                <div className="relative w-full max-w-md overflow-hidden border border-[rgba(220,232,93,0.18)] bg-[#111416] shadow-[0_28px_80px_rgba(0,0,0,0.52)]">
                  <div className="border-b border-[rgba(255,255,255,0.08)] bg-[linear-gradient(135deg,rgba(220,232,93,0.14),rgba(220,232,93,0.02)_48%,transparent_100%)] px-6 py-5">
                    <div className="text-[0.62rem] font-semibold uppercase tracking-[0.18em] text-[#dce85d]">wallet access</div>
                    <h3 className="mt-2 text-xl font-semibold text-neutral-50">Pick the wallet you want to use</h3>
                  </div>

                  <div className="grid gap-3 p-4">
                    {availableWallets.map((wallet) => (
                      <button
                        key={wallet.id}
                        type="button"
                        onClick={async () => {
                          setPendingWalletId(wallet.id);
                          setPickerError(null);
                          try {
                            await connectWallet({ walletClientType: wallet.id });
                            setPickerOpen(false);
                          } catch (error) {
                            if (isWalletPromptCancelled(error)) {
                              setPickerError(null);
                              return;
                            }
                            if (error instanceof Error) {
                              setPickerError(error.message);
                            } else {
                              setPickerError("Wallet connection failed.");
                            }
                          } finally {
                            setPendingWalletId(null);
                          }
                        }}
                        disabled={Boolean(pendingWalletId)}
                        className="group grid gap-1 border border-[rgba(255,255,255,0.08)] bg-[#0b0d0f] px-4 py-4 text-left transition duration-200 hover:border-[#dce85d] hover:bg-[#121610]"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <span className="text-sm font-semibold uppercase tracking-[0.14em] text-neutral-50">{wallet.label}</span>
                          <span className="text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-500 transition group-hover:text-[#dce85d]">
                            {pendingWalletId === wallet.id ? "connecting" : "select"}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>

                  {pickerError ? (
                    <div className="border-t border-[rgba(255,255,255,0.08)] px-4 py-3 text-sm text-[#dce85d]">
                      {pickerError}
                    </div>
                  ) : null}

                  <div className="flex items-center justify-between border-t border-[rgba(255,255,255,0.08)] px-4 py-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-neutral-500">
                      {availableWallets.length} wallet{availableWallets.length === 1 ? "" : "s"} detected
                    </div>
                    <button
                      type="button"
                      onClick={() => setPickerOpen(false)}
                      disabled={Boolean(pendingWalletId)}
                      className="rounded-full border border-[rgba(255,255,255,0.08)] px-3 py-1.5 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-neutral-50 hover:text-neutral-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>,
              portalRoot,
            )
          : null}
      </>
    );
  }

  return (
    <div className="grid gap-2 sm:grid-cols-[1fr_auto] sm:items-center">
      <span className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[#090a0a] px-3 py-2 text-sm font-medium text-neutral-50">
        {shortAddress(walletAddress)}
      </span>
      <button
        type="button"
        onClick={logout}
        className="rounded-full border border-[rgba(255,255,255,0.06)] px-4 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-neutral-400 transition hover:border-[#dce85d] hover:text-[#dce85d]"
      >
        Sign out
      </button>
    </div>
  );
}
