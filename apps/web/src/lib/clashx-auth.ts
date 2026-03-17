"use client";

import { useCallback, useMemo } from "react";

import { usePrivy } from "@privy-io/react-auth";

type LinkedAccount = {
  type?: string;
  address?: string;
  chainType?: string;
  chain_type?: string;
};

type PrivyLikeUser = {
  linkedAccounts?: LinkedAccount[];
  linked_accounts?: LinkedAccount[];
};

function extractWalletAddress(user: unknown): string | null {
  const payload = (user ?? {}) as PrivyLikeUser;
  const linkedAccounts = payload.linkedAccounts ?? payload.linked_accounts ?? [];
  const solanaWallet = linkedAccounts.find(
    (account) => account.address && (account.chainType === "solana" || account.chain_type === "solana"),
  );
  if (solanaWallet?.address) {
    return solanaWallet.address;
  }
  const genericWallet = linkedAccounts.find((account) => account.type === "wallet" && account.address);
  return genericWallet?.address ?? null;
}

export function useClashxAuth() {
  const { ready, authenticated, login, logout, user, getAccessToken } = usePrivy();
  const walletAddress = useMemo(() => extractWalletAddress(user), [user]);

  const getAuthHeaders = useCallback(
    async (headersInit?: HeadersInit) => {
      const token = await getAccessToken();
      if (!token) {
        throw new Error("Privy access token unavailable");
      }
      const headers = new Headers(headersInit);
      headers.set("Authorization", `Bearer ${token}`);
      return headers;
    },
    [getAccessToken],
  );

  return {
    ready,
    authenticated,
    login,
    logout,
    user,
    walletAddress,
    getAccessToken,
    getAuthHeaders,
  };
}