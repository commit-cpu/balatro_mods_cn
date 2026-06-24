create virtual table if not exists tm_entries_fts using fts5(
    source_text,
    target_text,
    normalized_source,
    content='tm_entries',
    content_rowid='id'
);

create trigger if not exists tm_entries_ai after insert on tm_entries begin
    insert into tm_entries_fts(rowid, source_text, target_text, normalized_source)
    values (new.id, new.source_text, new.target_text, new.normalized_source);
end;

create trigger if not exists tm_entries_ad after delete on tm_entries begin
    insert into tm_entries_fts(tm_entries_fts, rowid, source_text, target_text, normalized_source)
    values ('delete', old.id, old.source_text, old.target_text, old.normalized_source);
end;

create trigger if not exists tm_entries_au after update on tm_entries begin
    insert into tm_entries_fts(tm_entries_fts, rowid, source_text, target_text, normalized_source)
    values ('delete', old.id, old.source_text, old.target_text, old.normalized_source);
    insert into tm_entries_fts(rowid, source_text, target_text, normalized_source)
    values (new.id, new.source_text, new.target_text, new.normalized_source);
end;
