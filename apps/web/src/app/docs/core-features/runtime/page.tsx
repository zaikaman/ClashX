import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCallout, DocsCard } from "@/components/docs/DocsUI";
import { Play, Pause, StopCircle, ClipboardEdit, ServerCog } from "lucide-react";

export default function RuntimePage() {
    return (
        <DocsPageLayout
            title="Bot Runtime Engine"
            description="The engine orchestrating lifecycle states of your trading bots."
        >
            <DocsCallout title="Execution Loop">
                The runtime engine is responsible for the full lifecycle of bot execution: deployment, evaluation, action submission, pause/resume, and graceful shutdown.
            </DocsCallout>

            <h2 className="mt-12">Lifecycle States</h2>

            <div className="grid gap-4 mt-6">
                <DocsCard title="Draft" icon={<ClipboardEdit className="h-5 w-5" />}>
                    Bot definition created but not yet deployed. Safe to edit.
                </DocsCard>
                <DocsCard title="Active" icon={<Play className="h-5 w-5" />}>
                    Bot is live and evaluating rules on each tick against current market conditions.
                </DocsCard>
                <DocsCard title="Paused" icon={<Pause className="h-5 w-5" />}>
                    Bot is temporarily suspended; no new actions are submitted but positions may be tracked.
                </DocsCard>
                <DocsCard title="Stopped" icon={<StopCircle className="h-5 w-5" />}>
                    Bot is permanently deactivated and all related active tracking ceases.
                </DocsCard>
            </div>

            <h2 className="mt-12">Execution Model</h2>
            <p>
                The <code>BotRuntimeWorker</code> continuously polls for active runtimes, evaluates their rule sets against current market conditions, and submits actions to Pacifica when conditions are met.
            </p>

            <div className="my-6 space-y-3 pl-4 border-l border-white/10">
                <p className="not-prose text-sm text-neutral-400">Each evaluation cycle fetches real-time price data, candlestick history, and current position state from Pacifica's REST and WebSocket APIs.</p>
                <p className="not-prose text-sm text-neutral-400">An idempotency layer prevents duplicate order submission in case of worker restarts.</p>
                <p className="not-prose text-sm text-neutral-400">Every execution event is logged.</p>
            </div>

            <h2 className="mt-12">Advanced Execution Controls</h2>
            <div className="grid gap-4 md:grid-cols-2 mt-6">
                <DocsCard title="Sizing Configuration" icon={<ServerCog className="h-5 w-5" />}>
                    Configurable leverage, precision position sizing (fixed amount, percentage of equity, risk-based logic).
                </DocsCard>
                <DocsCard title="Action Governance" icon={<ServerCog className="h-5 w-5" />}>
                    Cooldown periods between trades, market scope restrictions, and maximum drawdown limits with automatic pause.
                </DocsCard>
            </div>
        </DocsPageLayout>
    );
}
