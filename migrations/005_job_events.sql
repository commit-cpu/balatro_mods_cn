create table if not exists job_events (
    id integer primary key,
    job_id integer not null references jobs(id) on delete cascade,
    level text not null default 'info',
    event text not null,
    message text not null,
    payload_json text not null default '{}',
    created_at text not null default current_timestamp
);

create index if not exists idx_job_events_job_id on job_events(job_id, id);
