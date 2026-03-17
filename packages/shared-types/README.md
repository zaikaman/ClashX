# ClashX Shared Types

Shared event and API contract types consumed by frontend and backend.

## Bot Schemas

- `bot-schemas/bot-definition.schema.json`: canonical bot definition shape used by visual builder and SDK registration.
- `bot-schemas/sdk-manifest.schema.json`: SDK capability and runtime requirements schema.
- `bot-schemas/sdk-registration.schema.json`: schema for validating source-compiled SDK bot definitions before registration.

Both authoring paths must normalize into the same bot runtime payload used by backend services.

