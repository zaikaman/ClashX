begin;

create table if not exists public.copilot_conversations (
  id uuid not null,
  user_id uuid not null,
  wallet_address character varying not null,
  title character varying not null default 'New conversation'::character varying,
  context_summary text not null default ''::text,
  summary_message_count integer not null default 0,
  summary_token_estimate integer not null default 0,
  message_count integer not null default 0,
  last_message_preview text not null default ''::text,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  latest_message_at timestamp with time zone not null default now(),
  constraint copilot_conversations_pkey primary key (id),
  constraint copilot_conversations_user_id_fkey foreign key (user_id) references public.users(id)
);

create table if not exists public.copilot_messages (
  id uuid not null,
  conversation_id uuid not null,
  role character varying not null,
  content text not null default ''::text,
  tool_calls_json jsonb not null default '[]'::jsonb,
  follow_ups_json jsonb not null default '[]'::jsonb,
  provider character varying,
  token_estimate integer not null default 0,
  created_at timestamp with time zone not null default now(),
  constraint copilot_messages_pkey primary key (id),
  constraint copilot_messages_conversation_id_fkey foreign key (conversation_id) references public.copilot_conversations(id)
);

create index if not exists ix_copilot_conversations_wallet_latest
  on public.copilot_conversations(wallet_address, latest_message_at desc);

create index if not exists ix_copilot_conversations_user_latest
  on public.copilot_conversations(user_id, latest_message_at desc);

create index if not exists ix_copilot_messages_conversation_created
  on public.copilot_messages(conversation_id, created_at asc);

commit;
