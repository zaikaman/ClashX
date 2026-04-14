import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCallout, DocsStep, DocsCard } from "@/components/docs/DocsUI";

export default function IntroductionPage() {
    return (
        <DocsPageLayout
            title="Introduction to ClashX"
            description="Autonomous Trading Bot Platform Built on Pacifica Perpetuals Infrastructure"
        >
            <DocsCallout title="What is ClashX?">
                ClashX reimagines the perpetual futures trading experience by shifting the user's role from manual trader to bot operator. The platform is designed around a single insight: most retail traders lose money placing discretionary trades, but systematic, rule-based strategies with proper risk controls can outperform emotional decision-making.
            </DocsCallout>

            <h2>How it works</h2>
            <p className="mb-8">
                ClashX makes bot-driven trading accessible to everyone, from beginners who use pre-built templates to advanced quants who design sophisticated multi-condition strategies. The product flow is straightforward:
            </p>

            <div className="mb-12 border-l border-white/5 ml-2">
                <DocsStep number={1} title="Connect your wallet">
                    Use Privy's embedded wallet authentication.
                </DocsStep>
                <DocsStep number={2} title="Authorize delegated execution">
                    Allow ClashX to place trades on your behalf through Pacifica's agent wallet system, without ever taking custody of your funds.
                </DocsStep>
                <DocsStep number={3} title="Build a bot">
                    Use the visual graph-based builder or leverage the AI copilot to generate strategies from natural language descriptions.
                </DocsStep>
                <DocsStep number={4} title="Backtest your strategy">
                    Validate performance against historical market data before risking any capital.
                </DocsStep>
                <DocsStep number={5} title="Deploy the bot">
                    Begin automated trading on Pacifica's perpetuals markets.
                </DocsStep>
                <DocsStep number={6} title="Monitor performance">
                    Track real-time dashboards, execution logs, and health indicators.
                </DocsStep>
                <DocsStep number={7} title="Discover and copy">
                    Find top-performing bots from the public leaderboard, either by live mirroring or by cloning their configuration into your own editable draft.
                </DocsStep>
                <DocsStep number={8} title="Compose portfolios">
                    Allocate capital across multiple bots with automatic drift-based rebalancing.
                </DocsStep>
            </div>

            <DocsCallout type="warning" title="Non-custodial by Design">
                ClashX is not a custodial service. Users retain full control of their wallets at all times. The delegated authorization model ensures that ClashX can only execute trades within the boundaries set by the user, and authorization can be revoked instantly.
            </DocsCallout>
        </DocsPageLayout>
    );
}
