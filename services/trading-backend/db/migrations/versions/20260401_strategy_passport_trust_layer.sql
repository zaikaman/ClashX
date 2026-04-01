begin;

create table if not exists public.bot_strategy_versions (
  id uuid primary key,
  bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  created_by_user_id uuid not null references public.users(id) on delete cascade,
  version_number integer not null default 1,
  change_kind varchar(32) not null default 'revision',
  visibility_snapshot varchar(24) not null default 'private',
  name_snapshot varchar(120) not null,
  description_snapshot text not null default '',
  market_scope_snapshot varchar(120) not null default 'Pacifica perpetuals',
  strategy_type_snapshot varchar(64) not null default 'rules',
  authoring_mode_snapshot varchar(24) not null default 'visual',
  rules_version_snapshot integer not null default 1,
  rules_json_snapshot jsonb not null default '{}'::jsonb,
  is_public_release boolean not null default false,
  created_at timestamptz not null default now()
);

alter table public.bot_strategy_versions add column if not exists bot_definition_id uuid references public.bot_definitions(id) on delete cascade;
alter table public.bot_strategy_versions add column if not exists created_by_user_id uuid references public.users(id) on delete cascade;
alter table public.bot_strategy_versions add column if not exists version_number integer not null default 1;
alter table public.bot_strategy_versions add column if not exists change_kind varchar(32) not null default 'revision';
alter table public.bot_strategy_versions add column if not exists visibility_snapshot varchar(24) not null default 'private';
alter table public.bot_strategy_versions add column if not exists name_snapshot varchar(120) not null default '';
alter table public.bot_strategy_versions add column if not exists description_snapshot text not null default '';
alter table public.bot_strategy_versions add column if not exists market_scope_snapshot varchar(120) not null default 'Pacifica perpetuals';
alter table public.bot_strategy_versions add column if not exists strategy_type_snapshot varchar(64) not null default 'rules';
alter table public.bot_strategy_versions add column if not exists authoring_mode_snapshot varchar(24) not null default 'visual';
alter table public.bot_strategy_versions add column if not exists rules_version_snapshot integer not null default 1;
alter table public.bot_strategy_versions add column if not exists rules_json_snapshot jsonb not null default '{}'::jsonb;
alter table public.bot_strategy_versions add column if not exists is_public_release boolean not null default false;
alter table public.bot_strategy_versions add column if not exists created_at timestamptz not null default now();

create unique index if not exists ix_bot_strategy_versions_bot_definition_version on public.bot_strategy_versions(bot_definition_id, version_number);
create index if not exists ix_bot_strategy_versions_created_by_user_id on public.bot_strategy_versions(created_by_user_id);
create index if not exists ix_bot_strategy_versions_created_at on public.bot_strategy_versions(created_at desc);

create table if not exists public.bot_publish_snapshots (
  id uuid primary key,
  bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  strategy_version_id uuid not null references public.bot_strategy_versions(id) on delete cascade,
  runtime_id uuid references public.bot_runtimes(id) on delete set null,
  visibility_snapshot varchar(24) not null default 'public',
  publish_state varchar(24) not null default 'published',
  summary_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.bot_publish_snapshots add column if not exists bot_definition_id uuid references public.bot_definitions(id) on delete cascade;
alter table public.bot_publish_snapshots add column if not exists strategy_version_id uuid references public.bot_strategy_versions(id) on delete cascade;
alter table public.bot_publish_snapshots add column if not exists runtime_id uuid references public.bot_runtimes(id) on delete set null;
alter table public.bot_publish_snapshots add column if not exists visibility_snapshot varchar(24) not null default 'public';
alter table public.bot_publish_snapshots add column if not exists publish_state varchar(24) not null default 'published';
alter table public.bot_publish_snapshots add column if not exists summary_json jsonb not null default '{}'::jsonb;
alter table public.bot_publish_snapshots add column if not exists created_at timestamptz not null default now();

create index if not exists ix_bot_publish_snapshots_bot_definition_id on public.bot_publish_snapshots(bot_definition_id);
create index if not exists ix_bot_publish_snapshots_strategy_version_id on public.bot_publish_snapshots(strategy_version_id);
create index if not exists ix_bot_publish_snapshots_created_at on public.bot_publish_snapshots(created_at desc);

commit;
