import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCallout, DocsCard } from "@/components/docs/DocsUI";
import { Bot, Network, ShieldCheck, MessagesSquare, Code } from "lucide-react";

export default function CopilotPage() {
    return (
        <DocsPageLayout
            title="AI Copilot"
            description="Your conversational trading assistant integrated deep into the systems."
        >
            <DocsCallout title="Autonomous Assistance">
                ClashX includes a full-featured AI copilot that acts as a conversational trading assistant. The copilot is deeply integrated with the platform's data layer, enabling it to answer questions, generate strategies, analyze performance, and execute platform actions on behalf of the user.
            </DocsCallout>

            <h2 className="mt-12">Architecture Overview</h2>
            <div className="grid gap-4 md:grid-cols-2 mt-6">
                <DocsCard title="Dual-provider failover" icon={<Network className="h-5 w-5" />}>
                    The copilot attempts requests against TrollLLM first, then falls back to OpenAI if unavailable. Ensures consistent uptime.
                </DocsCard>
                <DocsCard title="Tool-calling framework" icon={<Bot className="h-5 w-5" />}>
                    Extensive tool catalog enables the agent to query the database, inspect bot definitions, review execution history, and examine portfolios.
                </DocsCard>
                <DocsCard title="Conversation persistence" icon={<MessagesSquare className="h-5 w-5" />}>
                    Full conversation history is stored with rolling summarization to manage and optimize context window limits.
                </DocsCard>
                <DocsCard title="Scoped database access" icon={<ShieldCheck className="h-5 w-5" />}>
                    All queries are automatically and securely filtered against the authenticated user's active wallet address.
                </DocsCard>
            </div>

            <h2 className="mt-12">Supported Capabilities</h2>
            <p>The copilot can assist you directly via chat for a variety of execution tasks. Common prompts include:</p>

            <div className="mt-6 space-y-4">
                <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/5 px-4 py-3 text-sm text-neutral-300">
                    <Code className="h-4 w-4 text-[#dce85d]" />
                    <span>"Query my bot definitions, runtimes, and backtest history."</span>
                </div>
                <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/5 px-4 py-3 text-sm text-neutral-300">
                    <Code className="h-4 w-4 text-[#dce85d]" />
                    <span>"Inspect portfolio baskets and active allocation members."</span>
                </div>
                <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/5 px-4 py-3 text-sm text-neutral-300">
                    <Code className="h-4 w-4 text-[#dce85d]" />
                    <span>"Analyze performance metrics and trade history for the last 7 days."</span>
                </div>
                <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/5 px-4 py-3 text-sm text-neutral-300">
                    <Code className="h-4 w-4 text-[#dce85d]" />
                    <span>"Generate a momentum breakout strategy using RSI and SMA."</span>
                </div>
            </div>
        </DocsPageLayout>
    );
}
