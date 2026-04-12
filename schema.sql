


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


COMMENT ON SCHEMA "public" IS 'standard public schema';



CREATE EXTENSION IF NOT EXISTS "pg_graphql" WITH SCHEMA "graphql";






CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";






CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";






CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";





SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."ai_job_runs" (
    "id" "uuid" NOT NULL,
    "job_type" character varying NOT NULL,
    "status" character varying DEFAULT 'queued'::character varying NOT NULL,
    "wallet_address" character varying,
    "conversation_id" "uuid",
    "request_payload_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "result_payload_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "error_detail" "text",
    "started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."ai_job_runs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."audit_events" (
    "id" "uuid" NOT NULL,
    "user_id" "uuid",
    "action" character varying(120) NOT NULL,
    "payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."audit_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_action_claims" (
    "id" "uuid" NOT NULL,
    "runtime_id" "uuid" NOT NULL,
    "idempotency_key" character varying(255) NOT NULL,
    "claimed_by" character varying(128) NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_action_claims" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_backtest_runs" (
    "id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "wallet_address" character varying(128) NOT NULL,
    "bot_name_snapshot" character varying(120) NOT NULL,
    "rules_snapshot_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "interval" character varying(8) NOT NULL,
    "start_time" bigint NOT NULL,
    "end_time" bigint NOT NULL,
    "initial_capital_usd" double precision DEFAULT 0 NOT NULL,
    "execution_model" character varying(64) DEFAULT 'candle_close_v2'::character varying NOT NULL,
    "pnl_total" double precision DEFAULT 0 NOT NULL,
    "pnl_total_pct" double precision DEFAULT 0 NOT NULL,
    "max_drawdown_pct" double precision DEFAULT 0 NOT NULL,
    "win_rate" double precision DEFAULT 0 NOT NULL,
    "trade_count" integer DEFAULT 0 NOT NULL,
    "status" character varying(24) DEFAULT 'completed'::character varying NOT NULL,
    "result_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "completed_at" timestamp with time zone,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "market_scope_snapshot" character varying(120) DEFAULT 'Pacifica perpetuals'::character varying NOT NULL,
    "strategy_type_snapshot" character varying(64) DEFAULT 'rules'::character varying NOT NULL,
    "assumption_config_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "failure_reason" "text"
);


ALTER TABLE "public"."bot_backtest_runs" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_clones" (
    "id" "uuid" NOT NULL,
    "source_bot_definition_id" "uuid" NOT NULL,
    "new_bot_definition_id" "uuid" NOT NULL,
    "created_by_user_id" "uuid" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_clones" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_copy_relationships" (
    "id" "uuid" NOT NULL,
    "source_runtime_id" "uuid" NOT NULL,
    "follower_user_id" "uuid" NOT NULL,
    "follower_wallet_address" character varying(128) NOT NULL,
    "mode" character varying(24) DEFAULT 'mirror'::character varying NOT NULL,
    "scale_bps" integer DEFAULT 10000 NOT NULL,
    "status" character varying(24) DEFAULT 'active'::character varying NOT NULL,
    "risk_ack_version" character varying(24) DEFAULT 'v1'::character varying NOT NULL,
    "confirmed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "portfolio_basket_id" "uuid",
    "max_notional_usd" double precision
);


ALTER TABLE "public"."bot_copy_relationships" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_definitions" (
    "id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "wallet_address" character varying(128) NOT NULL,
    "name" character varying(120) NOT NULL,
    "description" "text" DEFAULT ''::"text" NOT NULL,
    "visibility" character varying(24) DEFAULT 'private'::character varying NOT NULL,
    "market_scope" character varying(120) DEFAULT 'Pacifica perpetuals'::character varying NOT NULL,
    "strategy_type" character varying(64) DEFAULT 'rules'::character varying NOT NULL,
    "authoring_mode" character varying(24) DEFAULT 'visual'::character varying NOT NULL,
    "rules_version" integer DEFAULT 1 NOT NULL,
    "rules_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "sdk_bundle_ref" character varying(255),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_definitions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_execution_events" (
    "id" "uuid" NOT NULL,
    "runtime_id" "uuid" NOT NULL,
    "event_type" character varying(48) NOT NULL,
    "decision_summary" "text" DEFAULT ''::"text" NOT NULL,
    "request_payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "result_payload" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "status" character varying(24) DEFAULT 'pending'::character varying NOT NULL,
    "error_reason" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_execution_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_invite_access" (
    "id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "invited_wallet_address" character varying(128) NOT NULL,
    "invited_by_user_id" "uuid" NOT NULL,
    "status" character varying(24) DEFAULT 'active'::character varying NOT NULL,
    "note" "text" DEFAULT ''::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_invite_access" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_leaderboard_snapshots" (
    "id" "uuid" NOT NULL,
    "runtime_id" "uuid" NOT NULL,
    "rank" integer DEFAULT 0 NOT NULL,
    "pnl_total" double precision DEFAULT 0 NOT NULL,
    "pnl_unrealized" double precision DEFAULT 0 NOT NULL,
    "win_streak" integer DEFAULT 0 NOT NULL,
    "drawdown" double precision DEFAULT 0 NOT NULL,
    "captured_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_leaderboard_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_publish_snapshots" (
    "id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "strategy_version_id" "uuid" NOT NULL,
    "runtime_id" "uuid",
    "visibility_snapshot" character varying(24) DEFAULT 'public'::character varying NOT NULL,
    "publish_state" character varying(24) DEFAULT 'published'::character varying NOT NULL,
    "summary_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_publish_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_publishing_settings" (
    "id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "visibility" character varying(24) DEFAULT 'private'::character varying NOT NULL,
    "access_mode" character varying(24) DEFAULT 'private'::character varying NOT NULL,
    "publish_state" character varying(24) DEFAULT 'draft'::character varying NOT NULL,
    "listed_at" timestamp with time zone,
    "hero_headline" "text" DEFAULT ''::"text" NOT NULL,
    "access_note" "text" DEFAULT ''::"text" NOT NULL,
    "featured_collection_key" character varying(120),
    "featured_collection_title" character varying(120),
    "featured_rank" integer DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_publishing_settings" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_runtime_snapshots" (
    "runtime_id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "user_id" "uuid",
    "wallet_address" character varying NOT NULL,
    "status" character varying DEFAULT 'draft'::character varying NOT NULL,
    "mode" character varying DEFAULT 'live'::character varying NOT NULL,
    "health_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "metrics_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "performance_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "source_runtime_updated_at" timestamp with time zone,
    "last_computed_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_runtime_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_runtimes" (
    "id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "wallet_address" character varying(128) NOT NULL,
    "status" character varying(24) DEFAULT 'draft'::character varying NOT NULL,
    "mode" character varying(24) DEFAULT 'live'::character varying NOT NULL,
    "risk_policy_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "deployed_at" timestamp with time zone,
    "stopped_at" timestamp with time zone,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_runtimes" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_strategy_versions" (
    "id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "created_by_user_id" "uuid" NOT NULL,
    "version_number" integer DEFAULT 1 NOT NULL,
    "change_kind" character varying(32) DEFAULT 'revision'::character varying NOT NULL,
    "visibility_snapshot" character varying(24) DEFAULT 'private'::character varying NOT NULL,
    "name_snapshot" character varying(120) NOT NULL,
    "description_snapshot" "text" DEFAULT ''::"text" NOT NULL,
    "market_scope_snapshot" character varying(120) DEFAULT 'Pacifica perpetuals'::character varying NOT NULL,
    "strategy_type_snapshot" character varying(64) DEFAULT 'rules'::character varying NOT NULL,
    "authoring_mode_snapshot" character varying(24) DEFAULT 'visual'::character varying NOT NULL,
    "rules_version_snapshot" integer DEFAULT 1 NOT NULL,
    "rules_json_snapshot" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "is_public_release" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_strategy_versions" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_trade_closures" (
    "id" "uuid" NOT NULL,
    "runtime_id" "uuid" NOT NULL,
    "lot_id" "uuid" NOT NULL,
    "symbol" character varying NOT NULL,
    "side" character varying NOT NULL,
    "closed_at" timestamp with time zone NOT NULL,
    "source" character varying NOT NULL,
    "source_event_id" "uuid",
    "source_order_id" character varying,
    "source_history_id" bigint,
    "quantity_closed" double precision DEFAULT 0 NOT NULL,
    "entry_price" double precision DEFAULT 0 NOT NULL,
    "exit_price" double precision DEFAULT 0 NOT NULL,
    "realized_pnl" double precision DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_trade_closures" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_trade_lots" (
    "id" "uuid" NOT NULL,
    "runtime_id" "uuid" NOT NULL,
    "symbol" character varying NOT NULL,
    "side" character varying NOT NULL,
    "opened_at" timestamp with time zone NOT NULL,
    "source" character varying DEFAULT 'bot'::character varying NOT NULL,
    "source_event_id" "uuid",
    "source_order_id" character varying,
    "source_history_id" bigint,
    "entry_price" double precision DEFAULT 0 NOT NULL,
    "quantity_opened" double precision DEFAULT 0 NOT NULL,
    "quantity_remaining" double precision DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."bot_trade_lots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."bot_trade_sync_state" (
    "runtime_id" "uuid" NOT NULL,
    "synced_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "execution_events_count" integer DEFAULT 0 NOT NULL,
    "position_history_count" integer DEFAULT 0 NOT NULL,
    "last_execution_at" timestamp with time zone,
    "last_history_at" timestamp with time zone,
    "last_error" "text"
);


ALTER TABLE "public"."bot_trade_sync_state" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."copilot_conversations" (
    "id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "wallet_address" character varying NOT NULL,
    "title" character varying DEFAULT 'New conversation'::character varying NOT NULL,
    "context_summary" "text" DEFAULT ''::"text" NOT NULL,
    "summary_message_count" integer DEFAULT 0 NOT NULL,
    "summary_token_estimate" integer DEFAULT 0 NOT NULL,
    "message_count" integer DEFAULT 0 NOT NULL,
    "last_message_preview" "text" DEFAULT ''::"text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "latest_message_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."copilot_conversations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."copilot_messages" (
    "id" "uuid" NOT NULL,
    "conversation_id" "uuid" NOT NULL,
    "role" character varying NOT NULL,
    "content" "text" DEFAULT ''::"text" NOT NULL,
    "tool_calls_json" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "follow_ups_json" "jsonb" DEFAULT '[]'::"jsonb" NOT NULL,
    "provider" character varying,
    "token_estimate" integer DEFAULT 0 NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."copilot_messages" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."copy_execution_events" (
    "id" "uuid" NOT NULL,
    "copy_relationship_id" "uuid" NOT NULL,
    "source_order_ref" character varying(120) NOT NULL,
    "mirrored_order_ref" character varying(120) NOT NULL,
    "symbol" character varying(16) NOT NULL,
    "side" character varying(8) NOT NULL,
    "size_source" double precision DEFAULT 0 NOT NULL,
    "size_mirrored" double precision DEFAULT 0 NOT NULL,
    "status" character varying(24) DEFAULT 'queued'::character varying NOT NULL,
    "error_reason" character varying(240),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."copy_execution_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."copy_relationships" (
    "id" "uuid" NOT NULL,
    "follower_user_id" "uuid" NOT NULL,
    "source_user_id" "uuid" NOT NULL,
    "scale_bps" integer DEFAULT 10000 NOT NULL,
    "status" character varying(24) DEFAULT 'active'::character varying NOT NULL,
    "risk_ack_version" character varying(24) DEFAULT 'v1'::character varying NOT NULL,
    "max_notional_usd" double precision,
    "confirmed_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."copy_relationships" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."creator_marketplace_profiles" (
    "id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "display_name" character varying(120) NOT NULL,
    "slug" character varying(160) NOT NULL,
    "headline" "text" DEFAULT ''::"text" NOT NULL,
    "bio" "text" DEFAULT ''::"text" NOT NULL,
    "social_links_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "featured_collection_title" character varying(120) DEFAULT 'Featured strategies'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."creator_marketplace_profiles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."featured_bots" (
    "id" "uuid" NOT NULL,
    "creator_profile_id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "collection_key" character varying(120) DEFAULT 'featured'::character varying NOT NULL,
    "collection_title" character varying(120) DEFAULT 'Featured strategies'::character varying NOT NULL,
    "shelf_rank" integer DEFAULT 0 NOT NULL,
    "featured_reason" "text" DEFAULT ''::"text" NOT NULL,
    "active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."featured_bots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."leaderboard_snapshots" (
    "id" "uuid" NOT NULL,
    "league_id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "rank" integer NOT NULL,
    "unrealized_pnl" double precision DEFAULT 0 NOT NULL,
    "realized_pnl" double precision DEFAULT 0 NOT NULL,
    "win_streak" integer DEFAULT 0 NOT NULL,
    "captured_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."leaderboard_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."marketplace_creator_snapshots" (
    "creator_id" "uuid" NOT NULL,
    "display_name" character varying DEFAULT ''::character varying NOT NULL,
    "marketplace_reach_score" integer DEFAULT 0 NOT NULL,
    "highlight_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "profile_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "last_computed_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."marketplace_creator_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."marketplace_runtime_snapshots" (
    "runtime_id" "uuid" NOT NULL,
    "bot_definition_id" "uuid" NOT NULL,
    "creator_id" "uuid" NOT NULL,
    "strategy_type" character varying DEFAULT ''::character varying NOT NULL,
    "rank" integer DEFAULT 0 NOT NULL,
    "row_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "detail_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "captured_at" timestamp with time zone,
    "last_computed_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."marketplace_runtime_snapshots" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."pacifica_authorizations" (
    "id" "uuid" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "account_address" character varying(128) NOT NULL,
    "agent_wallet_address" character varying(128) NOT NULL,
    "encrypted_agent_private_key" "text" NOT NULL,
    "builder_code" character varying(32),
    "max_fee_rate" character varying(32) DEFAULT '0.001'::character varying NOT NULL,
    "status" character varying(24) DEFAULT 'draft'::character varying NOT NULL,
    "builder_approval_message" "text",
    "builder_approval_timestamp" bigint,
    "builder_approval_expiry_window" integer,
    "builder_approval_signature" "text",
    "builder_approved_at" timestamp with time zone,
    "bind_agent_message" "text" NOT NULL,
    "bind_agent_timestamp" bigint NOT NULL,
    "bind_agent_expiry_window" integer NOT NULL,
    "bind_agent_signature" "text",
    "agent_bound_at" timestamp with time zone,
    "last_error" character varying(240),
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."pacifica_authorizations" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."portfolio_allocation_members" (
    "id" "uuid" NOT NULL,
    "portfolio_basket_id" "uuid" NOT NULL,
    "source_runtime_id" "uuid" NOT NULL,
    "target_weight_pct" double precision DEFAULT 0 NOT NULL,
    "target_notional_usd" double precision DEFAULT 0 NOT NULL,
    "max_scale_bps" integer DEFAULT 20000 NOT NULL,
    "target_scale_bps" integer DEFAULT 10000 NOT NULL,
    "relationship_id" "uuid",
    "status" character varying(24) DEFAULT 'active'::character varying NOT NULL,
    "latest_scale_bps" integer,
    "last_rebalanced_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."portfolio_allocation_members" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."portfolio_baskets" (
    "id" "uuid" NOT NULL,
    "owner_user_id" "uuid" NOT NULL,
    "wallet_address" character varying(128) NOT NULL,
    "name" character varying(120) NOT NULL,
    "description" "text" DEFAULT ''::"text" NOT NULL,
    "status" character varying(24) DEFAULT 'draft'::character varying NOT NULL,
    "rebalance_mode" character varying(24) DEFAULT 'drift'::character varying NOT NULL,
    "rebalance_interval_minutes" integer DEFAULT 60 NOT NULL,
    "drift_threshold_pct" double precision DEFAULT 6 NOT NULL,
    "target_notional_usd" double precision DEFAULT 0 NOT NULL,
    "current_notional_usd" double precision DEFAULT 0 NOT NULL,
    "kill_switch_reason" "text",
    "last_rebalanced_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."portfolio_baskets" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."portfolio_rebalance_events" (
    "id" "uuid" NOT NULL,
    "portfolio_basket_id" "uuid" NOT NULL,
    "trigger" character varying(32) DEFAULT 'manual'::character varying NOT NULL,
    "status" character varying(24) DEFAULT 'completed'::character varying NOT NULL,
    "summary_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."portfolio_rebalance_events" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."portfolio_risk_policies" (
    "id" "uuid" NOT NULL,
    "portfolio_basket_id" "uuid" NOT NULL,
    "max_drawdown_pct" double precision DEFAULT 18 NOT NULL,
    "max_member_drawdown_pct" double precision DEFAULT 22 NOT NULL,
    "min_trust_score" integer DEFAULT 55 NOT NULL,
    "max_active_members" integer DEFAULT 5 NOT NULL,
    "auto_pause_on_source_stale" boolean DEFAULT true NOT NULL,
    "kill_switch_on_breach" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."portfolio_risk_policies" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."strategy_activity_records" (
    "id" "uuid" NOT NULL,
    "vault_id" "uuid" NOT NULL,
    "action_type" character varying(48) NOT NULL,
    "summary" "text" NOT NULL,
    "metadata_json" "jsonb" DEFAULT '{}'::"jsonb" NOT NULL,
    "recorded_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."strategy_activity_records" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."users" (
    "id" "uuid" NOT NULL,
    "wallet_address" character varying(128) NOT NULL,
    "display_name" character varying(80),
    "auth_provider" character varying(32) DEFAULT 'privy'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."users" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."worker_leases" (
    "lease_key" character varying(255) NOT NULL,
    "owner_id" character varying(128) NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL
);


ALTER TABLE "public"."worker_leases" OWNER TO "postgres";


ALTER TABLE ONLY "public"."ai_job_runs"
    ADD CONSTRAINT "ai_job_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."audit_events"
    ADD CONSTRAINT "audit_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_action_claims"
    ADD CONSTRAINT "bot_action_claims_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_action_claims"
    ADD CONSTRAINT "bot_action_claims_runtime_id_idempotency_key_key" UNIQUE ("runtime_id", "idempotency_key");



ALTER TABLE ONLY "public"."bot_backtest_runs"
    ADD CONSTRAINT "bot_backtest_runs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_clones"
    ADD CONSTRAINT "bot_clones_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_copy_relationships"
    ADD CONSTRAINT "bot_copy_relationships_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_definitions"
    ADD CONSTRAINT "bot_definitions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_execution_events"
    ADD CONSTRAINT "bot_execution_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_invite_access"
    ADD CONSTRAINT "bot_invite_access_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_leaderboard_snapshots"
    ADD CONSTRAINT "bot_leaderboard_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_publish_snapshots"
    ADD CONSTRAINT "bot_publish_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_publishing_settings"
    ADD CONSTRAINT "bot_publishing_settings_bot_definition_id_key" UNIQUE ("bot_definition_id");



ALTER TABLE ONLY "public"."bot_publishing_settings"
    ADD CONSTRAINT "bot_publishing_settings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_runtime_snapshots"
    ADD CONSTRAINT "bot_runtime_snapshots_pkey" PRIMARY KEY ("runtime_id");



ALTER TABLE ONLY "public"."bot_runtimes"
    ADD CONSTRAINT "bot_runtimes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_strategy_versions"
    ADD CONSTRAINT "bot_strategy_versions_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_trade_closures"
    ADD CONSTRAINT "bot_trade_closures_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_trade_lots"
    ADD CONSTRAINT "bot_trade_lots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."bot_trade_sync_state"
    ADD CONSTRAINT "bot_trade_sync_state_pkey" PRIMARY KEY ("runtime_id");



ALTER TABLE ONLY "public"."copilot_conversations"
    ADD CONSTRAINT "copilot_conversations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."copilot_messages"
    ADD CONSTRAINT "copilot_messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."copy_execution_events"
    ADD CONSTRAINT "copy_execution_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."copy_relationships"
    ADD CONSTRAINT "copy_relationships_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."creator_marketplace_profiles"
    ADD CONSTRAINT "creator_marketplace_profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."creator_marketplace_profiles"
    ADD CONSTRAINT "creator_marketplace_profiles_slug_key" UNIQUE ("slug");



ALTER TABLE ONLY "public"."creator_marketplace_profiles"
    ADD CONSTRAINT "creator_marketplace_profiles_user_id_key" UNIQUE ("user_id");



ALTER TABLE ONLY "public"."featured_bots"
    ADD CONSTRAINT "featured_bots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."leaderboard_snapshots"
    ADD CONSTRAINT "leaderboard_snapshots_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."marketplace_creator_snapshots"
    ADD CONSTRAINT "marketplace_creator_snapshots_pkey" PRIMARY KEY ("creator_id");



ALTER TABLE ONLY "public"."marketplace_runtime_snapshots"
    ADD CONSTRAINT "marketplace_runtime_snapshots_pkey" PRIMARY KEY ("runtime_id");



ALTER TABLE ONLY "public"."pacifica_authorizations"
    ADD CONSTRAINT "pacifica_authorizations_account_address_key" UNIQUE ("account_address");



ALTER TABLE ONLY "public"."pacifica_authorizations"
    ADD CONSTRAINT "pacifica_authorizations_agent_wallet_address_key" UNIQUE ("agent_wallet_address");



ALTER TABLE ONLY "public"."pacifica_authorizations"
    ADD CONSTRAINT "pacifica_authorizations_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."pacifica_authorizations"
    ADD CONSTRAINT "pacifica_authorizations_user_id_key" UNIQUE ("user_id");



ALTER TABLE ONLY "public"."portfolio_allocation_members"
    ADD CONSTRAINT "portfolio_allocation_members_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."portfolio_baskets"
    ADD CONSTRAINT "portfolio_baskets_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."portfolio_rebalance_events"
    ADD CONSTRAINT "portfolio_rebalance_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."portfolio_risk_policies"
    ADD CONSTRAINT "portfolio_risk_policies_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."portfolio_risk_policies"
    ADD CONSTRAINT "portfolio_risk_policies_portfolio_basket_id_key" UNIQUE ("portfolio_basket_id");



ALTER TABLE ONLY "public"."strategy_activity_records"
    ADD CONSTRAINT "strategy_activity_records_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."users"
    ADD CONSTRAINT "users_wallet_address_key" UNIQUE ("wallet_address");



ALTER TABLE ONLY "public"."worker_leases"
    ADD CONSTRAINT "worker_leases_pkey" PRIMARY KEY ("lease_key");



CREATE INDEX "ix_ai_job_runs_conversation_created" ON "public"."ai_job_runs" USING "btree" ("conversation_id", "created_at" DESC);



CREATE INDEX "ix_ai_job_runs_status_created" ON "public"."ai_job_runs" USING "btree" ("status", "created_at" DESC);



CREATE INDEX "ix_ai_job_runs_wallet_created" ON "public"."ai_job_runs" USING "btree" ("wallet_address", "created_at" DESC);



CREATE INDEX "ix_audit_events_action" ON "public"."audit_events" USING "btree" ("action");



CREATE INDEX "ix_audit_events_user_created" ON "public"."audit_events" USING "btree" ("user_id", "created_at" DESC);



CREATE INDEX "ix_bot_action_claims_created_at" ON "public"."bot_action_claims" USING "btree" ("created_at");



CREATE INDEX "ix_bot_action_claims_runtime_id" ON "public"."bot_action_claims" USING "btree" ("runtime_id");



CREATE INDEX "ix_bot_backtest_runs_bot_definition_id" ON "public"."bot_backtest_runs" USING "btree" ("bot_definition_id");



CREATE INDEX "ix_bot_backtest_runs_completed_at" ON "public"."bot_backtest_runs" USING "btree" ("completed_at");



CREATE INDEX "ix_bot_backtest_runs_status" ON "public"."bot_backtest_runs" USING "btree" ("status");



CREATE INDEX "ix_bot_backtest_runs_user_id" ON "public"."bot_backtest_runs" USING "btree" ("user_id");



CREATE INDEX "ix_bot_backtest_runs_wallet_address" ON "public"."bot_backtest_runs" USING "btree" ("wallet_address");



CREATE INDEX "ix_bot_clones_created_by_user_id" ON "public"."bot_clones" USING "btree" ("created_by_user_id");



CREATE INDEX "ix_bot_clones_new_bot_definition_id" ON "public"."bot_clones" USING "btree" ("new_bot_definition_id");



CREATE INDEX "ix_bot_clones_source_bot_definition_id" ON "public"."bot_clones" USING "btree" ("source_bot_definition_id");



CREATE INDEX "ix_bot_copy_relationships_follower_user_id" ON "public"."bot_copy_relationships" USING "btree" ("follower_user_id");



CREATE INDEX "ix_bot_copy_relationships_follower_wallet_address" ON "public"."bot_copy_relationships" USING "btree" ("follower_wallet_address");



CREATE INDEX "ix_bot_copy_relationships_portfolio_basket_id" ON "public"."bot_copy_relationships" USING "btree" ("portfolio_basket_id");



CREATE INDEX "ix_bot_copy_relationships_source_runtime_id" ON "public"."bot_copy_relationships" USING "btree" ("source_runtime_id");



CREATE INDEX "ix_bot_copy_relationships_status" ON "public"."bot_copy_relationships" USING "btree" ("status");



CREATE INDEX "ix_bot_definitions_name" ON "public"."bot_definitions" USING "btree" ("name");



CREATE INDEX "ix_bot_definitions_user_id" ON "public"."bot_definitions" USING "btree" ("user_id");



CREATE INDEX "ix_bot_definitions_visibility" ON "public"."bot_definitions" USING "btree" ("visibility");



CREATE INDEX "ix_bot_definitions_wallet_address" ON "public"."bot_definitions" USING "btree" ("wallet_address");



CREATE INDEX "ix_bot_definitions_wallet_updated" ON "public"."bot_definitions" USING "btree" ("wallet_address", "updated_at" DESC);



CREATE INDEX "ix_bot_execution_events_created_at" ON "public"."bot_execution_events" USING "btree" ("created_at");



CREATE INDEX "ix_bot_execution_events_event_type" ON "public"."bot_execution_events" USING "btree" ("event_type");



CREATE INDEX "ix_bot_execution_events_runtime_created_at" ON "public"."bot_execution_events" USING "btree" ("runtime_id", "created_at" DESC);



CREATE INDEX "ix_bot_execution_events_runtime_decision_created" ON "public"."bot_execution_events" USING "btree" ("runtime_id", "decision_summary", "created_at" DESC);



CREATE INDEX "ix_bot_execution_events_runtime_id" ON "public"."bot_execution_events" USING "btree" ("runtime_id");



CREATE INDEX "ix_bot_execution_events_status" ON "public"."bot_execution_events" USING "btree" ("status");



CREATE UNIQUE INDEX "ix_bot_invite_access_unique_wallet_per_bot" ON "public"."bot_invite_access" USING "btree" ("bot_definition_id", "invited_wallet_address");



CREATE INDEX "ix_bot_invite_access_wallet_status" ON "public"."bot_invite_access" USING "btree" ("invited_wallet_address", "status");



CREATE INDEX "ix_bot_leaderboard_snapshots_captured_at" ON "public"."bot_leaderboard_snapshots" USING "btree" ("captured_at");



CREATE INDEX "ix_bot_leaderboard_snapshots_rank" ON "public"."bot_leaderboard_snapshots" USING "btree" ("rank");



CREATE INDEX "ix_bot_leaderboard_snapshots_runtime_id" ON "public"."bot_leaderboard_snapshots" USING "btree" ("runtime_id");



CREATE INDEX "ix_bot_publish_snapshots_bot_definition_id" ON "public"."bot_publish_snapshots" USING "btree" ("bot_definition_id");



CREATE INDEX "ix_bot_publish_snapshots_created_at" ON "public"."bot_publish_snapshots" USING "btree" ("created_at" DESC);



CREATE INDEX "ix_bot_publish_snapshots_strategy_version_id" ON "public"."bot_publish_snapshots" USING "btree" ("strategy_version_id");



CREATE UNIQUE INDEX "ix_bot_publishing_settings_bot_definition_id" ON "public"."bot_publishing_settings" USING "btree" ("bot_definition_id");



CREATE INDEX "ix_bot_publishing_settings_publish_state" ON "public"."bot_publishing_settings" USING "btree" ("publish_state");



CREATE INDEX "ix_bot_publishing_settings_user_id" ON "public"."bot_publishing_settings" USING "btree" ("user_id");



CREATE INDEX "ix_bot_runtime_snapshots_bot_wallet" ON "public"."bot_runtime_snapshots" USING "btree" ("bot_definition_id", "wallet_address", "last_computed_at" DESC);



CREATE INDEX "ix_bot_runtime_snapshots_wallet_runtime" ON "public"."bot_runtime_snapshots" USING "btree" ("wallet_address", "last_computed_at" DESC);



CREATE INDEX "ix_bot_runtimes_bot_definition_id" ON "public"."bot_runtimes" USING "btree" ("bot_definition_id");



CREATE INDEX "ix_bot_runtimes_bot_wallet" ON "public"."bot_runtimes" USING "btree" ("bot_definition_id", "wallet_address");



CREATE INDEX "ix_bot_runtimes_status" ON "public"."bot_runtimes" USING "btree" ("status");



CREATE INDEX "ix_bot_runtimes_user_id" ON "public"."bot_runtimes" USING "btree" ("user_id");



CREATE INDEX "ix_bot_runtimes_wallet_address" ON "public"."bot_runtimes" USING "btree" ("wallet_address");



CREATE INDEX "ix_bot_runtimes_wallet_status_updated" ON "public"."bot_runtimes" USING "btree" ("wallet_address", "status", "updated_at" DESC);



CREATE UNIQUE INDEX "ix_bot_strategy_versions_bot_definition_version" ON "public"."bot_strategy_versions" USING "btree" ("bot_definition_id", "version_number");



CREATE INDEX "ix_bot_strategy_versions_created_at" ON "public"."bot_strategy_versions" USING "btree" ("created_at" DESC);



CREATE INDEX "ix_bot_strategy_versions_created_by_user_id" ON "public"."bot_strategy_versions" USING "btree" ("created_by_user_id");



CREATE INDEX "ix_copilot_conversations_user_latest" ON "public"."copilot_conversations" USING "btree" ("user_id", "latest_message_at" DESC);



CREATE INDEX "ix_copilot_conversations_wallet_latest" ON "public"."copilot_conversations" USING "btree" ("wallet_address", "latest_message_at" DESC);



CREATE INDEX "ix_copilot_messages_conversation_created" ON "public"."copilot_messages" USING "btree" ("conversation_id", "created_at");



CREATE INDEX "ix_copy_execution_events_copy_relationship_id" ON "public"."copy_execution_events" USING "btree" ("copy_relationship_id");



CREATE INDEX "ix_copy_execution_events_mirrored_order_ref" ON "public"."copy_execution_events" USING "btree" ("mirrored_order_ref");



CREATE INDEX "ix_copy_execution_events_source_order_ref" ON "public"."copy_execution_events" USING "btree" ("source_order_ref");



CREATE INDEX "ix_copy_execution_events_status" ON "public"."copy_execution_events" USING "btree" ("status");



CREATE INDEX "ix_copy_execution_events_symbol" ON "public"."copy_execution_events" USING "btree" ("symbol");



CREATE INDEX "ix_copy_relationships_follower_user_id" ON "public"."copy_relationships" USING "btree" ("follower_user_id");



CREATE INDEX "ix_copy_relationships_source_user_id" ON "public"."copy_relationships" USING "btree" ("source_user_id");



CREATE INDEX "ix_copy_relationships_status" ON "public"."copy_relationships" USING "btree" ("status");



CREATE UNIQUE INDEX "ix_creator_marketplace_profiles_slug" ON "public"."creator_marketplace_profiles" USING "btree" ("slug");



CREATE UNIQUE INDEX "ix_creator_marketplace_profiles_user_id" ON "public"."creator_marketplace_profiles" USING "btree" ("user_id");



CREATE INDEX "ix_featured_bots_active_rank" ON "public"."featured_bots" USING "btree" ("active", "shelf_rank", "updated_at" DESC);



CREATE INDEX "ix_featured_bots_creator_profile_id" ON "public"."featured_bots" USING "btree" ("creator_profile_id");



CREATE UNIQUE INDEX "ix_featured_bots_unique_bot_collection" ON "public"."featured_bots" USING "btree" ("bot_definition_id", "collection_key");



CREATE INDEX "ix_leaderboard_snapshots_captured_at" ON "public"."leaderboard_snapshots" USING "btree" ("captured_at");



CREATE INDEX "ix_leaderboard_snapshots_league_id" ON "public"."leaderboard_snapshots" USING "btree" ("league_id");



CREATE INDEX "ix_leaderboard_snapshots_user_id" ON "public"."leaderboard_snapshots" USING "btree" ("user_id");



CREATE INDEX "ix_marketplace_creator_snapshots_reach" ON "public"."marketplace_creator_snapshots" USING "btree" ("marketplace_reach_score" DESC, "display_name");



CREATE INDEX "ix_marketplace_runtime_snapshots_rank" ON "public"."marketplace_runtime_snapshots" USING "btree" ("rank", "captured_at" DESC);



CREATE INDEX "ix_marketplace_runtime_snapshots_strategy_creator" ON "public"."marketplace_runtime_snapshots" USING "btree" ("strategy_type", "creator_id", "rank");



CREATE INDEX "ix_pacifica_authorizations_account_address" ON "public"."pacifica_authorizations" USING "btree" ("account_address");



CREATE INDEX "ix_pacifica_authorizations_agent_wallet_address" ON "public"."pacifica_authorizations" USING "btree" ("agent_wallet_address");



CREATE INDEX "ix_pacifica_authorizations_status" ON "public"."pacifica_authorizations" USING "btree" ("status");



CREATE INDEX "ix_portfolio_allocation_members_portfolio_basket_id" ON "public"."portfolio_allocation_members" USING "btree" ("portfolio_basket_id");



CREATE INDEX "ix_portfolio_allocation_members_source_runtime_id" ON "public"."portfolio_allocation_members" USING "btree" ("source_runtime_id");



CREATE UNIQUE INDEX "ix_portfolio_allocation_members_unique_runtime_per_basket" ON "public"."portfolio_allocation_members" USING "btree" ("portfolio_basket_id", "source_runtime_id");



CREATE INDEX "ix_portfolio_baskets_owner_user_id" ON "public"."portfolio_baskets" USING "btree" ("owner_user_id");



CREATE INDEX "ix_portfolio_baskets_status" ON "public"."portfolio_baskets" USING "btree" ("status");



CREATE INDEX "ix_portfolio_baskets_wallet_address" ON "public"."portfolio_baskets" USING "btree" ("wallet_address");



CREATE INDEX "ix_portfolio_rebalance_events_created_at" ON "public"."portfolio_rebalance_events" USING "btree" ("created_at" DESC);



CREATE INDEX "ix_portfolio_rebalance_events_portfolio_basket_id" ON "public"."portfolio_rebalance_events" USING "btree" ("portfolio_basket_id");



CREATE INDEX "ix_strategy_activity_records_action_type" ON "public"."strategy_activity_records" USING "btree" ("action_type");



CREATE INDEX "ix_strategy_activity_records_recorded_at" ON "public"."strategy_activity_records" USING "btree" ("recorded_at");



CREATE INDEX "ix_strategy_activity_records_vault_id" ON "public"."strategy_activity_records" USING "btree" ("vault_id");



CREATE INDEX "ix_users_wallet_address" ON "public"."users" USING "btree" ("wallet_address");



CREATE INDEX "ix_worker_leases_expires_at" ON "public"."worker_leases" USING "btree" ("expires_at");



CREATE INDEX "worker_leases_expires_at_idx" ON "public"."worker_leases" USING "btree" ("expires_at");



ALTER TABLE ONLY "public"."ai_job_runs"
    ADD CONSTRAINT "ai_job_runs_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."copilot_conversations"("id");



ALTER TABLE ONLY "public"."audit_events"
    ADD CONSTRAINT "audit_events_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."bot_action_claims"
    ADD CONSTRAINT "bot_action_claims_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_backtest_runs"
    ADD CONSTRAINT "bot_backtest_runs_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_backtest_runs"
    ADD CONSTRAINT "bot_backtest_runs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_clones"
    ADD CONSTRAINT "bot_clones_created_by_user_id_fkey" FOREIGN KEY ("created_by_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_clones"
    ADD CONSTRAINT "bot_clones_new_bot_definition_id_fkey" FOREIGN KEY ("new_bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_clones"
    ADD CONSTRAINT "bot_clones_source_bot_definition_id_fkey" FOREIGN KEY ("source_bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_copy_relationships"
    ADD CONSTRAINT "bot_copy_relationships_follower_user_id_fkey" FOREIGN KEY ("follower_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_copy_relationships"
    ADD CONSTRAINT "bot_copy_relationships_source_runtime_id_fkey" FOREIGN KEY ("source_runtime_id") REFERENCES "public"."bot_runtimes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_definitions"
    ADD CONSTRAINT "bot_definitions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_execution_events"
    ADD CONSTRAINT "bot_execution_events_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_invite_access"
    ADD CONSTRAINT "bot_invite_access_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_invite_access"
    ADD CONSTRAINT "bot_invite_access_invited_by_user_id_fkey" FOREIGN KEY ("invited_by_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_leaderboard_snapshots"
    ADD CONSTRAINT "bot_leaderboard_snapshots_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_publish_snapshots"
    ADD CONSTRAINT "bot_publish_snapshots_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_publish_snapshots"
    ADD CONSTRAINT "bot_publish_snapshots_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."bot_publish_snapshots"
    ADD CONSTRAINT "bot_publish_snapshots_strategy_version_id_fkey" FOREIGN KEY ("strategy_version_id") REFERENCES "public"."bot_strategy_versions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_publishing_settings"
    ADD CONSTRAINT "bot_publishing_settings_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_publishing_settings"
    ADD CONSTRAINT "bot_publishing_settings_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_runtime_snapshots"
    ADD CONSTRAINT "bot_runtime_snapshots_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id");



ALTER TABLE ONLY "public"."bot_runtime_snapshots"
    ADD CONSTRAINT "bot_runtime_snapshots_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id");



ALTER TABLE ONLY "public"."bot_runtime_snapshots"
    ADD CONSTRAINT "bot_runtime_snapshots_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."bot_runtimes"
    ADD CONSTRAINT "bot_runtimes_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_runtimes"
    ADD CONSTRAINT "bot_runtimes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_strategy_versions"
    ADD CONSTRAINT "bot_strategy_versions_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_strategy_versions"
    ADD CONSTRAINT "bot_strategy_versions_created_by_user_id_fkey" FOREIGN KEY ("created_by_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."bot_trade_closures"
    ADD CONSTRAINT "bot_trade_closures_lot_id_fkey" FOREIGN KEY ("lot_id") REFERENCES "public"."bot_trade_lots"("id");



ALTER TABLE ONLY "public"."bot_trade_closures"
    ADD CONSTRAINT "bot_trade_closures_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id");



ALTER TABLE ONLY "public"."bot_trade_lots"
    ADD CONSTRAINT "bot_trade_lots_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id");



ALTER TABLE ONLY "public"."bot_trade_sync_state"
    ADD CONSTRAINT "bot_trade_sync_state_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id");



ALTER TABLE ONLY "public"."copilot_conversations"
    ADD CONSTRAINT "copilot_conversations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."copilot_messages"
    ADD CONSTRAINT "copilot_messages_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "public"."copilot_conversations"("id");



ALTER TABLE ONLY "public"."copy_execution_events"
    ADD CONSTRAINT "copy_execution_events_copy_relationship_id_fkey" FOREIGN KEY ("copy_relationship_id") REFERENCES "public"."copy_relationships"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."copy_relationships"
    ADD CONSTRAINT "copy_relationships_follower_user_id_fkey" FOREIGN KEY ("follower_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."copy_relationships"
    ADD CONSTRAINT "copy_relationships_source_user_id_fkey" FOREIGN KEY ("source_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."creator_marketplace_profiles"
    ADD CONSTRAINT "creator_marketplace_profiles_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."featured_bots"
    ADD CONSTRAINT "featured_bots_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."featured_bots"
    ADD CONSTRAINT "featured_bots_creator_profile_id_fkey" FOREIGN KEY ("creator_profile_id") REFERENCES "public"."creator_marketplace_profiles"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."leaderboard_snapshots"
    ADD CONSTRAINT "leaderboard_snapshots_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."marketplace_creator_snapshots"
    ADD CONSTRAINT "marketplace_creator_snapshots_creator_id_fkey" FOREIGN KEY ("creator_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."marketplace_runtime_snapshots"
    ADD CONSTRAINT "marketplace_runtime_snapshots_bot_definition_id_fkey" FOREIGN KEY ("bot_definition_id") REFERENCES "public"."bot_definitions"("id");



ALTER TABLE ONLY "public"."marketplace_runtime_snapshots"
    ADD CONSTRAINT "marketplace_runtime_snapshots_creator_id_fkey" FOREIGN KEY ("creator_id") REFERENCES "public"."users"("id");



ALTER TABLE ONLY "public"."marketplace_runtime_snapshots"
    ADD CONSTRAINT "marketplace_runtime_snapshots_runtime_id_fkey" FOREIGN KEY ("runtime_id") REFERENCES "public"."bot_runtimes"("id");



ALTER TABLE ONLY "public"."pacifica_authorizations"
    ADD CONSTRAINT "pacifica_authorizations_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."portfolio_allocation_members"
    ADD CONSTRAINT "portfolio_allocation_members_portfolio_basket_id_fkey" FOREIGN KEY ("portfolio_basket_id") REFERENCES "public"."portfolio_baskets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."portfolio_allocation_members"
    ADD CONSTRAINT "portfolio_allocation_members_relationship_id_fkey" FOREIGN KEY ("relationship_id") REFERENCES "public"."bot_copy_relationships"("id") ON DELETE SET NULL;



ALTER TABLE ONLY "public"."portfolio_allocation_members"
    ADD CONSTRAINT "portfolio_allocation_members_source_runtime_id_fkey" FOREIGN KEY ("source_runtime_id") REFERENCES "public"."bot_runtimes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."portfolio_baskets"
    ADD CONSTRAINT "portfolio_baskets_owner_user_id_fkey" FOREIGN KEY ("owner_user_id") REFERENCES "public"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."portfolio_rebalance_events"
    ADD CONSTRAINT "portfolio_rebalance_events_portfolio_basket_id_fkey" FOREIGN KEY ("portfolio_basket_id") REFERENCES "public"."portfolio_baskets"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."portfolio_risk_policies"
    ADD CONSTRAINT "portfolio_risk_policies_portfolio_basket_id_fkey" FOREIGN KEY ("portfolio_basket_id") REFERENCES "public"."portfolio_baskets"("id") ON DELETE CASCADE;





ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";


GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";








































































































































































GRANT ALL ON TABLE "public"."ai_job_runs" TO "anon";
GRANT ALL ON TABLE "public"."ai_job_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."ai_job_runs" TO "service_role";



GRANT ALL ON TABLE "public"."audit_events" TO "anon";
GRANT ALL ON TABLE "public"."audit_events" TO "authenticated";
GRANT ALL ON TABLE "public"."audit_events" TO "service_role";



GRANT ALL ON TABLE "public"."bot_action_claims" TO "anon";
GRANT ALL ON TABLE "public"."bot_action_claims" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_action_claims" TO "service_role";



GRANT ALL ON TABLE "public"."bot_backtest_runs" TO "anon";
GRANT ALL ON TABLE "public"."bot_backtest_runs" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_backtest_runs" TO "service_role";



GRANT ALL ON TABLE "public"."bot_clones" TO "anon";
GRANT ALL ON TABLE "public"."bot_clones" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_clones" TO "service_role";



GRANT ALL ON TABLE "public"."bot_copy_relationships" TO "anon";
GRANT ALL ON TABLE "public"."bot_copy_relationships" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_copy_relationships" TO "service_role";



GRANT ALL ON TABLE "public"."bot_definitions" TO "anon";
GRANT ALL ON TABLE "public"."bot_definitions" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_definitions" TO "service_role";



GRANT ALL ON TABLE "public"."bot_execution_events" TO "anon";
GRANT ALL ON TABLE "public"."bot_execution_events" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_execution_events" TO "service_role";



GRANT ALL ON TABLE "public"."bot_invite_access" TO "anon";
GRANT ALL ON TABLE "public"."bot_invite_access" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_invite_access" TO "service_role";



GRANT ALL ON TABLE "public"."bot_leaderboard_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."bot_leaderboard_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_leaderboard_snapshots" TO "service_role";



GRANT ALL ON TABLE "public"."bot_publish_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."bot_publish_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_publish_snapshots" TO "service_role";



GRANT ALL ON TABLE "public"."bot_publishing_settings" TO "anon";
GRANT ALL ON TABLE "public"."bot_publishing_settings" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_publishing_settings" TO "service_role";



GRANT ALL ON TABLE "public"."bot_runtime_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."bot_runtime_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_runtime_snapshots" TO "service_role";



GRANT ALL ON TABLE "public"."bot_runtimes" TO "anon";
GRANT ALL ON TABLE "public"."bot_runtimes" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_runtimes" TO "service_role";



GRANT ALL ON TABLE "public"."bot_strategy_versions" TO "anon";
GRANT ALL ON TABLE "public"."bot_strategy_versions" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_strategy_versions" TO "service_role";



GRANT ALL ON TABLE "public"."bot_trade_closures" TO "anon";
GRANT ALL ON TABLE "public"."bot_trade_closures" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_trade_closures" TO "service_role";



GRANT ALL ON TABLE "public"."bot_trade_lots" TO "anon";
GRANT ALL ON TABLE "public"."bot_trade_lots" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_trade_lots" TO "service_role";



GRANT ALL ON TABLE "public"."bot_trade_sync_state" TO "anon";
GRANT ALL ON TABLE "public"."bot_trade_sync_state" TO "authenticated";
GRANT ALL ON TABLE "public"."bot_trade_sync_state" TO "service_role";



GRANT ALL ON TABLE "public"."copilot_conversations" TO "anon";
GRANT ALL ON TABLE "public"."copilot_conversations" TO "authenticated";
GRANT ALL ON TABLE "public"."copilot_conversations" TO "service_role";



GRANT ALL ON TABLE "public"."copilot_messages" TO "anon";
GRANT ALL ON TABLE "public"."copilot_messages" TO "authenticated";
GRANT ALL ON TABLE "public"."copilot_messages" TO "service_role";



GRANT ALL ON TABLE "public"."copy_execution_events" TO "anon";
GRANT ALL ON TABLE "public"."copy_execution_events" TO "authenticated";
GRANT ALL ON TABLE "public"."copy_execution_events" TO "service_role";



GRANT ALL ON TABLE "public"."copy_relationships" TO "anon";
GRANT ALL ON TABLE "public"."copy_relationships" TO "authenticated";
GRANT ALL ON TABLE "public"."copy_relationships" TO "service_role";



GRANT ALL ON TABLE "public"."creator_marketplace_profiles" TO "anon";
GRANT ALL ON TABLE "public"."creator_marketplace_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."creator_marketplace_profiles" TO "service_role";



GRANT ALL ON TABLE "public"."featured_bots" TO "anon";
GRANT ALL ON TABLE "public"."featured_bots" TO "authenticated";
GRANT ALL ON TABLE "public"."featured_bots" TO "service_role";



GRANT ALL ON TABLE "public"."leaderboard_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."leaderboard_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."leaderboard_snapshots" TO "service_role";



GRANT ALL ON TABLE "public"."marketplace_creator_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."marketplace_creator_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."marketplace_creator_snapshots" TO "service_role";



GRANT ALL ON TABLE "public"."marketplace_runtime_snapshots" TO "anon";
GRANT ALL ON TABLE "public"."marketplace_runtime_snapshots" TO "authenticated";
GRANT ALL ON TABLE "public"."marketplace_runtime_snapshots" TO "service_role";



GRANT ALL ON TABLE "public"."pacifica_authorizations" TO "anon";
GRANT ALL ON TABLE "public"."pacifica_authorizations" TO "authenticated";
GRANT ALL ON TABLE "public"."pacifica_authorizations" TO "service_role";



GRANT ALL ON TABLE "public"."portfolio_allocation_members" TO "anon";
GRANT ALL ON TABLE "public"."portfolio_allocation_members" TO "authenticated";
GRANT ALL ON TABLE "public"."portfolio_allocation_members" TO "service_role";



GRANT ALL ON TABLE "public"."portfolio_baskets" TO "anon";
GRANT ALL ON TABLE "public"."portfolio_baskets" TO "authenticated";
GRANT ALL ON TABLE "public"."portfolio_baskets" TO "service_role";



GRANT ALL ON TABLE "public"."portfolio_rebalance_events" TO "anon";
GRANT ALL ON TABLE "public"."portfolio_rebalance_events" TO "authenticated";
GRANT ALL ON TABLE "public"."portfolio_rebalance_events" TO "service_role";



GRANT ALL ON TABLE "public"."portfolio_risk_policies" TO "anon";
GRANT ALL ON TABLE "public"."portfolio_risk_policies" TO "authenticated";
GRANT ALL ON TABLE "public"."portfolio_risk_policies" TO "service_role";



GRANT ALL ON TABLE "public"."strategy_activity_records" TO "anon";
GRANT ALL ON TABLE "public"."strategy_activity_records" TO "authenticated";
GRANT ALL ON TABLE "public"."strategy_activity_records" TO "service_role";



GRANT ALL ON TABLE "public"."users" TO "anon";
GRANT ALL ON TABLE "public"."users" TO "authenticated";
GRANT ALL ON TABLE "public"."users" TO "service_role";



GRANT ALL ON TABLE "public"."worker_leases" TO "anon";
GRANT ALL ON TABLE "public"."worker_leases" TO "authenticated";
GRANT ALL ON TABLE "public"."worker_leases" TO "service_role";









ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";































