create index if not exists ix_bot_definitions_wallet_updated
  on public.bot_definitions(wallet_address, updated_at desc);

create index if not exists ix_bot_runtimes_wallet_status_updated
  on public.bot_runtimes(wallet_address, status, updated_at desc);

create index if not exists ix_bot_runtimes_bot_wallet
  on public.bot_runtimes(bot_definition_id, wallet_address);

create index if not exists ix_bot_execution_events_runtime_decision_created
  on public.bot_execution_events(runtime_id, decision_summary, created_at desc);

create index if not exists ix_audit_events_user_created
  on public.audit_events(user_id, created_at desc);
