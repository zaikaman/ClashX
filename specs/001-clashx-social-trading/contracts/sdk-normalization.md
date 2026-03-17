# SDK Normalization Contract

This contract defines how source-authored SDK bots are compiled into the same runtime model used by visually composed bots.

## Goal

- Accept advanced authoring inputs.
- Validate and compile SDK source code.
- Produce a deterministic normalized `rules_json` payload and `sdk_bundle_ref`.
- Enforce the same deploy-time and runtime safety checks used by visual bots.

## Registration Input

`POST /api/sdk/register`

Required fields:
- `language` (`python`)
- `entrypoint`
- `source_code`

Optional fields:
- `metadata`

## Normalized Output

The backend returns:

- `sdk_bundle_ref`: unique immutable bundle reference
- `authoring_mode`: always `sdk`
- `normalized_rules_json`:

```json
{
  "conditions": [
    {
      "type": "price_above",
      "symbol": "BTC",
      "value": 100000
    }
  ],
  "actions": [
    {
      "type": "open_long",
      "symbol": "BTC",
      "size_usd": 150,
      "leverage": 3
    }
  ],
  "_sdk": {
    "language": "python",
    "entrypoint": "build_bot_definition",
    "source_hash": "..."
  }
}
```

## Runtime Convergence Rules

1. SDK bots must pass `BotDefinition` validation with `authoring_mode=sdk`.
2. `sdk_bundle_ref` is mandatory for deployable SDK bots.
3. Compiled SDK bots execute through the same rules engine as visual bots.
4. Runtime risk policies and execution guards are applied identically to visual and SDK bots.
4. Copy and leaderboard systems consume runtime outputs only; they do not branch by authoring mode.

## Error Contract

- Invalid language, entrypoint, imports, syntax, or compiled rules return `400` with actionable validation issues.
- Registration does not imply deployment; deployment still requires runtime authorization and bot validation.
