create table if not exists mod_workflows (
    mod_id text primary key,
    upstream_url text,
    upstream_slug text,
    canonical_upstream text,
    fork_slug text,
    fork_status text,
    localization_status text,
    workflow_status text not null default 'unprobed',
    next_action text not null default 'probe',
    last_probe_at text,
    cache_expires_at text,
    last_job_id integer,
    last_error text,
    updated_at text not null default current_timestamp
);

create index if not exists idx_mod_workflows_status on mod_workflows(workflow_status);
create index if not exists idx_mod_workflows_next_action on mod_workflows(next_action);
