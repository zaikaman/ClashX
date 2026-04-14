import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCallout, DocsCard } from "@/components/docs/DocsUI";
import { Activity, ShieldCheck, Zap } from "lucide-react";

export default function RulesEnginePage() {
    return (
        <DocsPageLayout
            title="Rules Engine"
            description="The decision-making core of ClashX."
        >
            <DocsCallout title="Core Execution System">
                The rules engine evaluates bot strategy graphs against live market data and produces a list of actions to execute. It's the core system that takes user intent and translates it into on-chain Pacifica orders.
            </DocsCallout>

            <h2>Supported Conditions</h2>
            <p>
                The rules engine supports over 50 approved condition types across several categories:
            </p>

            <div className="grid gap-6 md:grid-cols-2 my-8">
                <DocsCard title="Price Conditions" icon={<Activity className="h-5 w-5" />}>
                    <ul className="not-prose pl-4 text-sm space-y-1 mb-0 list-disc text-neutral-400">
                        <li><code>price_above</code> / <code>price_below</code></li>
                        <li><code>price_change_up</code> / <code>price_change_down</code></li>
                        <li><code>price_crosses_above</code> / <code>price_crosses_below</code></li>
                    </ul>
                </DocsCard>

                <DocsCard title="Indicator Conditions" icon={<Zap className="h-5 w-5" />}>
                    <ul className="not-prose pl-4 text-sm space-y-1 mb-0 list-disc text-neutral-400">
                        <li><code>rsi_above</code> / <code>rsi_below</code></li>
                        <li><code>sma_crossover</code> / <code>ema_crossover</code></li>
                        <li><code>macd_bullish</code> / <code>macd_bearish</code></li>
                        <li><code>bollinger_bands_breakout</code></li>
                    </ul>
                </DocsCard>
            </div>

            <h2>Supported Actions</h2>
            <p>When conditions are met, the engine emits actions. Available actions include:</p>
            <div className="rounded-xl border border-white/10 bg-[#000000] p-6 font-mono text-sm">
                <div className="flex flex-col gap-3 text-neutral-300">
                    <div><code className="text-[#dce85d]">open_long</code> / <code className="text-[#dce85d]">open_short</code><span className="text-neutral-500 ml-4">// Initiate a new position</span></div>
                    <div><code className="text-[#dce85d]">close_position</code> / <code className="text-[#dce85d]">close_all_positions</code><span className="text-neutral-500 ml-4">// Exit active trades</span></div>
                    <div><code className="text-[#dce85d]">set_stop_loss</code> / <code className="text-[#dce85d]">set_take_profit</code><span className="text-neutral-500 ml-4">// Defensive order placement</span></div>
                    <div><code className="text-[#dce85d]">scale_in</code> / <code className="text-[#dce85d]">scale_out</code><span className="text-neutral-500 ml-4">// Partial position sizing</span></div>
                    <div><code className="text-[#dce85d]">pause_bot</code><span className="text-neutral-500 ml-4">// Hard-stop automation based on severe risk triggers</span></div>
                </div>
            </div>

            <h2>Validation Pipeline</h2>
            <p>Before a strategy graph can be deployed, it passes through rigorous structural validation:</p>

            <div className="space-y-4">
                <div className="flex items-start gap-4">
                    <div className="mt-1 rounded-full bg-[#dce85d]/10 p-2 text-[#dce85d] ring-1 ring-white/10"><ShieldCheck className="h-4 w-4" /></div>
                    <div>
                        <h4 className="not-prose font-semibold text-white m-0">Topology checks</h4>
                        <p className="not-prose text-sm text-neutral-400 m-0 mt-1">Enforces no cycles, no orphan action nodes, single root per isolated logic tree.</p>
                    </div>
                </div>
                <div className="flex items-start gap-4">
                    <div className="mt-1 rounded-full bg-[#dce85d]/10 p-2 text-[#dce85d] ring-1 ring-white/10"><ShieldCheck className="h-4 w-4" /></div>
                    <div>
                        <h4 className="not-prose font-semibold text-white m-0">Risk enforcement</h4>
                        <p className="not-prose text-sm text-neutral-400 m-0 mt-1">Asserts that every <code>open_</code> node has a reachable stop-loss path.</p>
                    </div>
                </div>
                <div className="flex items-start gap-4">
                    <div className="mt-1 rounded-full bg-[#dce85d]/10 p-2 text-[#dce85d] ring-1 ring-white/10"><ShieldCheck className="h-4 w-4" /></div>
                    <div>
                        <h4 className="not-prose font-semibold text-white m-0">Parameter checks</h4>
                        <p className="not-prose text-sm text-neutral-400 m-0 mt-1">Verifies schema compliance for numeric thresholds.</p>
                    </div>
                </div>
            </div>
        </DocsPageLayout>
    );
}
