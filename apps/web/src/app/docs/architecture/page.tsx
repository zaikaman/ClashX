import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCode, DocsCard } from "@/components/docs/DocsUI";
import { Server, Layout, Database, Activity, Code } from "lucide-react";

export default function ArchitecturePage() {
    const architectureDiagram = `                                    +-----------------------+
                                    |    User (Web/Mobile)  |
                                    +-----------+-----------+
                                                |
                                    +-----------v-----------+
                                    |   Next.js 16 Frontend |
                                    |   (React 19 + TW CSS) |
                                    +-----------+-----------+
                                                |
                              +-----------------+-----------------+
                              |                                   |
                   +----------v----------+             +----------v----------+
                   |   Privy Auth Layer  |             |  FastAPI Backend    |
                   |   (Wallet Connect)  |             |  (Python 3.11+)    |
                   +---------------------+             +----------+----------+
                                                                  |
                         +----------------------------------------+-----------------------------+
                         |                |               |               |                     |
              +----------v---+   +--------v------+  +-----v------+  +----v--------+   +--------v-------+
              | Supabase     |   | Pacifica REST |  | Pacifica   |  | TrollLLM /  |   | Telegram Bot   |
              | PostgreSQL   |   | API           |  | WebSocket  |  | OpenAI API  |   | (Notifications)|
              | (30+ tables) |   | (Orders, Mkt) |  | (Realtime) |  | (Copilot)   |   | (Notifications)|
              +--------------+   +---------------+  +------------+  +-------------+   +----------------+

                              +----------------------------------------------+
                              |          Background Workers (5)              |
                              |  Bot Runtime | Copy | Snapshot | Portfolio   |
                              |  Backtest                                    |
                              +----------------------------------------------+`;

    return (
        <DocsPageLayout
            title="Architecture & Systems"
            description="High-level systemic overview of ClashX monorepo and service layer."
        >
            <h2>Architecture Topology</h2>
            <DocsCode language="ascii" code={architectureDiagram} />

            <h2>Technology Stack</h2>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mt-6">
                <DocsCard title="Frontend" icon={<Layout className="h-5 w-5" />}>
                    <ul className="not-prose space-y-1 text-sm text-neutral-400 list-disc ml-4">
                        <li><strong>Next.js 16.1</strong> + React 19</li>
                        <li><strong>Tailwind CSS</strong> for styling</li>
                        <li><strong>xyflow</strong> for Bot Builder</li>
                        <li><strong>Framer Motion</strong> for animations</li>
                        <li><strong>Privy</strong> for embedded wallets</li>
                    </ul>
                </DocsCard>

                <DocsCard title="Backend" icon={<Server className="h-5 w-5" />}>
                    <ul className="not-prose space-y-1 text-sm text-neutral-400 list-disc ml-4">
                        <li><strong>Python 3.11+</strong> backend</li>
                        <li><strong>FastAPI</strong> web framework</li>
                        <li><strong>Pydantic</strong> data modeling</li>
                        <li><strong>Solders</strong> for Solana primitives</li>
                    </ul>
                </DocsCard>

                <DocsCard title="Infrastructure" icon={<Database className="h-5 w-5" />}>
                    <ul className="not-prose space-y-1 text-sm text-neutral-400 list-disc ml-4">
                        <li><strong>Supabase</strong> Postgres + REST API</li>
                        <li><strong>Vercel</strong> for Next.js deployments</li>
                        <li><strong>Railway</strong> for API & Workers</li>
                    </ul>
                </DocsCard>
            </div>

            <h2 className="mt-12">Background Workers</h2>
            <p>ClashX runs five background workers that handle asynchronous processing using a lease-based coordination system:</p>

            <div className="space-y-4 mt-6">
                <div className="rounded-xl border border-white/5 bg-black/20 p-5">
                    <div className="flex items-center gap-3 mb-2">
                        <Activity className="h-4 w-4 text-[#dce85d]" />
                        <h4 className="text-white font-medium not-prose m-0">BotRuntimeWorker</h4>
                    </div>
                    <p className="not-prose text-sm text-neutral-400">Core bot execution loop. Evaluates rules and submits orders.</p>
                </div>

                <div className="rounded-xl border border-white/5 bg-black/20 p-5">
                    <div className="flex items-center gap-3 mb-2">
                        <Activity className="h-4 w-4 text-[#dce85d]" />
                        <h4 className="text-white font-medium not-prose m-0">BotCopyWorker</h4>
                    </div>
                    <p className="not-prose text-sm text-neutral-400">Monitors source bot execution events and replicates them to followers.</p>
                </div>

                <div className="rounded-xl border border-white/5 bg-black/20 p-5">
                    <div className="flex items-center gap-3 mb-2">
                        <Activity className="h-4 w-4 text-[#dce85d]" />
                        <h4 className="text-white font-medium not-prose m-0">BacktestJobWorker</h4>
                    </div>
                    <p className="not-prose text-sm text-neutral-400">Processes queued backtest jobs asynchronously.</p>
                </div>

                <div className="rounded-xl border border-white/5 bg-black/20 p-5">
                    <div className="flex items-center gap-3 mb-2">
                        <Activity className="h-4 w-4 text-[#dce85d]" />
                        <h4 className="text-white font-medium not-prose m-0">PortfolioAllocatorWorker</h4>
                    </div>
                    <p className="not-prose text-sm text-neutral-400">Monitors portfolios for drift and triggers automatic rebalancing.</p>
                </div>
            </div>
        </DocsPageLayout>
    );
}
