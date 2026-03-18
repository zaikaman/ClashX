-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

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
CREATE TABLE public.bot_clones (
  id uuid NOT NULL,
  source_bot_definition_id uuid NOT NULL,
  new_bot_definition_id uuid NOT NULL,
  created_by_user_id uuid NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT bot_clones_pkey PRIMARY KEY (id),
  CONSTRAINT bot_clones_source_bot_definition_id_fkey FOREIGN KEY (source_bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_clones_new_bot_definition_id_fkey FOREIGN KEY (new_bot_definition_id) REFERENCES public.bot_definitions(id),
  CONSTRAINT bot_clones_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public.users(id)
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
  CONSTRAINT bot_copy_relationships_pkey PRIMARY KEY (id),
  CONSTRAINT bot_copy_relationships_source_runtime_id_fkey FOREIGN KEY (source_runtime_id) REFERENCES public.bot_runtimes(id),
  CONSTRAINT bot_copy_relationships_follower_user_id_fkey FOREIGN KEY (follower_user_id) REFERENCES public.users(id)
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
  CONSTRAINT bot_trade_closures_runtime_id_fkey FOREIGN KEY (runtime_id) REFERENCES public.bot_runtimes(id),
  CONSTRAINT bot_trade_closures_lot_id_fkey FOREIGN KEY (lot_id) REFERENCES public.bot_trade_lots(id)
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
