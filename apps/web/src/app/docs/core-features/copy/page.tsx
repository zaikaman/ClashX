import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCallout, DocsCard, DocsStep } from "@/components/docs/DocsUI";
import { Copy, SplitSquareHorizontal, Lock } from "lucide-react";

export default function CopyTradingPage() {
    return (
        <DocsPageLayout
            title="Copy Trading and Mirroring"
            description="Leverage top-performing bots from the community."
        >
            <DocsCallout title="Accessing Community Alpha">
                ClashX supports two distinct copy trading models: Live Mirroring and Configuration Cloning. Both models empower users to utilize community alpha while retaining capital custody.
            </DocsCallout>

            <div className="my-12">
                <DocsCard title="Live Mirroring" icon={<Copy className="h-5 w-5" />}>
                    <div className="space-y-4 pt-2">
                        <div>
                            <strong className="text-white">Real-time Replication:</strong>
                            When a user mirrors a source bot, every execution event from the source bot is replicated to the follower's wallet in real-time.
                        </div>
                        <div>
                            <strong className="text-white">Scale Factors:</strong>
                            Followers can configure a scale factor (in basis points) to adjust position sizes. For example, a scale of 5000 bps means the follower takes positions at 50% of the source bot's size.
                        </div>
                        <div>
                            <strong className="text-white">Risk Limits:</strong>
                            Per-follower risk controls include maximum notional exposure limits and the ability to pause mirroring at any time.
                        </div>
                    </div>
                </DocsCard>
            </div>

            <div className="my-12">
                <DocsCard title="Configuration Cloning" icon={<SplitSquareHorizontal className="h-5 w-5" />}>
                    <div className="space-y-4 pt-2">
                        <div>Users can clone a public bot's strategy configuration into their own account as a new draft.</div>
                        <div>The cloned bot is fully editable, allowing the user to modify conditions, actions, risk parameters, and market scope before deployment.</div>
                        <div>Clone provenance is tracked in the system, maintaining an auditable lineage from source to derivative.</div>
                    </div>
                </DocsCard>
            </div>

            <h2 className="mt-12 flex items-center gap-2"><Lock className="h-6 w-6 text-white" /> Access Control</h2>
            <p>
                Creators have full control over who can copy their bots. Visibility can be set to <code>public</code>, <code>private</code>, <code>unlisted</code>, or <code>invite_only</code>.
            </p>
        </DocsPageLayout>
    );
}
