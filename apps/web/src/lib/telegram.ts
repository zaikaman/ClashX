export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type TelegramCommand = {
  command: string;
  description: string;
};

export type TelegramNotificationPrefs = {
  critical_alerts: boolean;
  execution_failures: boolean;
  copy_activity: boolean;
  trade_activity: boolean;
};

export type TelegramConnectionStatus = {
  wallet_address: string;
  bot_username: string | null;
  bot_link: string;
  deeplink_url: string | null;
  link_expires_at: string | null;
  connected: boolean;
  telegram_username: string | null;
  telegram_first_name: string | null;
  chat_label: string | null;
  connected_at: string | null;
  last_interaction_at: string | null;
  notifications_enabled: boolean;
  notification_prefs: TelegramNotificationPrefs;
  token_configured: boolean;
  webhook_url_configured: boolean;
  webhook_secret_configured: boolean;
  webhook_ready: boolean;
  commands: TelegramCommand[];
};

type AuthHeaderFactory = (headersInit?: HeadersInit) => Promise<Headers>;

type TelegramPreferencesPayload = {
  notifications_enabled?: boolean;
  critical_alerts?: boolean;
  execution_failures?: boolean;
  copy_activity?: boolean;
  trade_activity?: boolean;
};

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "Request failed";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail ?? detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function fetchTelegramStatus(
  walletAddress: string,
  getAuthHeaders: AuthHeaderFactory,
  signal?: AbortSignal,
) {
  const response = await fetch(
    `${API_BASE_URL}/api/telegram?wallet_address=${encodeURIComponent(walletAddress)}`,
    {
      headers: await getAuthHeaders(),
      signal,
    },
  );
  return parseResponse<TelegramConnectionStatus>(response);
}

export async function createTelegramLink(walletAddress: string, getAuthHeaders: AuthHeaderFactory) {
  const response = await fetch(`${API_BASE_URL}/api/telegram/link`, {
    method: "POST",
    headers: await getAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ wallet_address: walletAddress }),
  });
  return parseResponse<TelegramConnectionStatus>(response);
}

export async function updateTelegramPreferences(
  walletAddress: string,
  getAuthHeaders: AuthHeaderFactory,
  payload: TelegramPreferencesPayload,
) {
  const response = await fetch(`${API_BASE_URL}/api/telegram/preferences`, {
    method: "PATCH",
    headers: await getAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ wallet_address: walletAddress, ...payload }),
  });
  return parseResponse<TelegramConnectionStatus>(response);
}

export async function sendTelegramTest(walletAddress: string, getAuthHeaders: AuthHeaderFactory) {
  const response = await fetch(`${API_BASE_URL}/api/telegram/test`, {
    method: "POST",
    headers: await getAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ wallet_address: walletAddress }),
  });
  return parseResponse<TelegramConnectionStatus>(response);
}

export async function disconnectTelegram(walletAddress: string, getAuthHeaders: AuthHeaderFactory) {
  const response = await fetch(`${API_BASE_URL}/api/telegram/disconnect`, {
    method: "POST",
    headers: await getAuthHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ wallet_address: walletAddress }),
  });
  return parseResponse<TelegramConnectionStatus>(response);
}
