create table if not exists app_settings (
    key text primary key,
    value_json text not null,
    updated_at text not null default current_timestamp
);

insert into app_settings(key, value_json)
values
    ('auto_translate_enabled', 'false'),
    ('auto_translate_interval_hours', '5'),
    ('last_auto_translate_at', 'null')
on conflict(key) do nothing;

create table if not exists translation_queue (
    id integer primary key,
    mod_id text not null,
    source_name text,
    repo_url text,
    priority integer not null default 1000,
    status text not null default 'queued'
        check(status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    locked_job_id integer,
    last_error text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    started_at text,
    finished_at text
);

create unique index if not exists idx_translation_queue_active_mod
on translation_queue(mod_id)
where status in ('queued', 'running');

create index if not exists idx_translation_queue_status_priority
on translation_queue(status, priority, created_at);
