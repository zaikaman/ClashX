begin;

create extension if not exists pgcrypto;

create table if not exists public.creator_marketplace_profiles (
  id uuid primary key,
  user_id uuid not null unique references public.users(id) on delete cascade,
  display_name varchar(120) not null,
  slug varchar(160) not null unique,
  headline text not null default '',
  bio text not null default '',
  social_links_json jsonb not null default '{}'::jsonb,
  featured_collection_title varchar(120) not null default 'Featured strategies',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.creator_marketplace_profiles add column if not exists user_id uuid references public.users(id) on delete cascade;
alter table public.creator_marketplace_profiles add column if not exists display_name varchar(120) not null default '';
alter table public.creator_marketplace_profiles add column if not exists slug varchar(160);
alter table public.creator_marketplace_profiles add column if not exists headline text not null default '';
alter table public.creator_marketplace_profiles add column if not exists bio text not null default '';
alter table public.creator_marketplace_profiles add column if not exists social_links_json jsonb not null default '{}'::jsonb;
alter table public.creator_marketplace_profiles add column if not exists featured_collection_title varchar(120) not null default 'Featured strategies';
alter table public.creator_marketplace_profiles add column if not exists created_at timestamptz not null default now();
alter table public.creator_marketplace_profiles add column if not exists updated_at timestamptz not null default now();

create unique index if not exists ix_creator_marketplace_profiles_user_id on public.creator_marketplace_profiles(user_id);
create unique index if not exists ix_creator_marketplace_profiles_slug on public.creator_marketplace_profiles(slug);

create table if not exists public.bot_publishing_settings (
  id uuid primary key,
  bot_definition_id uuid not null unique references public.bot_definitions(id) on delete cascade,
  user_id uuid not null references public.users(id) on delete cascade,
  visibility varchar(24) not null default 'private',
  access_mode varchar(24) not null default 'private',
  publish_state varchar(24) not null default 'draft',
  listed_at timestamptz,
  hero_headline text not null default '',
  access_note text not null default '',
  featured_collection_key varchar(120),
  featured_collection_title varchar(120),
  featured_rank integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.bot_publishing_settings add column if not exists bot_definition_id uuid references public.bot_definitions(id) on delete cascade;
alter table public.bot_publishing_settings add column if not exists user_id uuid references public.users(id) on delete cascade;
alter table public.bot_publishing_settings add column if not exists visibility varchar(24) not null default 'private';
alter table public.bot_publishing_settings add column if not exists access_mode varchar(24) not null default 'private';
alter table public.bot_publishing_settings add column if not exists publish_state varchar(24) not null default 'draft';
alter table public.bot_publishing_settings add column if not exists listed_at timestamptz;
alter table public.bot_publishing_settings add column if not exists hero_headline text not null default '';
alter table public.bot_publishing_settings add column if not exists access_note text not null default '';
alter table public.bot_publishing_settings add column if not exists featured_collection_key varchar(120);
alter table public.bot_publishing_settings add column if not exists featured_collection_title varchar(120);
alter table public.bot_publishing_settings add column if not exists featured_rank integer not null default 0;
alter table public.bot_publishing_settings add column if not exists created_at timestamptz not null default now();
alter table public.bot_publishing_settings add column if not exists updated_at timestamptz not null default now();

create unique index if not exists ix_bot_publishing_settings_bot_definition_id
  on public.bot_publishing_settings(bot_definition_id);
create index if not exists ix_bot_publishing_settings_user_id
  on public.bot_publishing_settings(user_id);
create index if not exists ix_bot_publishing_settings_publish_state
  on public.bot_publishing_settings(publish_state);

create table if not exists public.featured_bots (
  id uuid primary key,
  creator_profile_id uuid not null references public.creator_marketplace_profiles(id) on delete cascade,
  bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  collection_key varchar(120) not null default 'featured',
  collection_title varchar(120) not null default 'Featured strategies',
  shelf_rank integer not null default 0,
  featured_reason text not null default '',
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.featured_bots add column if not exists creator_profile_id uuid references public.creator_marketplace_profiles(id) on delete cascade;
alter table public.featured_bots add column if not exists bot_definition_id uuid references public.bot_definitions(id) on delete cascade;
alter table public.featured_bots add column if not exists collection_key varchar(120) not null default 'featured';
alter table public.featured_bots add column if not exists collection_title varchar(120) not null default 'Featured strategies';
alter table public.featured_bots add column if not exists shelf_rank integer not null default 0;
alter table public.featured_bots add column if not exists featured_reason text not null default '';
alter table public.featured_bots add column if not exists active boolean not null default true;
alter table public.featured_bots add column if not exists created_at timestamptz not null default now();
alter table public.featured_bots add column if not exists updated_at timestamptz not null default now();

create unique index if not exists ix_featured_bots_unique_bot_collection
  on public.featured_bots(bot_definition_id, collection_key);
create index if not exists ix_featured_bots_creator_profile_id
  on public.featured_bots(creator_profile_id);
create index if not exists ix_featured_bots_active_rank
  on public.featured_bots(active, shelf_rank, updated_at desc);

create table if not exists public.bot_invite_access (
  id uuid primary key,
  bot_definition_id uuid not null references public.bot_definitions(id) on delete cascade,
  invited_wallet_address varchar(128) not null,
  invited_by_user_id uuid not null references public.users(id) on delete cascade,
  status varchar(24) not null default 'active',
  note text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.bot_invite_access add column if not exists bot_definition_id uuid references public.bot_definitions(id) on delete cascade;
alter table public.bot_invite_access add column if not exists invited_wallet_address varchar(128);
alter table public.bot_invite_access add column if not exists invited_by_user_id uuid references public.users(id) on delete cascade;
alter table public.bot_invite_access add column if not exists status varchar(24) not null default 'active';
alter table public.bot_invite_access add column if not exists note text not null default '';
alter table public.bot_invite_access add column if not exists created_at timestamptz not null default now();
alter table public.bot_invite_access add column if not exists updated_at timestamptz not null default now();

create unique index if not exists ix_bot_invite_access_unique_wallet_per_bot
  on public.bot_invite_access(bot_definition_id, invited_wallet_address);
create index if not exists ix_bot_invite_access_wallet_status
  on public.bot_invite_access(invited_wallet_address, status);

insert into public.creator_marketplace_profiles (
  id,
  user_id,
  display_name,
  slug,
  headline,
  bio,
  social_links_json,
  featured_collection_title,
  created_at,
  updated_at
)
select
  gen_random_uuid(),
  u.id,
  coalesce(nullif(btrim(u.display_name), ''), left(u.wallet_address, 8)),
  lower(
    regexp_replace(
      coalesce(nullif(btrim(u.display_name), ''), left(u.wallet_address, 8)),
      '[^a-zA-Z0-9]+',
      '-',
      'g'
    )
  ) || '-' || left(replace(u.id::text, '-', ''), 6),
  'Publishing live strategies with clear guardrails.',
  '',
  '{}'::jsonb,
  'Featured strategies',
  now(),
  now()
from public.users u
where exists (
  select 1
  from public.bot_definitions defs
  where defs.user_id = u.id
)
and not exists (
  select 1
  from public.creator_marketplace_profiles profiles
  where profiles.user_id = u.id
);

update public.creator_marketplace_profiles
set
  display_name = coalesce(nullif(btrim(display_name), ''), 'Creator'),
  slug = coalesce(
    nullif(btrim(slug), ''),
    lower(regexp_replace(display_name, '[^a-zA-Z0-9]+', '-', 'g'))
  ),
  headline = coalesce(headline, ''),
  bio = coalesce(bio, ''),
  social_links_json = coalesce(social_links_json, '{}'::jsonb),
  featured_collection_title = coalesce(nullif(btrim(featured_collection_title), ''), 'Featured strategies'),
  updated_at = coalesce(updated_at, now());

insert into public.bot_publishing_settings (
  id,
  bot_definition_id,
  user_id,
  visibility,
  access_mode,
  publish_state,
  listed_at,
  hero_headline,
  access_note,
  featured_collection_key,
  featured_collection_title,
  featured_rank,
  created_at,
  updated_at
)
select
  gen_random_uuid(),
  defs.id,
  defs.user_id,
  defs.visibility,
  defs.visibility,
  case
    when defs.visibility = 'public' then 'published'
    when defs.visibility = 'unlisted' then 'unlisted'
    when defs.visibility = 'invite_only' then 'invite_only'
    else 'draft'
  end,
  case
    when defs.visibility in ('public', 'unlisted', 'invite_only') then defs.updated_at
    else null
  end,
  '',
  '',
  null,
  null,
  0,
  coalesce(defs.created_at, now()),
  coalesce(defs.updated_at, now())
from public.bot_definitions defs
where not exists (
  select 1
  from public.bot_publishing_settings settings
  where settings.bot_definition_id = defs.id
);

update public.bot_publishing_settings
set
  visibility = coalesce(nullif(btrim(visibility), ''), 'private'),
  access_mode = coalesce(nullif(btrim(access_mode), ''), coalesce(nullif(btrim(visibility), ''), 'private')),
  publish_state = case
    when coalesce(nullif(btrim(visibility), ''), 'private') = 'public' then 'published'
    when coalesce(nullif(btrim(visibility), ''), 'private') = 'unlisted' then 'unlisted'
    when coalesce(nullif(btrim(visibility), ''), 'private') = 'invite_only' then 'invite_only'
    else 'draft'
  end,
  listed_at = case
    when coalesce(nullif(btrim(visibility), ''), 'private') in ('public', 'unlisted', 'invite_only')
      then coalesce(listed_at, updated_at, created_at, now())
    else null
  end,
  hero_headline = coalesce(hero_headline, ''),
  access_note = coalesce(access_note, ''),
  featured_rank = coalesce(featured_rank, 0),
  updated_at = coalesce(updated_at, now());

commit;
