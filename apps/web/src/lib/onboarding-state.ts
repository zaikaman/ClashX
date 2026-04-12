"use client";

const ONBOARDING_STATE_KEY = "clashx:onboarding-state";
const ONBOARDING_ROUTE = "/onboarding" as const;
const DASHBOARD_ROUTE = "/dashboard" as const;

type StoredOnboardingState = {
  version: 1;
  completed: boolean;
  walletAddress: string | null;
  completedAt: string;
};

function isBrowser() {
  return typeof window !== "undefined";
}

function normalizeWalletAddress(walletAddress?: string | null) {
  const resolvedWalletAddress = walletAddress?.trim();
  return resolvedWalletAddress ? resolvedWalletAddress.toLowerCase() : null;
}

export function readStoredOnboardingState(): StoredOnboardingState | null {
  if (!isBrowser()) {
    return null;
  }

  const rawValue = window.localStorage.getItem(ONBOARDING_STATE_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsedValue = JSON.parse(rawValue) as Partial<StoredOnboardingState>;
    if (parsedValue.completed !== true || typeof parsedValue.completedAt !== "string") {
      return null;
    }

    return {
      version: 1,
      completed: true,
      walletAddress: normalizeWalletAddress(parsedValue.walletAddress) ?? null,
      completedAt: parsedValue.completedAt,
    };
  } catch {
    return null;
  }
}

export function hasCompletedOnboardingForWallet(walletAddress?: string | null) {
  const storedState = readStoredOnboardingState();
  if (!storedState?.completed) {
    return false;
  }

  const normalizedWalletAddress = normalizeWalletAddress(walletAddress);
  if (!normalizedWalletAddress || !storedState.walletAddress) {
    return true;
  }

  return storedState.walletAddress === normalizedWalletAddress;
}

export function writeStoredOnboardingState(walletAddress?: string | null) {
  if (!isBrowser()) {
    return;
  }

  const nextState: StoredOnboardingState = {
    version: 1,
    completed: true,
    walletAddress: normalizeWalletAddress(walletAddress),
    completedAt: new Date().toISOString(),
  };

  window.localStorage.setItem(ONBOARDING_STATE_KEY, JSON.stringify(nextState));
}

export function clearStoredOnboardingState() {
  if (!isBrowser()) {
    return;
  }

  window.localStorage.removeItem(ONBOARDING_STATE_KEY);
}

export function getPreferredLaunchPath() {
  return readStoredOnboardingState()?.completed ? DASHBOARD_ROUTE : ONBOARDING_ROUTE;
}
