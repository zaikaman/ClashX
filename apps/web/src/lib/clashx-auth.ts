"use client";

import { useCallback, useMemo, type MouseEvent } from "react";

import { useLogin, useLoginWithSiws, usePrivy } from "@privy-io/react-auth";

import { encodeBase58 } from "@/lib/base58";

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

type SolanaSignResult =
  | Uint8Array
  | {
      publicKey?: { toString(): string };
      signature: Uint8Array;
    };

type SolanaProvider = {
  publicKey?: { toString(): string };
  connect: (options?: { onlyIfTrusted?: boolean }) => Promise<{ publicKey: { toString(): string } }>;
  signMessage: (message: Uint8Array, display?: "utf8") => Promise<SolanaSignResult>;
  isPhantom?: boolean;
  isSolflare?: boolean;
  isBackpack?: boolean;
};

export type AvailableSolanaWallet = {
  id: string;
  label: string;
};

type SolanaWindow = Window & {
  solana?: SolanaProvider;
  phantom?: { solana?: SolanaProvider };
  solflare?: SolanaProvider;
  backpack?: { solana?: SolanaProvider };
};

function getInjectedSolanaProvider(): SolanaProvider | null {
  if (typeof window === "undefined") {
    return null;
  }

  const browserWindow = window as SolanaWindow;
  return (
    browserWindow.phantom?.solana ??
    browserWindow.backpack?.solana ??
    browserWindow.solflare ??
    browserWindow.solana ??
    null
  );
}

function listInjectedSolanaProviders(): Array<{ wallet: AvailableSolanaWallet; provider: SolanaProvider }> {
  if (typeof window === "undefined") {
    return [];
  }

  const browserWindow = window as SolanaWindow;
  const candidates: Array<{ wallet: AvailableSolanaWallet; provider: SolanaProvider | null | undefined }> = [
    { wallet: { id: "phantom", label: "Phantom" }, provider: browserWindow.phantom?.solana },
    { wallet: { id: "backpack", label: "Backpack" }, provider: browserWindow.backpack?.solana },
    { wallet: { id: "solflare", label: "Solflare" }, provider: browserWindow.solflare },
  ];

  const seen = new Set<SolanaProvider>();
  return candidates.filter((candidate): candidate is { wallet: AvailableSolanaWallet; provider: SolanaProvider } => {
    if (!candidate.provider || seen.has(candidate.provider)) {
      return false;
    }
    seen.add(candidate.provider);
    return true;
  });
}

function getInjectedSolanaProviderByWallet(walletClientType?: string): SolanaProvider | null {
  const available = listInjectedSolanaProviders();
  if (!walletClientType) {
    return available[0]?.provider ?? getInjectedSolanaProvider();
  }

  return available.find((entry) => entry.wallet.id === walletClientType)?.provider ?? null;
}

function getWalletClientType(provider: SolanaProvider): string {
  if (provider.isPhantom) {
    return "phantom";
  }
  if (provider.isSolflare) {
    return "solflare";
  }
  if (provider.isBackpack) {
    return "backpack";
  }
  return "unknown";
}

function getSignatureBytes(result: SolanaSignResult): Uint8Array {
  return result instanceof Uint8Array ? result : result.signature;
}

function encodeBase64(value: Uint8Array): string {
  let binary = "";
  for (const byte of value) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function isUserCancelledWalletPrompt(error: unknown) {
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
    message.includes("closed") ||
    message.includes("cancelled")
  );
}

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
  const { ready, authenticated, logout, user, getAccessToken } = usePrivy();
  const { login: openLoginModal } = useLogin();
  const { generateSiwsMessage, loginWithSiws } = useLoginWithSiws();
  const walletAddress = useMemo(() => extractWalletAddress(user), [user]);
  const availableWallets = useMemo(
    () => listInjectedSolanaProviders().map((entry) => entry.wallet),
    [ready, authenticated, user],
  );

  const connectWallet = useCallback(
    async (options?: { disableSignup?: boolean; walletClientType?: string }) => {
      const provider = getInjectedSolanaProviderByWallet(options?.walletClientType);
      if (!provider) {
        openLoginModal({
          ...options,
          loginMethods: ["wallet"],
          walletChainType: "solana-only",
        });
        return;
      }

      const connected = await provider.connect();
      const address = connected.publicKey?.toString() ?? provider.publicKey?.toString();
      if (!address) {
        throw new Error("No Solana wallet address returned by the connected wallet.");
      }

      const message = await generateSiwsMessage({ address });
      let signed;
      try {
        signed = await provider.signMessage(new TextEncoder().encode(message), "utf8");
      } catch {
        signed = await provider.signMessage(new TextEncoder().encode(message));
      }
      const signatureBytes = getSignatureBytes(signed);

      try {
        await loginWithSiws({
          message,
          signature: encodeBase58(signatureBytes),
          disableSignup: options?.disableSignup,
          walletClientType: options?.walletClientType ?? getWalletClientType(provider),
          connectorType: "injected",
        });
      } catch (error) {
        if (!(error instanceof Error) || !error.message.includes("Invalid SIWS message and/or nonce")) {
          throw error;
        }

        await loginWithSiws({
          message,
          signature: encodeBase64(signatureBytes),
          disableSignup: options?.disableSignup,
          walletClientType: options?.walletClientType ?? getWalletClientType(provider),
          connectorType: "injected",
        });
      }
    },
    [generateSiwsMessage, loginWithSiws, openLoginModal],
  );

  const login = useCallback(
    (eventOrOptions?: MouseEvent<HTMLElement> | { disableSignup?: boolean; walletClientType?: string }) => {
      if (eventOrOptions && "preventDefault" in eventOrOptions) {
        eventOrOptions.preventDefault();
      }
      const options =
        eventOrOptions && "preventDefault" in eventOrOptions ? undefined : eventOrOptions;

      void connectWallet(options).catch((error) => {
        if (isUserCancelledWalletPrompt(error)) {
          console.warn("Solana wallet login aborted.", error);
          return;
        }
        console.error("Solana wallet login failed.", error);
        if (!options?.walletClientType) {
          openLoginModal({
            ...options,
            loginMethods: ["wallet"],
            walletChainType: "solana-only",
          });
        }
      });
    },
    [connectWallet, openLoginModal],
  );

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
    availableWallets,
    connectWallet,
    getAccessToken,
    getAuthHeaders,
  };
}
