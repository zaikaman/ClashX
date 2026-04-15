import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { Network, Timer, Lock, ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";

export default function RoadmapPage() {
    return (
        <DocsPageLayout
            title="Roadmap"
            description="Our vision for the future of ClashX. Taking autonomous trading beyond single-strategy automation."
        >
            <div className="relative mt-8 space-y-12 before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-white/10 before:to-transparent">

                {/* Milestone 1 */}
                <div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                    {/* Marker */}
                    <div className="flex items-center justify-center w-10 h-10 rounded-full border border-[#dce85d]/30 bg-[#dce85d]/10 text-[#dce85d] shadow-[0_0_15px_rgba(220,232,93,0.2)] md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 relative z-10">
                        <Network className="w-5 h-5" />
                    </div>
                    {/* Card */}
                    <div className="w-[calc(100%-3rem)] md:w-[calc(50%-2.5rem)] p-6 rounded-2xl border border-white/10 bg-[#090a0a]/80 backdrop-blur-md shadow-2xl transition-all duration-300 hover:border-[#dce85d]/50 hover:shadow-[0_0_30px_rgba(220,232,93,0.15)] group-hover:-translate-y-1">
                        <div className="flex flex-col items-start gap-2 mb-3">
                            <span className="shrink-0 w-fit whitespace-nowrap px-2 py-1 rounded-md bg-[#dce85d]/10 text-[#dce85d] text-xs font-bold uppercase tracking-wider">Phase I</span>
                            <h3 className="text-xl font-bold text-white m-0 mt-0">Cross-Margin Portfolio Engine</h3>
                        </div>
                        <p className="text-neutral-400 text-sm leading-relaxed mb-4">
                            Capital can be globally allocated across multiple correlated positions with shared risk awareness. Move beyond single-strategy automation into expressive, full-portfolio risk management.
                        </p>
                        <div className="flex flex-wrap gap-2">
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Shared Margin</span>
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Risk Awareness</span>
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Auto Rebalancing</span>
                        </div>
                    </div>
                </div>

                {/* Milestone 2 */}
                <div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group">
                    <div className="flex items-center justify-center w-10 h-10 rounded-full border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.2)] md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 relative z-10">
                        <Timer className="w-5 h-5" />
                    </div>
                    <div className="w-[calc(100%-3rem)] md:w-[calc(50%-2.5rem)] p-6 rounded-2xl border border-white/10 bg-[#090a0a]/80 backdrop-blur-md shadow-2xl transition-all duration-300 hover:border-cyan-500/50 hover:shadow-[0_0_30px_rgba(6,182,212,0.15)] group-hover:-translate-y-1">
                        <div className="flex flex-col items-start gap-2 mb-3">
                            <span className="shrink-0 w-fit whitespace-nowrap px-2 py-1 rounded-md bg-cyan-500/10 text-cyan-400 text-xs font-bold uppercase tracking-wider">Phase II</span>
                            <h3 className="text-xl font-bold text-white m-0 mt-0">TWAP / VWAP Execution Nodes</h3>
                        </div>
                        <p className="text-neutral-400 text-sm leading-relaxed mb-4">
                            Implement slower, more deliberate order flow instead of simple one-shot entries. Scale into positions intelligently without disrupting the Pacifica orderbook.
                        </p>
                        <div className="flex flex-wrap gap-2">
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Smart Execution</span>
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Time-Weighted</span>
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Volume-Weighted</span>
                        </div>
                    </div>
                </div>

                {/* Milestone 3 */}
                <div className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group">
                    <div className="flex items-center justify-center w-10 h-10 rounded-full border border-purple-500/30 bg-purple-500/10 text-purple-400 shadow-[0_0_15px_rgba(168,85,247,0.2)] md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 relative z-10">
                        <Lock className="w-5 h-5" />
                    </div>
                    <div className="w-[calc(100%-3rem)] md:w-[calc(50%-2.5rem)] p-6 rounded-2xl border border-white/10 bg-[#090a0a]/80 backdrop-blur-md shadow-2xl transition-all duration-300 hover:border-purple-500/50 hover:shadow-[0_0_30px_rgba(168,85,247,0.15)] group-hover:-translate-y-1">
                        <div className="flex flex-col items-start gap-2 mb-3">
                            <span className="shrink-0 w-fit whitespace-nowrap px-2 py-1 rounded-md bg-purple-500/10 text-purple-400 text-xs font-bold uppercase tracking-wider">Phase III</span>
                            <h3 className="text-xl font-bold text-white m-0 mt-0">NFT-Gated Private Bots</h3>
                        </div>
                        <p className="text-neutral-400 text-sm leading-relaxed mb-4">
                            Access, subscriptions, and strategy communities can all live on-chain. Tokenize access to top-performing alpha, creating exclusive ecosystems for top creators.
                        </p>
                        <div className="flex flex-wrap gap-2">
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Web3 Native</span>
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Token Gating</span>
                            <span className="text-xs px-2 py-1 bg-white/5 border border-white/10 rounded-md text-neutral-300">Creator Economy</span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-16 sm:mt-24 rounded-3xl border border-white/10 bg-gradient-to-b from-white/5 to-transparent p-8 md:p-12 text-center relative overflow-hidden group">
                <div className="absolute inset-0 bg-[#dce85d]/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-32 h-32 bg-[#dce85d]/20 blur-[100px] rounded-full pointer-events-none" />

                <h3 className="text-2xl md:text-3xl font-bold text-white mb-4 relative z-10 flex items-center justify-center gap-3">
                    <Sparkles className="w-6 h-6 text-[#dce85d]" />
                    ClashX is just getting started
                </h3>
                <p className="text-neutral-400 text-lg mb-8 max-w-2xl mx-auto relative z-10">
                    We're building the future of autonomous, zero-emotion trading on Pacifica. Join us to reshape how the world executes strategies.
                </p>

                <Link href="/dashboard" className="inline-flex items-center gap-2 bg-white !text-black !no-underline px-6 py-3 rounded-full font-medium hover:bg-[#dce85d] transition-colors relative z-10 group/btn">
                    Launch Application
                    <ArrowRight className="w-4 h-4 group-hover/btn:translate-x-1 transition-transform" />
                </Link>
            </div>
        </DocsPageLayout>
    );
}
