import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCard, DocsCallout } from "@/components/docs/DocsUI";
import { CopyPlus, Compass, MousePointerSquareDashed, ShieldAlert } from "lucide-react";

export default function BuilderPage() {
    return (
        <DocsPageLayout
            title="Visual Bot Builder Studio"
            description="The centerpiece of ClashX's user experience."
        >
            <DocsCallout title="Node-Based Strategy Creator">
                The builder studio provides a node-based graph editor (powered by xyflow) where users visually compose trading strategies by connecting condition nodes to action nodes. No coding required.
            </DocsCallout>

            <h2 className="mt-12">Key Capabilities</h2>

            <div className="grid gap-6 md:grid-cols-2 mt-6">
                <DocsCard title="Drag-and-drop editor" icon={<MousePointerSquareDashed className="h-5 w-5" />}>
                    Place condition nodes (price thresholds, technical indicators) and action nodes (open long, close position) onto a canvas and connect them with directional edges.
                </DocsCard>

                <DocsCard title="Template library" icon={<CopyPlus className="h-5 w-5" />}>
                    Pre-built templates covering patterns like RSI mean-reversion, SMA crossover, and momentum following. Serve as strong starting points.
                </DocsCard>

                <DocsCard title="Real-time validation" icon={<ShieldAlert className="h-5 w-5" />}>
                    Continuously validates the graph for structural correctness, ensuring every entry action has a protective stop-loss, no orphan nodes exist.
                </DocsCard>

                <DocsCard title="Simulation mode" icon={<Compass className="h-5 w-5" />}>
                    Before deployment, users can simulate their strategy against recent market conditions to preview expected behavior before risking capital.
                </DocsCard>
            </div>
        </DocsPageLayout>
    );
}
