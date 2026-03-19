const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type PacificaReadinessStep = {
  id: "funding" | "app_access" | "agent_authorization";
  title: string;
  verified: boolean;
  detail: string;
};

export type PacificaReadinessPayload = {
  wallet_address: string;
  ready: boolean;
  blockers: string[];
  metrics: {
    sol_balance: number;
    min_sol_balance: number;
    equity_usd: number | null;
    min_equity_usd: number;
    agent_wallet_address: string | null;
    authorization_status: string;
    builder_code: string | null;
  };
  steps: PacificaReadinessStep[];
};

type ReadinessErrorPayload = {
  detail?: string;
};

type AuthHeaderFactory = (headersInit?: HeadersInit) => Promise<Headers>;

export class PacificaReadinessError extends Error {
  readonly readiness: PacificaReadinessPayload;

  constructor(readiness: PacificaReadinessPayload) {
    super(formatPacificaReadinessBlockers(readiness.blockers));
    this.name = "PacificaReadinessError";
    this.readiness = readiness;
  }
}

export function formatPacificaReadinessBlockers(blockers: string[]) {
  const uniqueBlockers = Array.from(new Set(blockers.map((blocker) => blocker.trim()).filter(Boolean)));
  return uniqueBlockers.length > 0 ? uniqueBlockers.join(" ") : "Pacifica setup is incomplete.";
}

export async function fetchPacificaReadiness(walletAddress: string, getAuthHeaders: AuthHeaderFactory) {
  const resolvedWalletAddress = walletAddress.trim();
  if (!resolvedWalletAddress) {
    throw new Error("Connect the wallet you want ClashX to trade with.");
  }

  const response = await fetch(`${API_BASE_URL}/api/pacifica/readiness?wallet_address=${encodeURIComponent(resolvedWalletAddress)}`, {
    cache: "no-store",
    headers: await getAuthHeaders(),
  });
  const payload = (await response.json()) as PacificaReadinessPayload | ReadinessErrorPayload;
  if (!response.ok) {
    throw new Error("detail" in payload ? payload.detail ?? "Pacifica readiness check failed." : "Pacifica readiness check failed.");
  }
  return payload as PacificaReadinessPayload;
}

export async function assertPacificaDeployReadiness(walletAddress: string, getAuthHeaders: AuthHeaderFactory) {
  const readiness = await fetchPacificaReadiness(walletAddress, getAuthHeaders);
  if (!readiness.ready) {
    throw new PacificaReadinessError(readiness);
  }
  return readiness;
}
