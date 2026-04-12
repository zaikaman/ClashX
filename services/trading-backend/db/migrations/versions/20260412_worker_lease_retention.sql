create index if not exists worker_leases_expires_at_idx
    on public.worker_leases (expires_at);

delete from public.worker_leases
where expires_at < (now() - interval '1 day');
