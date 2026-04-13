"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Bot,
  CircleX,
  History,
  LoaderCircle,
  Plus,
  SendHorizontal,
  Sparkles,
  X,
} from "lucide-react";

import { useClashxAuth } from "@/lib/clashx-auth";

type ChatRole = "user" | "assistant";

type CopilotToolTrace = {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  resultPreview: string;
};

type CopilotMessage = {
  id: string;
  role: ChatRole;
  content: string;
  toolCalls?: CopilotToolTrace[];
  followUps?: string[];
  provider?: string | null;
  createdAt?: string;
};

type CopilotConversationSummary = {
  id: string;
  title: string;
  walletAddress: string;
  messageCount: number;
  lastMessagePreview: string;
  createdAt: string;
  updatedAt: string;
  latestMessageAt: string;
};

type CopilotConversationDetail = CopilotConversationSummary & {
  summaryMessageCount: number;
  summaryText: string;
  messages: CopilotMessage[];
};

type CopilotChatResponse = {
  conversationId: string;
  conversation: CopilotConversationSummary;
  assistantMessage: CopilotMessage;
  reply: string;
  followUps?: string[];
  toolCalls?: CopilotToolTrace[];
  provider?: string;
  usedWalletAddress?: string | null;
  detail?: string;
};

type CopilotChatJobCreateResponse = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  conversationId?: string | null;
  detail?: string;
};

type CopilotChatJobStatusResponse = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  conversationId?: string | null;
  result?: CopilotChatResponse | null;
  errorDetail?: string | null;
  detail?: string;
};

type FetchState = "idle" | "loading";
type ComposerState = "idle" | "creating" | "sending";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const QUICK_PROMPTS = [
  {
    title: "What are my active bots doing right now?",
    description: "The safest first prompt for a live status snapshot of running strategies and recent activity.",
  },
  {
    title: "Show my open order exposure",
    description: "Review active orders, side concentration, and where risk is currently sitting.",
  },
  {
    title: "Am I ready to trade on Pacifica?",
    description: "Check account readiness, balances, and anything blocking a new trade.",
  },
  {
    title: "Give me a quick account health check and call out anything that needs attention.",
    description: "A broader check across balance state, bot status, and anything obviously urgent.",
  },
];
const LOADING_MESSAGES = ["Thinking...", "Reviewing your account context...", "Checking recent activity...", "Putting the answer together..."];
const JOB_POLL_VISIBLE_MS = 1200;
const JOB_POLL_VISIBLE_FAST_MS = 450;
const JOB_POLL_HIDDEN_MS = 2500;

function formatWalletAddress(walletAddress: string | null | undefined) {
  if (!walletAddress) return "";
  return `${walletAddress.slice(0, 6)}...${walletAddress.slice(-4)}`;
}

function formatConversationTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function upsertConversation(
  conversations: CopilotConversationSummary[],
  nextConversation: CopilotConversationSummary,
) {
  return [nextConversation, ...conversations.filter((conversation) => conversation.id !== nextConversation.id)];
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

async function parseJson<T>(response: Response): Promise<T | { detail?: string }> {
  try {
    return (await response.json()) as T | { detail?: string };
  } catch {
    return {};
  }
}

function renderFormattedContent(content: string) {
  return content.split("\n").map((line, lineIndex) => {
    const isList = line.trim().startsWith("* ") || line.trim().startsWith("- ");
    const lineContent = isList ? line.replace(/^(\*|-)\s/, "") : line;
    const parts = lineContent.split(/(\*\*.*?\*\*)/g);
    return (
      <div key={`${lineIndex}-${lineContent.slice(0, 12)}`} className={`mt-2 first:mt-0 ${isList ? "flex gap-2" : ""}`}>
        {isList ? <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[#dce85d]" /> : null}
        <span className="min-w-0">
          {parts.map((part, index) =>
            part.startsWith("**") && part.endsWith("**") ? (
              <strong key={index} className="font-semibold text-[#eef5a8]">
                {part.slice(2, -2)}
              </strong>
            ) : (
              <span key={index}>{part}</span>
            ),
          )}
        </span>
      </div>
    );
  });
}

export function CopilotPage() {
  const { ready, authenticated, login, walletAddress, getAuthHeaders } = useClashxAuth();
  const [conversations, setConversations] = useState<CopilotConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [activeConversation, setActiveConversation] = useState<CopilotConversationSummary | null>(null);
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [input, setInput] = useState("");
  const [composerState, setComposerState] = useState<ComposerState>("idle");
  const [historyState, setHistoryState] = useState<FetchState>("idle");
  const [conversationState, setConversationState] = useState<FetchState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [pendingChatJob, setPendingChatJob] = useState<{ jobId: string; optimisticMessageId: string } | null>(null);
  const [resolvedWallet, setResolvedWallet] = useState<string | null>(walletAddress ?? null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loadingMessageIndex, setLoadingMessageIndex] = useState(0);
  const messageEndRef = useRef<HTMLDivElement | null>(null);
  const historyRequestRef = useRef<AbortController | null>(null);
  const conversationRequestRef = useRef<AbortController | null>(null);
  const bootstrapScopeRef = useRef<string | null>(null);

  const isCreating = composerState === "creating";
  const isSending = composerState === "sending";
  const isBusy = isCreating || isSending;
  const isHistoryLoading = historyState === "loading";
  const isConversationLoading = conversationState === "loading";

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, composerState]);

  useEffect(() => {
    if (walletAddress) {
      setResolvedWallet(walletAddress);
    }
  }, [walletAddress]);

  useEffect(() => {
    return () => {
      historyRequestRef.current?.abort();
      conversationRequestRef.current?.abort();
    };
  }, []);

  function closeHistoryOnMobile() {
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      setHistoryOpen(false);
    }
  }

  const loadConversations = useCallback(async () => {
    if (!authenticated) {
      return;
    }

    historyRequestRef.current?.abort();
    const controller = new AbortController();
    historyRequestRef.current = controller;
    setHistoryState("loading");
    setError(null);

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/api/copilot/conversations`, {
        headers,
        signal: controller.signal,
      });
      const payload = (await parseJson<CopilotConversationSummary[]>(response)) as
        | CopilotConversationSummary[]
        | { detail?: string };
      if (!response.ok || !Array.isArray(payload)) {
        throw new Error((payload as { detail?: string }).detail ?? "Failed to load conversations");
      }
      if (controller.signal.aborted) {
        return;
      }

      setConversations(payload);
      setActiveConversation((current) => {
        if (!current) {
          return null;
        }
        const matchingConversation = payload.find((conversation) => conversation.id === current.id);
        return matchingConversation ? { ...current, ...matchingConversation } : null;
      });

      if (activeConversationId && !payload.some((conversation) => conversation.id === activeConversationId)) {
        setActiveConversationId(null);
        setActiveConversation(null);
        setMessages([]);
      }
    } catch (requestError) {
      if (!isAbortError(requestError)) {
        setError(requestError instanceof Error ? requestError.message : "Failed to load Copilot");
      }
    } finally {
      if (historyRequestRef.current === controller) {
        historyRequestRef.current = null;
        setHistoryState("idle");
      }
    }
  }, [activeConversationId, authenticated, getAuthHeaders]);

  useEffect(() => {
    if (!authenticated) {
      bootstrapScopeRef.current = null;
      historyRequestRef.current?.abort();
      conversationRequestRef.current?.abort();
      setConversations([]);
      setActiveConversationId(null);
      setActiveConversation(null);
      setMessages([]);
      setHistoryState("idle");
      setConversationState("idle");
      return;
    }

    const scopeKey = walletAddress ?? "authenticated";
    if (bootstrapScopeRef.current === scopeKey) {
      return;
    }
    bootstrapScopeRef.current = scopeKey;

    let timeoutId: number | null = null;
    let idleId: number | null = null;
    const browserWindow = typeof window !== "undefined"
      ? (window as Window & {
          requestIdleCallback?: (callback: IdleRequestCallback) => number;
          cancelIdleCallback?: (handle: number) => void;
        })
      : null;

    const startBootstrap = () => {
      void loadConversations();
    };

    if (browserWindow?.requestIdleCallback) {
      idleId = browserWindow.requestIdleCallback(() => startBootstrap());
    } else if (typeof window !== "undefined") {
      timeoutId = window.setTimeout(startBootstrap, 0);
    } else {
      startBootstrap();
    }

    return () => {
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      if (idleId !== null && browserWindow?.cancelIdleCallback) {
        browserWindow.cancelIdleCallback(idleId);
      }
    };
  }, [authenticated, getAuthHeaders, loadConversations, walletAddress]);

  useEffect(() => {
    if (!authenticated || !pendingChatJob) {
      return;
    }

    let cancelled = false;
    let timeoutId: number | null = null;
    let pollCount = 0;

    const scheduleNextPoll = () => {
      if (cancelled) {
        return;
      }
      const hidden = typeof document !== "undefined" && document.visibilityState === "hidden";
      const delay = hidden ? JOB_POLL_HIDDEN_MS : pollCount < 3 ? JOB_POLL_VISIBLE_FAST_MS : JOB_POLL_VISIBLE_MS;
      timeoutId = window.setTimeout(() => {
        void pollJob();
      }, delay);
    };

    const pollJob = async () => {
      pollCount += 1;
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${API_BASE_URL}/api/copilot/chat/jobs/${pendingChatJob.jobId}`, { headers });
        const payload = (await parseJson<CopilotChatJobStatusResponse>(response)) as CopilotChatJobStatusResponse;
        if (!response.ok) {
          throw new Error(payload.detail ?? "Failed to poll Copilot job");
        }
        if (cancelled) {
          return;
        }
        if (payload.status === "completed" && payload.result) {
          const result = payload.result;
          setResolvedWallet(result.usedWalletAddress ?? result.conversation.walletAddress ?? walletAddress ?? null);
          setConversations((current) => upsertConversation(current, result.conversation));
          setActiveConversationId(result.conversationId);
          setActiveConversation(result.conversation);
          setMessages((current) => {
            if (current.some((message) => message.id === result.assistantMessage.id)) {
              return current;
            }
            return [...current, result.assistantMessage];
          });
          setPendingChatJob(null);
          setComposerState("idle");
          closeHistoryOnMobile();
          return;
        }
        if (payload.status === "failed") {
          setMessages((current) => current.filter((message) => message.id !== pendingChatJob.optimisticMessageId));
          setPendingChatJob(null);
          setComposerState("idle");
          setError(payload.errorDetail ?? "Copilot request failed");
          return;
        }
        scheduleNextPoll();
      } catch (pollError) {
        if (cancelled) {
          return;
        }
        setMessages((current) => current.filter((message) => message.id !== pendingChatJob.optimisticMessageId));
        setPendingChatJob(null);
        setComposerState("idle");
        setError(pollError instanceof Error ? pollError.message : "Copilot request failed");
      }
    };

    void pollJob();

    return () => {
      cancelled = true;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [authenticated, getAuthHeaders, pendingChatJob, walletAddress]);

  useEffect(() => {
    if (!isSending) {
      setLoadingMessageIndex(0);
      return;
    }

    const intervalId = window.setInterval(() => {
      setLoadingMessageIndex((current) => (current + 1) % LOADING_MESSAGES.length);
    }, 1600);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [isSending]);

  async function openConversation(conversationId: string) {
    if (!authenticated || isSending) {
      return;
    }
    const summary = conversations.find((conversation) => conversation.id === conversationId) ?? null;
    if (conversationId === activeConversationId && messages.length > 0) {
      closeHistoryOnMobile();
      return;
    }

    conversationRequestRef.current?.abort();
    const controller = new AbortController();
    conversationRequestRef.current = controller;
    setConversationState("loading");
    setError(null);
    setActiveConversationId(conversationId);
    setActiveConversation(summary);
    setMessages([]);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/api/copilot/conversations/${conversationId}`, {
        headers,
        signal: controller.signal,
      });
      const payload = (await parseJson<CopilotConversationDetail>(response)) as
        | CopilotConversationDetail
        | { detail?: string };
      if (!response.ok || !("messages" in payload)) {
        throw new Error((payload as { detail?: string }).detail ?? "Failed to load conversation");
      }
      if (controller.signal.aborted) {
        return;
      }
      setActiveConversationId(payload.id);
      setActiveConversation(payload);
      setMessages(payload.messages);
      setConversations((current) => upsertConversation(current, payload));
      closeHistoryOnMobile();
    } catch (requestError) {
      if (!isAbortError(requestError)) {
        setError(requestError instanceof Error ? requestError.message : "Failed to load conversation");
      }
    } finally {
      if (conversationRequestRef.current === controller) {
        conversationRequestRef.current = null;
        setConversationState("idle");
      }
    }
  }

  async function createConversation() {
    if (!authenticated || isBusy) {
      return;
    }
    conversationRequestRef.current?.abort();
    conversationRequestRef.current = null;
    setConversationState("idle");
    setComposerState("creating");
    setError(null);
    try {
      const headers = await getAuthHeaders({ "Content-Type": "application/json" });
      const response = await fetch(`${API_BASE_URL}/api/copilot/conversations`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          walletAddress: walletAddress ?? null,
        }),
      });
      const payload = (await parseJson<CopilotConversationSummary>(response)) as
        | CopilotConversationSummary
        | { detail?: string };
      if (!response.ok || !("id" in payload)) {
        throw new Error((payload as { detail?: string }).detail ?? "Failed to create conversation");
      }
      setConversations((current) => upsertConversation(current, payload));
      setActiveConversationId(payload.id);
      setActiveConversation(payload);
      setMessages([]);
      setInput("");
      closeHistoryOnMobile();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to create conversation");
    } finally {
      setComposerState("idle");
    }
  }

  async function deleteConversation(conversationId: string) {
    if (!authenticated || isBusy) {
      return;
    }
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/api/copilot/conversations/${conversationId}`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) {
        const payload = (await parseJson<{ detail?: string }>(response)) as { detail?: string };
        throw new Error(payload.detail ?? "Failed to delete conversation");
      }

      setConversations((current) => current.filter((conversation) => conversation.id !== conversationId));
      if (activeConversationId === conversationId) {
        conversationRequestRef.current?.abort();
        setActiveConversationId(null);
        setActiveConversation(null);
        setMessages([]);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to delete conversation");
    }
  }

  async function sendMessage(seed?: string) {
    const content = (seed ?? input).trim();
    if (!content || isSending || isConversationLoading) {
      return;
    }
    if (!authenticated) {
      login();
      return;
    }

    const optimisticMessage: CopilotMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };

    setMessages((current) => [...current, optimisticMessage]);
    setInput("");
    setComposerState("sending");
    setError(null);

    try {
      const headers = await getAuthHeaders({ "Content-Type": "application/json" });
      const response = await fetch(`${API_BASE_URL}/api/copilot/chat/jobs`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          conversationId: activeConversationId,
          content,
          walletAddress: walletAddress ?? activeConversation?.walletAddress ?? null,
        }),
      });
      const payload = (await parseJson<CopilotChatJobCreateResponse>(response)) as CopilotChatJobCreateResponse;
      if (!response.ok || !payload.id) {
        throw new Error(payload.detail ?? "Copilot request failed");
      }
      if (payload.conversationId) {
        setActiveConversationId(payload.conversationId);
      }
      setPendingChatJob({ jobId: payload.id, optimisticMessageId: optimisticMessage.id });
      void loadConversations();
    } catch (requestError) {
      setMessages((current) => current.filter((message) => message.id !== optimisticMessage.id));
      setComposerState("idle");
      setError(requestError instanceof Error ? requestError.message : "Copilot request failed");
    }
  }

  const showIntro = messages.length === 0;
  const activeTitle = activeConversation?.title ?? "New conversation";

  const historyPanel = (
    <aside className="flex h-full w-full max-w-[320px] flex-col overflow-hidden rounded-[2rem] border border-white/[0.06] bg-[linear-gradient(180deg,rgba(22,24,28,0.96),rgba(9,10,11,0.98))] shadow-[0_28px_90px_rgba(0,0,0,0.38)]">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-neutral-500">History</p>
          <h2 className="mt-1 text-sm font-semibold text-neutral-100">Past conversations</h2>
        </div>
        <button
          type="button"
          onClick={() => setHistoryOpen(false)}
          className="rounded-full border border-white/[0.08] p-2 text-neutral-400 transition hover:border-white/[0.18] hover:text-neutral-100 lg:hidden"
          aria-label="Close history"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="border-b border-white/[0.06] px-5 py-4">
        <button
          type="button"
          onClick={() => void createConversation()}
          disabled={!authenticated || isBusy}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-[#dce85d] px-4 py-3 text-sm font-semibold text-black transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
          New conversation
        </button>
      </div>

      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3 text-[10px] uppercase tracking-[0.22em] text-neutral-500">
        <span>{isHistoryLoading ? "Syncing history" : "History ready"}</span>
        {authenticated ? (
          <button
            type="button"
            onClick={() => void loadConversations()}
            disabled={isHistoryLoading}
            className="text-neutral-400 transition hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Refresh
          </button>
        ) : null}
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {authenticated ? (
          conversations.length > 0 ? (
            <div className="space-y-2">
              {conversations.map((conversation) => {
                const isActive = conversation.id === activeConversationId;
                return (
                  <div key={conversation.id} className="relative">
                    <button
                      type="button"
                      onClick={() => void openConversation(conversation.id)}
                      className={`w-full rounded-[1.35rem] border px-4 py-3 pr-12 text-left transition ${
                        isActive
                          ? "border-[#dce85d]/35 bg-[#dce85d]/10"
                          : "border-white/[0.04] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.05]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <p className={`text-sm font-medium ${isActive ? "text-[#eef5a8]" : "text-neutral-100"}`}>
                          {conversation.title}
                        </p>
                        <span className="shrink-0 text-[10px] uppercase tracking-[0.2em] text-neutral-500">
                          {formatConversationTime(conversation.latestMessageAt)}
                        </span>
                      </div>
                      <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-neutral-400">
                        {conversation.lastMessagePreview || "No messages yet."}
                      </p>
                      <p className="mt-3 text-[10px] uppercase tracking-[0.22em] text-neutral-600">
                        {conversation.messageCount} messages
                      </p>
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void deleteConversation(conversation.id);
                      }}
                      disabled={isBusy}
                      className="absolute right-3 top-3 rounded-full border border-white/[0.08] bg-black/25 p-1.5 text-neutral-500 transition hover:border-rose-400/30 hover:text-rose-300 disabled:cursor-not-allowed disabled:opacity-40"
                      aria-label={`Delete ${conversation.title}`}
                      title="Delete conversation"
                    >
                      <CircleX className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          ) : isHistoryLoading ? (
            <div className="rounded-[1.5rem] border border-dashed border-white/[0.08] bg-white/[0.02] px-4 py-6 text-sm text-neutral-400">
              Loading saved conversations...
            </div>
          ) : (
            <div className="rounded-[1.5rem] border border-dashed border-white/[0.08] bg-white/[0.02] px-4 py-6 text-sm text-neutral-400">
              Your conversations will show up here after you send your first message.
            </div>
          )
        ) : (
          <div className="rounded-[1.5rem] border border-dashed border-white/[0.08] bg-white/[0.02] px-4 py-6 text-sm text-neutral-400">
            Connect your wallet to see your saved conversations.
          </div>
        )}
      </div>
    </aside>
  );

  return (
    <main className="min-h-[calc(100vh-64px)] bg-[#090a0b] text-neutral-50 selection:bg-[#dce85d]/30">
      <div className="mx-auto flex h-[calc(100vh-64px)] max-w-7xl gap-4 px-4 py-4 md:px-6">
        <div className="hidden h-full lg:block">{historyOpen ? historyPanel : null}</div>

        {historyOpen ? (
          <div
            className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
            onClick={() => setHistoryOpen(false)}
          >
            <div className="h-full max-w-[340px] p-3" onClick={(event) => event.stopPropagation()}>
              {historyPanel}
            </div>
          </div>
        ) : null}

        <section className="relative flex min-w-0 flex-1 flex-col overflow-hidden rounded-[2rem] border border-white/[0.06] bg-[radial-gradient(circle_at_top_left,rgba(220,232,93,0.12),transparent_24%),linear-gradient(180deg,rgba(16,18,21,0.98),rgba(8,9,11,1))] shadow-[0_35px_110px_rgba(0,0,0,0.42)]">
          <header className="flex items-center justify-between gap-4 border-b border-white/[0.06] px-5 py-4 md:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#dce85d] text-black shadow-[0_10px_24px_rgba(220,232,93,0.25)]">
                <Sparkles className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-[0.3em] text-neutral-500">ClashX Copilot</p>
                <h1 className="truncate text-base font-semibold text-neutral-100">{activeTitle}</h1>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setHistoryOpen((current) => !current)}
                className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs font-medium text-neutral-300 transition hover:border-white/[0.18] hover:text-neutral-50"
              >
                <span className="flex items-center gap-2">
                  <History className="h-3.5 w-3.5" />
                  {isHistoryLoading ? "History..." : "History"}
                </span>
              </button>
              <button
                type="button"
                onClick={() => void createConversation()}
                disabled={!authenticated || isBusy}
                className="rounded-full bg-[#dce85d] px-3 py-2 text-xs font-semibold text-black transition hover:scale-[1.02] disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="flex items-center gap-2">
                  <Plus className="h-3.5 w-3.5" />
                  New
                </span>
              </button>
              {ready ? (
                authenticated ? (
                  <div className="hidden items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-neutral-400 md:flex">
                    <span className="h-2 w-2 rounded-full bg-[#dce85d]" />
                    <span className="font-mono">{formatWalletAddress(resolvedWallet)}</span>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={login}
                    className="rounded-full border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs font-medium text-neutral-300 transition hover:border-white/[0.18] hover:text-neutral-50"
                  >
                    Connect wallet
                  </button>
                )
              ) : (
                <div className="h-9 w-24 animate-pulse rounded-full bg-white/[0.04]" />
              )}
            </div>
          </header>

          <div className="relative flex-1 overflow-y-auto px-5 py-5 md:px-6">
            {isConversationLoading ? (
              <div className="absolute inset-x-5 top-5 z-10 rounded-2xl border border-white/[0.06] bg-black/40 px-4 py-3 text-xs uppercase tracking-[0.22em] text-neutral-400 backdrop-blur md:inset-x-6">
                Loading conversation...
              </div>
            ) : null}

            {!authenticated ? (
              <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
                <div className="space-y-3">
                  <p className="text-[11px] uppercase tracking-[0.3em] text-neutral-500">Private account context</p>
                  <h2 className="text-3xl font-semibold tracking-tight text-neutral-100 md:text-4xl">
                    Pick up where you left off
                  </h2>
                  <p className="mx-auto max-w-xl text-sm leading-relaxed text-neutral-400">
                    Connect your wallet to chat with Copilot using your ClashX account data, keep your past
                    conversations, and come back to them anytime.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={login}
                  className="rounded-full bg-[#dce85d] px-5 py-3 text-sm font-semibold text-black transition hover:scale-[1.02]"
                >
                  Connect wallet
                </button>
              </div>
            ) : showIntro ? (
              <div className="flex h-full flex-col items-center justify-center gap-10 text-center">
                <div className="max-w-2xl space-y-4">
                  <p className="text-[11px] uppercase tracking-[0.34em] text-neutral-500">Conversation history</p>
                  <h2 className="text-3xl font-semibold tracking-tight text-neutral-100 md:text-5xl">
                    Start a new conversation without waiting for history
                  </h2>
                  <p className="text-sm leading-relaxed text-neutral-400">
                    Ask about your bots, trading account, or runtime activity right away. Saved conversations keep
                    syncing in the background and can be reopened whenever you need them.
                  </p>
                </div>

                <div className="grid w-full max-w-3xl gap-3 md:grid-cols-2">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button
                      key={prompt.title}
                      type="button"
                      onClick={() => void sendMessage(prompt.title)}
                      disabled={isBusy || isConversationLoading}
                      className="rounded-[1.6rem] border border-white/[0.05] bg-white/[0.025] px-5 py-5 text-left transition hover:border-[#dce85d]/30 hover:bg-[#dce85d]/[0.04] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <p className="text-sm font-medium text-neutral-100">{prompt.title}</p>
                      <p className="mt-2 text-xs leading-relaxed text-neutral-400">
                        {prompt.description}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-8 pb-8">
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={`flex items-start gap-4 ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {message.role === "assistant" ? (
                      <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.03]">
                        <Bot className="h-4 w-4 text-neutral-300" />
                      </div>
                    ) : null}

                    <div className={`max-w-[90%] space-y-3 ${message.role === "user" ? "items-end" : "items-start"}`}>
                      <div
                        className={
                          message.role === "user"
                            ? "rounded-[1.6rem] rounded-tr-sm bg-[#dce85d] px-5 py-3.5 text-sm leading-relaxed text-black shadow-[0_12px_30px_rgba(220,232,93,0.16)]"
                            : "rounded-[1.6rem] rounded-tl-sm border border-white/[0.05] bg-white/[0.03] px-5 py-4 text-sm leading-relaxed text-neutral-200"
                        }
                      >
                        {renderFormattedContent(message.content)}
                      </div>

                      {message.toolCalls && message.toolCalls.length > 0 ? (
                        <div className="space-y-2">
                          {message.toolCalls.map((toolCall, index) => (
                            <div
                              key={`${message.id}-tool-${index}`}
                              className="rounded-[1.2rem] border border-white/[0.05] bg-black/20 px-4 py-3"
                            >
                              <div className="flex items-center gap-2">
                                <span className="text-[11px] uppercase tracking-[0.22em] text-neutral-500">
                                  {toolCall.tool}
                                </span>
                                {toolCall.ok ? null : (
                                  <span className="rounded-full bg-rose-500/12 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-rose-300">
                                    Failed
                                  </span>
                                )}
                              </div>
                              <p className="mt-2 break-all text-xs leading-relaxed text-neutral-400">
                                {toolCall.resultPreview}
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : null}

                      {message.followUps && message.followUps.length > 0 ? (
                        <div className="flex flex-wrap gap-2">
                          {message.followUps.map((followUp) => (
                            <button
                              key={`${message.id}-${followUp}`}
                              type="button"
                              onClick={() => void sendMessage(followUp)}
                              disabled={isSending || isConversationLoading}
                              className="rounded-full border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-xs font-medium text-neutral-300 transition hover:border-[#dce85d]/30 hover:text-neutral-50 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {followUp}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </article>
                ))}

                {isSending ? (
                  <article className="flex items-start gap-4">
                    <div className="mt-1 flex h-9 w-9 items-center justify-center rounded-full border border-white/[0.08] bg-white/[0.03]">
                      <LoaderCircle className="h-4 w-4 animate-spin text-neutral-300" />
                    </div>
                    <div className="rounded-[1.6rem] rounded-tl-sm border border-white/[0.05] bg-white/[0.03] px-5 py-4">
                      <div className="flex gap-1">
                        <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:-0.3s]" />
                        <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500 [animation-delay:-0.15s]" />
                        <span className="h-2 w-2 animate-bounce rounded-full bg-neutral-500" />
                      </div>
                      <p className="mt-3 text-xs tracking-[0.04em] text-neutral-400">
                        {LOADING_MESSAGES[loadingMessageIndex]}
                      </p>
                    </div>
                  </article>
                ) : null}

                <div ref={messageEndRef} />
              </div>
            )}
          </div>

          <div className="border-t border-white/[0.06] px-5 py-4 md:px-6">
            {error ? (
              <div className="mb-3 flex items-center gap-2 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-xs text-rose-100">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}

            <div className="rounded-[1.75rem] border border-white/[0.08] bg-white/[0.03] p-2 transition focus-within:border-[#dce85d]/35">
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void sendMessage();
                    }
                  }}
                  disabled={!authenticated || isConversationLoading}
                  placeholder={authenticated ? "Ask about your account, bots, or recent activity..." : "Connect your wallet to start chatting..."}
                  rows={1}
                  className="max-h-[220px] min-h-[52px] w-full resize-none bg-transparent px-4 py-3 text-sm text-neutral-100 outline-none placeholder:text-neutral-500 disabled:cursor-not-allowed"
                />
                <button
                  type="button"
                  onClick={() => void sendMessage()}
                  disabled={!authenticated || isSending || isConversationLoading || input.trim().length === 0}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#dce85d] text-black transition hover:scale-[1.03] disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Send message"
                >
                  <SendHorizontal className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.22em] text-neutral-600">
              <span>Uses your authorized ClashX data</span>
              <span>
                {isHistoryLoading
                  ? "Syncing saved conversations"
                  : activeConversation
                    ? `${activeConversation.messageCount} messages saved`
                    : "No conversation selected"}
              </span>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
