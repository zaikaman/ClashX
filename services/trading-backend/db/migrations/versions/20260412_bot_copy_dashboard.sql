begin;

create table if not exists public.bot_copy_execution_events (
  id uuid not null,
  relationship_id uuid not null,
  source_runtime_id uuid not null,
  source_event_id uuid not null,
  follower_user_id uuid not null,
  follower_wallet_address character varying not null,
  symbol character varying not null default ''::character varying,
  side character varying,
  position_side character varying,
  action_type character varying not null,
  reduce_only boolean not null default false,
  requested_quantity double precision not null default 0,
  copied_quantity double precision not null default 0,
  reference_price double precision not null default 0,
  notional_estimate_usd double precision not null default 0,
  request_id character varying,
  client_order_id character varying,
  status character varying not null default 'queued'::character varying,
  error_reason text,
  result_payload_json jsonb not null default '{}'::jsonb,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint bot_copy_execution_events_pkey primary key (id),
  constraint bot_copy_execution_events_relationship_id_fkey foreign key (relationship_id) references public.bot_copy_relationships(id),
  constraint bot_copy_execution_events_source_runtime_id_fkey foreign key (source_runtime_id) references public.bot_runtimes(id),
  constraint bot_copy_execution_events_source_event_id_fkey foreign key (source_event_id) references public.bot_execution_events(id),
  constraint bot_copy_execution_events_follower_user_id_fkey foreign key (follower_user_id) references public.users(id)
);

create index if not exists ix_bot_copy_execution_events_wallet_created
  on public.bot_copy_execution_events(follower_wallet_address, created_at desc);

create index if not exists ix_bot_copy_execution_events_relationship_created
  on public.bot_copy_execution_events(relationship_id, created_at desc);

create index if not exists ix_bot_copy_execution_events_source_event
  on public.bot_copy_execution_events(source_event_id, relationship_id);

commit;
