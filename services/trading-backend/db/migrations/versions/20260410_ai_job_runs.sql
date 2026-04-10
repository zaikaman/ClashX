begin;

create table if not exists public.ai_job_runs (
  id uuid not null,
  job_type character varying not null,
  status character varying not null default 'queued'::character varying,
  wallet_address character varying,
  conversation_id uuid,
  request_payload_json jsonb not null default '{}'::jsonb,
  result_payload_json jsonb not null default '{}'::jsonb,
  error_detail text,
  started_at timestamp with time zone,
  completed_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  constraint ai_job_runs_pkey primary key (id),
  constraint ai_job_runs_conversation_id_fkey foreign key (conversation_id) references public.copilot_conversations(id)
);

create index if not exists ix_ai_job_runs_status_created
  on public.ai_job_runs(status, created_at desc);

create index if not exists ix_ai_job_runs_wallet_created
  on public.ai_job_runs(wallet_address, created_at desc);

create index if not exists ix_ai_job_runs_conversation_created
  on public.ai_job_runs(conversation_id, created_at desc);

commit;
