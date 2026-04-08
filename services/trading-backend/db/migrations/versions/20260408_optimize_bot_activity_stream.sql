begin;

create index if not exists ix_bot_execution_events_runtime_created_at
  on public.bot_execution_events(runtime_id, created_at desc);

commit;
