-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.ai_job_runs (
  id uuid NOT NULL,
  job_type character varying NOT NULL,
  status character varying NOT NULL DEFAULT 'queued'::character varying,
  wallet_address character varying,
  conversation_id uuid,
  request_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_detail text,
  started_at timestamp with time zone,
  completed_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT ai_job_runs_pkey PRIMARY KEY (id),
  CONSTRAINT ai_job_runs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.copilot_conversations(id)
);
CREATE TABLE public.audit_events (
  id uuid NOT NULL,
  user_id uuid,
  action character varying NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT audit_events_pkey PRIMARY KEY (id),
  CONSTRAINT audit_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_action_claims (
  id uuid NOT NULL,
  runtime_id uuid NOT NULL,
  idempotency_key character varying NOT NULL,
  claimed_by character varying NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_action_claims_pkey PRIMARY KEY (id),
  CONSTRAINT bot_action_claims_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.bot_backtest_runs (
  id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  user_id uuid NOT NULL,
  wallet_address character varying NOT NULL,
  bot_name_snapshot character varying NOT NULL,
  rules_snapshot_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  interval character varying NOT NULL,
  start_time bigint NOT NULL,
  end_time bigint NOT NULL,
  initial_capital_usd double precision NOT NULL DEFAULT 0,
  execution_model character varying NOT NULL DEFAULT 'candle_close_v2'::character varying,
  pnl_total double precision NOT NULL DEFAULT 0,
  pnl_total_pct double precision NOT NULL DEFAULT 0,
  max_drawdown_pct double precision NOT NULL DEFAULT 0,
  win_rate double precision NOT NULL DEFAULT 0,
  trade_count integer NOT NULL DEFAULT 0,
  status character varying NOT NULL DEFAULT 'completed'::character varying,
  result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  completed_at timestamp with time zone,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  market_scope_snapshot character varying NOT NULL DEFAULT 'Pacifica perpetuals'::character varying,
  strategy_type_snapshot character varying NOT NULL DEFAULT 'rules'::character varying,
  assumption_config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  failure_reason text,
  CONSTRAINT bot_backtest_runs_pkey PRIMARY KEY (id),
  CONSTRAINT bot_backtest_runs_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_backtest_runs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_clones (
  id uuid NOT NULL,
  source_bot_definition_id uuid NOT NULL,
  new_bot_definition_id uuid NOT NULL,
  created_by_user_id uuid NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_clones_pkey PRIMARY KEY (id),
  CONSTRAINT bot_clones_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id),
  CONSTRAINT bot_clones_new_bot_definition_id_fkey FOREIGN KEY (new_bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_clones_source_bot_definition_id_fkey FOREIGN KEY (source_bot_definition_id) REFERENCES public.bot_definitions(id)
);
CREATE TABLE public.bot_copy_execution_events (
  id uuid NOT NULL,
  relationship_id uuid NOT NULL,
  source_runtime_id uuid NOT NULL,
  source_event_id uuid NOT NULL,
  follower_user_id uuid NOT NULL,
  follower_wallet_address character varying NOT NULL,
  symbol character varying NOT NULL DEFAULT ''::character varying,
  side character varying,
  position_side character varying,
  action_type character varying NOT NULL,
  reduce_only boolean NOT NULL DEFAULT false,
  requested_quantity double precision NOT NULL DEFAULT 0,
  copied_quantity double precision NOT NULL DEFAULT 0,
  reference_price double precision NOT NULL DEFAULT 0,
  notional_estimate_usd double precision NOT NULL DEFAULT 0,
  request_id character varying,
  client_order_id character varying,
  status character varying NOT NULL DEFAULT 'queued'::character varying,
  error_reason text,
  result_payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_copy_execution_events_pkey PRIMARY KEY (id),
  CONSTRAINT bot_copy_execution_events_relationship_id_fkey FOREIGN KEY (relationship_id) REFERENCES public.bot_copy_relationships(id),
  CONSTRAINT bot_copy_execution_events_source_runtime_id_fkey FOREIGN KEY (source_runtime_id) REFERENCES public.bot_runtimes(id),
  CONSTRAINT bot_copy_execution_events_source_event_id_fkey FOREIGN KEY (source_event_id) REFERENCES public.bot_execution_events(id),
  CONSTRAINT bot_copy_execution_events_follower_user_id_fkey FOREIGN KEY (follower_user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_copy_relationships (
  id uuid NOT NULL,
  source_runtime_id uuid NOT NULL,
  follower_user_id uuid NOT NULL,
  follower_wallet_address character varying NOT NULL,
  mode character varying NOT NULL DEFAULT 'mirror'::character varying,
  scale_bps integer NOT NULL DEFAULT 10000,
  status character varying NOT NULL DEFAULT 'active'::character varying,
  risk_ack_version character varying NOT NULL DEFAULT 'v1'::character varying,
  confirmed_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  portfolio_basket_id uuid,
  max_notional_usd double precision,
  CONSTRAINT bot_copy_relationships_pkey PRIMARY KEY (id),
  CONSTRAINT bot_copy_relationships_follower_user_id_fkey FOREIGN KEY (follower_user_id) REFERENCES public.users(id),
  CONSTRAINT bot_copy_relationships_source_runtime_id_fkey FOREIGN KEY (source_runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.bot_definitions (
  id uuid NOT NULL,
  user_id uuid NOT NULL,
  wallet_address character varying NOT NULL,
  name character varying NOT NULL,
  description text NOT NULL DEFAULT ''::text,
  visibility character varying NOT NULL DEFAULT 'private'::character varying,
  market_scope character varying NOT NULL DEFAULT 'Pacifica perpetuals'::character varying,
  strategy_type character varying NOT NULL DEFAULT 'rules'::character varying,
  authoring_mode character varying NOT NULL DEFAULT 'visual'::character varying,
  rules_version integer NOT NULL DEFAULT 1,
  rules_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  sdk_bundle_ref character varying,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_definitions_pkey PRIMARY KEY (id),
  CONSTRAINT bot_definitions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_execution_events (
  id uuid NOT NULL,
  runtime_id uuid NOT NULL,
  event_type character varying NOT NULL,
  decision_summary text NOT NULL DEFAULT ''::text,
  request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status character varying NOT NULL DEFAULT 'pending'::character varying,
  error_reason text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_execution_events_pkey PRIMARY KEY (id),
  CONSTRAINT bot_execution_events_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.bot_invite_access (
  id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  invited_wallet_address character varying NOT NULL,
  invited_by_user_id uuid NOT NULL,
  status character varying NOT NULL DEFAULT 'active'::character varying,
  note text NOT NULL DEFAULT ''::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_invite_access_pkey PRIMARY KEY (id),
  CONSTRAINT bot_invite_access_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_invite_access_invited_by_user_id_fkey FOREIGN KEY (invited_by_user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_leaderboard_snapshots (
  id uuid NOT NULL,
  runtime_id uuid NOT NULL,
  rank integer NOT NULL DEFAULT 0,
  pnl_total double precision NOT NULL DEFAULT 0,
  pnl_unrealized double precision NOT NULL DEFAULT 0,
  win_streak integer NOT NULL DEFAULT 0,
  drawdown double precision NOT NULL DEFAULT 0,
  captured_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_leaderboard_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT bot_leaderboard_snapshots_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.bot_publish_snapshots (
  id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  strategy_version_id uuid NOT NULL,
  runtime_id uuid,
  visibility_snapshot character varying NOT NULL DEFAULT 'public'::character varying,
  publish_state character varying NOT NULL DEFAULT 'published'::character varying,
  summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_publish_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT bot_publish_snapshots_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_publish_snapshots_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id),
  CONSTRAINT bot_publish_snapshots_strategy_version_id_fkey FOREIGN KEY (strategy_version_id) REFERENCES public.bot_strategy_versions(id)
);
CREATE TABLE public.bot_publishing_settings (
  id uuid NOT NULL,
  bot_definition_id uuid NOT NULL UNIQUE,
  user_id uuid NOT NULL,
  visibility character varying NOT NULL DEFAULT 'private'::character varying,
  access_mode character varying NOT NULL DEFAULT 'private'::character varying,
  publish_state character varying NOT NULL DEFAULT 'draft'::character varying,
  listed_at timestamp with time zone,
  hero_headline text NOT NULL DEFAULT ''::text,
  access_note text NOT NULL DEFAULT ''::text,
  featured_collection_key character varying,
  featured_collection_title character varying,
  featured_rank integer NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_publishing_settings_pkey PRIMARY KEY (id),
  CONSTRAINT bot_publishing_settings_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_publishing_settings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_runtime_snapshots (
  runtime_id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  user_id uuid,
  wallet_address character varying NOT NULL,
  status character varying NOT NULL DEFAULT 'draft'::character varying,
  mode character varying NOT NULL DEFAULT 'live'::character varying,
  health_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  performance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_runtime_updated_at timestamp with time zone,
  last_computed_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_runtime_snapshots_pkey PRIMARY KEY (runtime_id),
  CONSTRAINT bot_runtime_snapshots_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_runtime_snapshots_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id),
  CONSTRAINT bot_runtime_snapshots_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_runtimes (
  id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  user_id uuid NOT NULL,
  wallet_address character varying NOT NULL,
  status character varying NOT NULL DEFAULT 'draft'::character varying,
  mode character varying NOT NULL DEFAULT 'live'::character varying,
  risk_policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  deployed_at timestamp with time zone,
  stopped_at timestamp with time zone,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_runtimes_pkey PRIMARY KEY (id),
  CONSTRAINT bot_runtimes_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_runtimes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_strategy_versions (
  id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  created_by_user_id uuid NOT NULL,
  version_number integer NOT NULL DEFAULT 1,
  change_kind character varying NOT NULL DEFAULT 'revision'::character varying,
  visibility_snapshot character varying NOT NULL DEFAULT 'private'::character varying,
  name_snapshot character varying NOT NULL,
  description_snapshot text NOT NULL DEFAULT ''::text,
  market_scope_snapshot character varying NOT NULL DEFAULT 'Pacifica perpetuals'::character varying,
  strategy_type_snapshot character varying NOT NULL DEFAULT 'rules'::character varying,
  authoring_mode_snapshot character varying NOT NULL DEFAULT 'visual'::character varying,
  rules_version_snapshot integer NOT NULL DEFAULT 1,
  rules_json_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_public_release boolean NOT NULL DEFAULT false,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_strategy_versions_pkey PRIMARY KEY (id),
  CONSTRAINT bot_strategy_versions_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_strategy_versions_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id)
);
CREATE TABLE public.bot_trade_closures (
  id uuid NOT NULL,
  runtime_id uuid NOT NULL,
  lot_id uuid NOT NULL,
  symbol character varying NOT NULL,
  side character varying NOT NULL,
  closed_at timestamp with time zone NOT NULL,
  source character varying NOT NULL,
  source_event_id uuid,
  source_order_id character varying,
  source_history_id bigint,
  quantity_closed double precision NOT NULL DEFAULT 0,
  entry_price double precision NOT NULL DEFAULT 0,
  exit_price double precision NOT NULL DEFAULT 0,
  realized_pnl double precision NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_trade_closures_pkey PRIMARY KEY (id),
  CONSTRAINT bot_trade_closures_lot_id_fkey FOREIGN KEY (lot_id) REFERENCES public.bot_trade_lots(id),
  CONSTRAINT bot_trade_closures_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.bot_trade_lots (
  id uuid NOT NULL,
  runtime_id uuid NOT NULL,
  symbol character varying NOT NULL,
  side character varying NOT NULL,
  opened_at timestamp with time zone NOT NULL,
  source character varying NOT NULL DEFAULT 'bot'::character varying,
  source_event_id uuid,
  source_order_id character varying,
  source_history_id bigint,
  entry_price double precision NOT NULL DEFAULT 0,
  quantity_opened double precision NOT NULL DEFAULT 0,
  quantity_remaining double precision NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_trade_lots_pkey PRIMARY KEY (id),
  CONSTRAINT bot_trade_lots_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.bot_trade_sync_state (
  runtime_id uuid NOT NULL,
  synced_at timestamp with time zone NOT NULL DEFAULT now(),
  execution_events_count integer NOT NULL DEFAULT 0,
  position_history_count integer NOT NULL DEFAULT 0,
  last_execution_at timestamp with time zone,
  last_history_at timestamp with time zone,
  last_error text,
  CONSTRAINT bot_trade_sync_state_pkey PRIMARY KEY (runtime_id),
  CONSTRAINT bot_trade_sync_state_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.copilot_conversations (
  id uuid NOT NULL,
  user_id uuid NOT NULL,
  wallet_address character varying NOT NULL,
  title character varying NOT NULL DEFAULT 'New conversation'::character varying,
  context_summary text NOT NULL DEFAULT ''::text,
  summary_message_count integer NOT NULL DEFAULT 0,
  summary_token_estimate integer NOT NULL DEFAULT 0,
  message_count integer NOT NULL DEFAULT 0,
  last_message_preview text NOT NULL DEFAULT ''::text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  latest_message_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT copilot_conversations_pkey PRIMARY KEY (id),
  CONSTRAINT copilot_conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.copilot_messages (
  id uuid NOT NULL,
  conversation_id uuid NOT NULL,
  role character varying NOT NULL,
  content text NOT NULL DEFAULT ''::text,
  tool_calls_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  follow_ups_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  provider character varying,
  token_estimate integer NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT copilot_messages_pkey PRIMARY KEY (id),
  CONSTRAINT copilot_messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.copilot_conversations(id)
);
CREATE TABLE public.copy_execution_events (
  id uuid NOT NULL,
  copy_relationship_id uuid NOT NULL,
  source_order_ref character varying NOT NULL,
  mirrored_order_ref character varying NOT NULL,
  symbol character varying NOT NULL,
  side character varying NOT NULL,
  size_source double precision NOT NULL DEFAULT 0,
  size_mirrored double precision NOT NULL DEFAULT 0,
  status character varying NOT NULL DEFAULT 'queued'::character varying,
  error_reason character varying,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT copy_execution_events_pkey PRIMARY KEY (id),
  CONSTRAINT copy_execution_events_copy_relationship_id_fkey FOREIGN KEY (copy_relationship_id) REFERENCES public.copy_relationships(id)
);
CREATE TABLE public.copy_relationships (
  id uuid NOT NULL,
  follower_user_id uuid NOT NULL,
  source_user_id uuid NOT NULL,
  scale_bps integer NOT NULL DEFAULT 10000,
  status character varying NOT NULL DEFAULT 'active'::character varying,
  risk_ack_version character varying NOT NULL DEFAULT 'v1'::character varying,
  max_notional_usd double precision,
  confirmed_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT copy_relationships_pkey PRIMARY KEY (id),
  CONSTRAINT copy_relationships_follower_user_id_fkey FOREIGN KEY (follower_user_id) REFERENCES public.users(id),
  CONSTRAINT copy_relationships_source_user_id_fkey FOREIGN KEY (source_user_id) REFERENCES public.users(id)
);
CREATE TABLE public.creator_marketplace_profiles (
  id uuid NOT NULL,
  user_id uuid NOT NULL UNIQUE,
  display_name character varying NOT NULL,
  slug character varying NOT NULL UNIQUE,
  headline text NOT NULL DEFAULT ''::text,
  bio text NOT NULL DEFAULT ''::text,
  social_links_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  featured_collection_title character varying NOT NULL DEFAULT 'Featured strategies'::character varying,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT creator_marketplace_profiles_pkey PRIMARY KEY (id),
  CONSTRAINT creator_marketplace_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.featured_bots (
  id uuid NOT NULL,
  creator_profile_id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  collection_key character varying NOT NULL DEFAULT 'featured'::character varying,
  collection_title character varying NOT NULL DEFAULT 'Featured strategies'::character varying,
  shelf_rank integer NOT NULL DEFAULT 0,
  featured_reason text NOT NULL DEFAULT ''::text,
  active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT featured_bots_pkey PRIMARY KEY (id),
  CONSTRAINT featured_bots_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT featured_bots_creator_profile_id_fkey FOREIGN KEY (creator_profile_id) REFERENCES public.creator_marketplace_profiles(id)
);
CREATE TABLE public.leaderboard_snapshots (
  id uuid NOT NULL,
  league_id uuid NOT NULL,
  user_id uuid NOT NULL,
  rank integer NOT NULL,
  unrealized_pnl double precision NOT NULL DEFAULT 0,
  realized_pnl double precision NOT NULL DEFAULT 0,
  win_streak integer NOT NULL DEFAULT 0,
  captured_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT leaderboard_snapshots_pkey PRIMARY KEY (id),
  CONSTRAINT leaderboard_snapshots_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.marketplace_creator_snapshots (
  creator_id uuid NOT NULL,
  display_name character varying NOT NULL DEFAULT ''::character varying,
  marketplace_reach_score integer NOT NULL DEFAULT 0,
  highlight_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  profile_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_computed_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT marketplace_creator_snapshots_pkey PRIMARY KEY (creator_id),
  CONSTRAINT marketplace_creator_snapshots_creator_id_fkey FOREIGN KEY (creator_id) REFERENCES public.users(id)
);
CREATE TABLE public.marketplace_runtime_snapshots (
  runtime_id uuid NOT NULL,
  bot_definition_id uuid NOT NULL,
  creator_id uuid NOT NULL,
  strategy_type character varying NOT NULL DEFAULT ''::character varying,
  rank integer NOT NULL DEFAULT 0,
  row_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  captured_at timestamp with time zone,
  last_computed_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT marketplace_runtime_snapshots_pkey PRIMARY KEY (runtime_id),
  CONSTRAINT marketplace_runtime_snapshots_bot_definition_id_fkey FOREIGN KEY (bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT marketplace_runtime_snapshots_creator_id_fkey FOREIGN KEY (creator_id) REFERENCES public.users(id),
  CONSTRAINT marketplace_runtime_snapshots_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.pacifica_authorizations (
  id uuid NOT NULL,
  user_id uuid NOT NULL UNIQUE,
  account_address character varying NOT NULL UNIQUE,
  agent_wallet_address character varying NOT NULL UNIQUE,
  encrypted_agent_private_key text NOT NULL,
  builder_code character varying,
  max_fee_rate character varying NOT NULL DEFAULT '0.001'::character varying,
  status character varying NOT NULL DEFAULT 'draft'::character varying,
  builder_approval_message text,
  builder_approval_timestamp bigint,
  builder_approval_expiry_window integer,
  builder_approval_signature text,
  builder_approved_at timestamp with time zone,
  bind_agent_message text NOT NULL,
  bind_agent_timestamp bigint NOT NULL,
  bind_agent_expiry_window integer NOT NULL,
  bind_agent_signature text,
  agent_bound_at timestamp with time zone,
  last_error character varying,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT pacifica_authorizations_pkey PRIMARY KEY (id),
  CONSTRAINT pacifica_authorizations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.portfolio_allocation_members (
  id uuid NOT NULL,
  portfolio_basket_id uuid NOT NULL,
  source_runtime_id uuid NOT NULL,
  target_weight_pct double precision NOT NULL DEFAULT 0,
  target_notional_usd double precision NOT NULL DEFAULT 0,
  max_scale_bps integer NOT NULL DEFAULT 20000,
  target_scale_bps integer NOT NULL DEFAULT 10000,
  relationship_id uuid,
  status character varying NOT NULL DEFAULT 'active'::character varying,
  latest_scale_bps integer,
  last_rebalanced_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT portfolio_allocation_members_pkey PRIMARY KEY (id),
  CONSTRAINT portfolio_allocation_members_portfolio_basket_id_fkey FOREIGN KEY (portfolio_basket_id) REFERENCES public.portfolio_baskets(id),
  CONSTRAINT portfolio_allocation_members_relationship_id_fkey FOREIGN KEY (relationship_id) REFERENCES public.bot_copy_relationships(id),
  CONSTRAINT portfolio_allocation_members_source_runtime_id_fkey FOREIGN KEY (source_runtime_id) REFERENCES public.bot_runtimes(id)
);
CREATE TABLE public.portfolio_baskets (
  id uuid NOT NULL,
  owner_user_id uuid NOT NULL,
  wallet_address character varying NOT NULL,
  name character varying NOT NULL,
  description text NOT NULL DEFAULT ''::text,
  status character varying NOT NULL DEFAULT 'draft'::character varying,
  rebalance_mode character varying NOT NULL DEFAULT 'drift'::character varying,
  rebalance_interval_minutes integer NOT NULL DEFAULT 60,
  drift_threshold_pct double precision NOT NULL DEFAULT 6,
  target_notional_usd double precision NOT NULL DEFAULT 0,
  current_notional_usd double precision NOT NULL DEFAULT 0,
  kill_switch_reason text,
  last_rebalanced_at timestamp with time zone,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT portfolio_baskets_pkey PRIMARY KEY (id),
  CONSTRAINT portfolio_baskets_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id)
);
CREATE TABLE public.portfolio_rebalance_events (
  id uuid NOT NULL,
  portfolio_basket_id uuid NOT NULL,
  trigger character varying NOT NULL DEFAULT 'manual'::character varying,
  status character varying NOT NULL DEFAULT 'completed'::character varying,
  summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT portfolio_rebalance_events_pkey PRIMARY KEY (id),
  CONSTRAINT portfolio_rebalance_events_portfolio_basket_id_fkey FOREIGN KEY (portfolio_basket_id) REFERENCES public.portfolio_baskets(id)
);
CREATE TABLE public.portfolio_risk_policies (
  id uuid NOT NULL,
  portfolio_basket_id uuid NOT NULL UNIQUE,
  max_drawdown_pct double precision NOT NULL DEFAULT 18,
  max_member_drawdown_pct double precision NOT NULL DEFAULT 22,
  min_trust_score integer NOT NULL DEFAULT 55,
  max_active_members integer NOT NULL DEFAULT 5,
  auto_pause_on_source_stale boolean NOT NULL DEFAULT true,
  kill_switch_on_breach boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT portfolio_risk_policies_pkey PRIMARY KEY (id),
  CONSTRAINT portfolio_risk_policies_portfolio_basket_id_fkey FOREIGN KEY (portfolio_basket_id) REFERENCES public.portfolio_baskets(id)
);
CREATE TABLE public.strategy_activity_records (
  id uuid NOT NULL,
  vault_id uuid NOT NULL,
  action_type character varying NOT NULL,
  summary text NOT NULL,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  recorded_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT strategy_activity_records_pkey PRIMARY KEY (id)
);
CREATE TABLE public.users (
  id uuid NOT NULL,
  wallet_address character varying NOT NULL UNIQUE,
  display_name character varying,
  auth_provider character varying NOT NULL DEFAULT 'privy'::character varying,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT users_pkey PRIMARY KEY (id)
);
CREATE TABLE public.worker_leases (
  lease_key character varying NOT NULL,
  owner_id character varying NOT NULL,
  expires_at timestamp with time zone NOT NULL,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT worker_leases_pkey PRIMARY KEY (lease_key)
);