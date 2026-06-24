create table if not exists schema_migrations (
    version integer primary key,
    name text not null,
    applied_at text not null default current_timestamp
);

create table if not exists mod_sources (
    id integer primary key,
    mod_id text not null unique,
    repo_path text not null,
    source_locale_path text not null,
    target_locale_path text not null,
    import_enabled integer not null default 1,
    created_at text not null default current_timestamp
);

create table if not exists import_runs (
    id integer primary key,
    mod_id text not null,
    source_locale_path text not null,
    target_locale_path text not null,
    source_unit_count integer not null,
    imported_pair_count integer not null,
    skipped_count integer not null,
    created_at text not null default current_timestamp
);

create table if not exists tm_entries (
    id integer primary key,
    mod_id text not null,
    unit_key text not null,
    context_type text not null,
    source_text text not null,
    target_text text not null,
    normalized_source text not null,
    token_signature text not null,
    source_locale text not null default 'en-us',
    target_locale text not null default 'zh_CN',
    quality text not null default 'imported_human',
    qdrant_point_id text not null unique,
    source_hash text not null,
    target_hash text not null,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique(mod_id, unit_key, source_hash, target_hash)
);

create index if not exists idx_tm_entries_mod_id on tm_entries(mod_id);
create index if not exists idx_tm_entries_context on tm_entries(context_type);
create index if not exists idx_tm_entries_signature on tm_entries(token_signature);

create table if not exists vector_outbox (
    id integer primary key,
    tm_entry_id integer not null references tm_entries(id) on delete cascade,
    operation text not null check(operation in ('upsert', 'delete')),
    collection text not null,
    status text not null default 'pending' check(status in ('pending', 'processing', 'done', 'failed')),
    attempts integer not null default 0,
    last_error text,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    unique(tm_entry_id, collection, operation)
);

create index if not exists idx_vector_outbox_status on vector_outbox(status, id);

create table if not exists rag_traces (
    id integer primary key,
    query_text text not null,
    normalized_query text not null,
    collection text not null,
    dense_top_k integer not null,
    result_count integer not null,
    trace_json text not null,
    created_at text not null default current_timestamp
);
