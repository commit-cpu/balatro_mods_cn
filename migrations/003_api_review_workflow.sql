create table if not exists jobs (
    id integer primary key,
    type text not null,
    status text not null default 'pending'
        check(status in ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
    idempotency_key text not null unique,
    payload_json text not null default '{}',
    attempts integer not null default 0,
    max_attempts integer not null default 3,
    last_error text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    started_at text,
    finished_at text
);

create index if not exists idx_jobs_status_created on jobs(status, created_at);
create index if not exists idx_jobs_type_status on jobs(type, status);

create table if not exists feedback (
    id integer primary key,
    mod_id text not null,
    unit_key text not null,
    translation_id text,
    feedback_type text not null
        check(feedback_type in (
            'semantic_error',
            'term_inconsistent',
            'unnatural',
            'format_error',
            'untranslated',
            'other'
        )),
    suggested_text text,
    comment text,
    status text not null default 'pending'
        check(status in ('pending', 'accepted', 'rejected', 'applied')),
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp
);

create index if not exists idx_feedback_mod_status on feedback(mod_id, status);
create index if not exists idx_feedback_unit on feedback(unit_key);

create table if not exists review_items (
    id integer primary key,
    mod_id text not null,
    unit_key text not null,
    source_text text not null,
    current_target_text text,
    suggested_target_text text,
    edited_target_text text,
    reason text not null,
    status text not null default 'pending'
        check(status in ('pending', 'approved', 'rejected', 'needs_changes')),
    reviewer text,
    comment text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    reviewed_at text
);

create index if not exists idx_review_items_mod_status on review_items(mod_id, status);
create index if not exists idx_review_items_unit on review_items(unit_key);

create table if not exists pull_requests (
    id integer primary key,
    mod_id text not null,
    repo_slug text not null,
    branch text not null,
    pr_number integer,
    title text,
    html_url text,
    state text not null default 'unknown',
    last_commit_sha text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique(mod_id, repo_slug, branch)
);

create index if not exists idx_pull_requests_mod_state on pull_requests(mod_id, state);
