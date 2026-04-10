"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const QUICK_PROMPTS = [
  "Summarize my active bots",
  "Check my Pacifica readiness",
  "Show open orders exposure",
  "Inspect recent runtime events",
];

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
  const [status, setStatus] = useState<"idle" | "loading" | "creating" | "sending">("idle");
  const [error, setError] = useState<string | null>(null);
  const [resolvedWallet, setResolvedWallet] = useState<string | null>(walletAddress ?? null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const messageEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status]);

  useEffect(() => {
    if (walletAddress) {
      setResolvedWallet(walletAddress);
    }
  }, [walletAddress]);

  function closeHistoryOnMobile() {
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      setHistoryOpen(false);
    }
  }

  useEffect(() => {
    if (!authenticated) {
      setConversations([]);
      setActiveConversationId(null);
      setActiveConversation(null);
      setMessages([]);
      return;
    }

    let ignore = false;
    async function loadConversations() {
      setStatus("loading");
      setError(null);
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${API_BASE_URL}/api/copilot/conversations`, { headers });
        const payload = (await parseJson<CopilotConversationSummary[]>(response)) as
          | CopilotConversationSummary[]
          | { detail?: string };
        if (!response.ok || !Array.isArray(payload)) {
          throw new Error((payload as { detail?: string }).detail ?? "Failed to load conversations");
        }
        if (ignore) {
          return;
        }
        setConversations(payload);
        if (payload.length === 0) {
          setActiveConversationId(null);
          setActiveConversation(null);
          setMessages([]);
          setStatus("idle");
          return;
        }

        const nextActiveId =
          payload.find((conversation) => conversation.id === activeConversationId)?.id ?? payload[0].id;
        const detailResponse = await fetch(`${API_BASE_URL}/api/copilot/conversations/${nextActiveId}`, { headers });
        const detailPayload = (await parseJson<CopilotConversationDetail>(detailResponse)) as
          | CopilotConversationDetail
          | { detail?: string };
        if (!detailResponse.ok || !("messages" in detailPayload)) {
          throw new Error((detailPayload as { detail?: string }).detail ?? "Failed to load conversation");
        }
        if (ignore) {
          return;
        }
        setActiveConversationId(detailPayload.id);
        setActiveConversation(detailPayload);
        setMessages(detailPayload.messages);
      } catch (requestError) {
        if (!ignore) {
          setError(requestError instanceof Error ? requestError.message : "Failed to load Copilot");
        }
      } finally {
        if (!ignore) {
          setStatus("idle");
        }
      }
    }

    void loadConversations();
    return () => {
      ignore = true;
    };
  }, [activeConversationId, authenticated, getAuthHeaders]);

  async function openConversation(conversationId: string) {
    if (!authenticated || status === "sending") {
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${API_BASE_URL}/api/copilot/conversations/${conversationId}`, { headers });
      const payload = (await parseJson<CopilotConversationDetail>(response)) as
        | CopilotConversationDetail
        | { detail?: string };
      if (!response.ok || !("messages" in payload)) {
        throw new Error((payload as { detail?: string }).detail ?? "Failed to load conversation");
      }
      setActiveConversationId(payload.id);
      setActiveConversation(payload);
      setMessages(payload.messages);
      closeHistoryOnMobile();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load conversation");
    } finally {
      setStatus("idle");
    }
  }

  async function createConversation() {
    if (!authenticated || status === "creating" || status === "sending") {
      return;
    }
    setStatus("creating");
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
      setStatus("idle");
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

      const remaining = conversations.filter((conversation) => conversation.id !== conversationId);
      setConversations(remaining);
      if (activeConversationId === conversationId) {
        const nextConversation = remaining[0] ?? null;
        setActiveConversationId(nextConversation?.id ?? null);
        setActiveConversation(nextConversation);
        setMessages([]);
        if (nextConversation) {
          await openConversation(nextConversation.id);
        }
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to delete conversation");
    }
  }

  async function sendMessage(seed?: string) {
    const content = (seed ?? input).trim();
    if (!content || status === "sending") {
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
    setStatus("sending");
    setError(null);

    try {
      const headers = await getAuthHeaders({ "Content-Type": "application/json" });
      const response = await fetch(`${API_BASE_URL}/api/copilot/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          conversationId: activeConversationId,
          content,
          walletAddress: walletAddress ?? activeConversation?.walletAddress ?? null,
        }),
      });
      const payload = (await parseJson<CopilotChatResponse>(response)) as CopilotChatResponse;
      if (!response.ok || !payload.reply || !payload.conversation) {
        throw new Error(payload.detail ?? "Copilot request failed");
      }

      setResolvedWallet(payload.usedWalletAddress ?? payload.conversation.walletAddress ?? walletAddress ?? null);
      setConversations((current) => upsertConversation(current, payload.conversation));
      setActiveConversationId(payload.conversationId);
      setActiveConversation(payload.conversation);
      setMessages((current) => {
        const withoutOptimistic = current.filter((message) => message.id !== optimisticMessage.id);
        return [...withoutOptimistic, optimisticMessage, payload.assistantMessage];
      });
      closeHistoryOnMobile();
    } catch (requestError) {
      setMessages((current) => current.filter((message) => message.id !== optimisticMessage.id));
      setError(requestError instanceof Error ? requestError.message : "Copilot request failed");
    } finally {
      setStatus("idle");
    }
  }

  const showIntro = messages.length === 0;
  const activeTitle = activeConversation?.title ?? "New conversation";
  const isBusy = status === "loading" || status === "creating" || status === "sending";

  const historyPanel = (
    <motion.aside
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -16 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="flex h-full w-full max-w-[320px] flex-col overflow-hidden rounded-[2rem] border border-white/[0.06] bg-[linear-gradient(180deg,rgba(22,24,28,0.96),rgba(9,10,11,0.98))] shadow-[0_28px_90px_rgba(0,0,0,0.38)]"
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-neutral-500">History</p>
          <h2 className="mt-1 text-sm font-semibold text-neutral-100">Previous conversations</h2>
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
          ) : (
            <div className="rounded-[1.5rem] border border-dashed border-white/[0.08] bg-white/[0.02] px-4 py-6 text-sm text-neutral-400">
              Your saved conversations will appear here after the first message.
            </div>
          )
        ) : (
          <div className="rounded-[1.5rem] border border-dashed border-white/[0.08] bg-white/[0.02] px-4 py-6 text-sm text-neutral-400">
            Connect your wallet to load saved copilot sessions.
          </div>
        )}
      </div>
    </motion.aside>
  );

  return (
    <main className="min-h-[calc(100vh-64px)] bg-[#090a0b] text-neutral-50 selection:bg-[#dce85d]/30">
      <div className="mx-auto flex h-[calc(100vh-64px)] max-w-7xl gap-4 px-4 py-4 md:px-6">
        <div className="hidden h-full lg:block">{historyOpen ? historyPanel : null}</div>

        <AnimatePresence>
          {historyOpen ? (
            <motion.div
              key="mobile-history"
              className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setHistoryOpen(false)}
            >
              <div className="h-full max-w-[340px] p-3" onClick={(event) => event.stopPropagation()}>
                {historyPanel}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>

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
                  History
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
            {!authenticated ? (
              <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
                <div className="space-y-3">
                  <p className="text-[11px] uppercase tracking-[0.3em] text-neutral-500">Authorized insight</p>
                  <h2 className="text-3xl font-semibold tracking-tight text-neutral-100 md:text-4xl">
                    Persistent copilot for your trading account
                  </h2>
                  <p className="mx-auto max-w-xl text-sm leading-relaxed text-neutral-400">
                    Connect your wallet to keep a saved conversation history, reopen earlier sessions, and let Copilot
                    compact older context automatically instead of losing it.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={login}
                  className="rounded-full bg-[#dce85d] px-5 py-3 text-sm font-semibold text-black transition hover:scale-[1.02]"
                >
                  Connect wallet to begin
                </button>
              </div>
            ) : showIntro ? (
              <div className="flex h-full flex-col items-center justify-center gap-10 text-center">
                <div className="max-w-2xl space-y-4">
                  <p className="text-[11px] uppercase tracking-[0.34em] text-neutral-500">Saved sessions</p>
                  <h2 className="text-3xl font-semibold tracking-tight text-neutral-100 md:text-5xl">
                    Start a fresh thread or reopen an older one.
                  </h2>
                  <p className="text-sm leading-relaxed text-neutral-400">
                    Copilot now keeps your conversation history, rolls older turns into a compact summary once the
                    session gets large, and continues from there without dropping the thread.
                  </p>
                </div>

                <div className="grid w-full max-w-3xl gap-3 md:grid-cols-2">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => void sendMessage(prompt)}
                      disabled={isBusy}
                      className="rounded-[1.6rem] border border-white/[0.05] bg-white/[0.025] px-5 py-5 text-left transition hover:border-[#dce85d]/30 hover:bg-[#dce85d]/[0.04] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <p className="text-sm font-medium text-neutral-100">{prompt}</p>
                      <p className="mt-2 text-xs leading-relaxed text-neutral-400">
                        Send this as the opening prompt in a saved conversation.
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
                              disabled={status === "sending"}
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

                {status === "sending" ? (
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
                  disabled={!authenticated}
                  placeholder={authenticated ? "Ask Copilot about your account, bots, or runtime state..." : "Connect wallet to start messaging..."}
                  rows={1}
                  className="max-h-[220px] min-h-[52px] w-full resize-none bg-transparent px-4 py-3 text-sm text-neutral-100 outline-none placeholder:text-neutral-500 disabled:cursor-not-allowed"
                />
                <button
                  type="button"
                  onClick={() => void sendMessage()}
                  disabled={!authenticated || status === "sending" || input.trim().length === 0}
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#dce85d] text-black transition hover:scale-[1.03] disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Send message"
                >
                  <SendHorizontal className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between gap-3 text-[11px] uppercase tracking-[0.22em] text-neutral-600">
              <span>Authorized ClashX data only</span>
              <span>{activeConversation ? `${activeConversation.messageCount} stored messages` : "No active session"}</span>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
