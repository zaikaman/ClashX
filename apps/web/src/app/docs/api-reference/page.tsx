import { DocsPageLayout } from "@/components/docs/DocsPageLayout";
import { DocsCode, DocsCallout } from "@/components/docs/DocsUI";

export default function ApiReferencePage() {
    return (
        <DocsPageLayout
            title="API Reference"
            description="FastAPI service endpoints and routing structures."
        >
            <DocsCallout title="Protected Architecture">
                ClashX uses a RESTful backend written in FastAPI (Python 3.11+). All endpoints are protected by Privy JWT validation via Middleware, resolving to the authenticated user's wallet automatically.
            </DocsCallout>

            <h2>Authentication and Authorization</h2>
            <DocsCode language="http" code={`GET  /api/pacifica/authorize         # Check authorization status
POST /api/pacifica/authorize/start   # Initiate delegated wallet auth
POST /api/pacifica/authorize/activate # Complete activation`} />

            <h2>Bot Builder and Runtime</h2>
            <DocsCode language="http" code={`GET   /api/bots                      # List all bots owned by user
POST  /api/bots                      # Create a new bot definition
GET   /api/bots/{bot_id}             # Get bot details and runtime state
PATCH /api/bots/{bot_id}             # Update bot configuration
POST  /api/bots/{bot_id}/validate    # Validate bot rules
POST  /api/bots/{bot_id}/deploy      # Deploy bot to start live execution
POST  /api/bots/{bot_id}/pause       # Pause runtime
POST  /api/bots/{bot_id}/resume      # Resume runtime
POST  /api/bots/{bot_id}/stop        # Permanently stop
GET   /api/bots/{bot_id}/events      # List execution event logs`} />

            <h2>Copy Trading</h2>
            <DocsCode language="http" code={`POST   /api/bots/{id}/copy/preview   # Preview mirror relationship
POST   /api/bots/{id}/copy/mirror    # Activate live mirroring
POST   /api/bots/{id}/copy/clone     # Clone bot configuration
PATCH  /api/copy/{id}                # Update relationship
DELETE /api/copy/{id}                # Deactivate relationship`} />

            <h2>Realtime Streaming</h2>
            <DocsCode language="http" code={`GET /api/stream/bots/{runtime_id}    # SSE stream for bot runtime events
GET /api/stream/leaderboard/bots      # SSE stream for leaderboard updates
GET /api/stream/user/{user_id}       # SSE stream for user-level events`} />
        </DocsPageLayout>
    );
}
