-- REVIEW PREVIEW ONLY — not a migration and never executed by the adapter.
-- Target: a separately approved Supabase project. Intentionally fail on existing names.
-- Apply once using the SQL editor only after project/scope authorization and backup review.
begin;

create schema demo_private;
create schema demo_reference;
revoke all on schema demo_private, demo_reference from public, anon, authenticated;
grant usage on schema demo_private to service_role;

create table demo_private.datasets (
  dataset_id text primary key,
  raw_hash text not null check (raw_hash ~ '^[a-f0-9]{64}$'),
  context text not null check (context='demo'),
  dataset_role text not null check (dataset_role='pipeline_test'),
  data_kind text not null check (data_kind='synthetic_demo')
);
create table demo_private.pipeline_runs (
  run_id text primary key,
  dataset_id text not null references demo_private.datasets(dataset_id),
  mode text not null check (mode='rules_demo'),
  generated_at timestamptz not null,
  versions jsonb not null,
  stages jsonb not null,
  unique(run_id,dataset_id)
);
create table demo_private.raw_records (
  dataset_id text not null references demo_private.datasets(dataset_id),
  record_id text not null,
  content_hash text not null check (content_hash ~ '^[a-f0-9]{64}$'),
  payload jsonb not null check (
    payload->>'dataset_role'='pipeline_test' and payload->>'data_kind'='synthetic_demo'
    and lower(payload->>'is_synthetic')='true'
    and coalesce(payload->>'target_product_id','')=''
    and payload->>'record_id'=record_id
    and payload ? 'review_text'
  ),
  primary key(dataset_id,record_id)
);
create table demo_private.cleaning_results (
  run_id text not null,
  dataset_id text not null,
  record_id text not null,
  final_action text not null check(final_action in ('KEEP','FILTER','PENDING','ERROR')),
  payload jsonb not null,
  primary key(run_id,record_id),
  foreign key(run_id,dataset_id) references demo_private.pipeline_runs(run_id,dataset_id),
  foreign key(dataset_id,record_id) references demo_private.raw_records(dataset_id,record_id)
);
create table demo_private.features (
  run_id text not null,
  feature_id text not null,
  record_id text not null,
  dataset_id text not null,
  payload jsonb not null check (payload->>'sentiment' in ('positive','negative','neutral') and payload->>'audit_status'='RULE_VALIDATED'),
  primary key(run_id,feature_id),
  foreign key(run_id,record_id) references demo_private.cleaning_results(run_id,record_id),
  foreign key(run_id,dataset_id) references demo_private.pipeline_runs(run_id,dataset_id),
  foreign key(dataset_id,record_id) references demo_private.raw_records(dataset_id,record_id)
);
create table demo_private.feature_checks (
  run_id text not null,
  feature_id text not null,
  status text not null check(status='RULE_VALIDATED'),
  payload jsonb not null,
  primary key(run_id,feature_id),
  foreign key(run_id,feature_id) references demo_private.features(run_id,feature_id)
);
create table demo_private.decisions (
  run_id text not null references demo_private.pipeline_runs(run_id),
  slice_key text not null,
  decision_id text not null,
  payload jsonb not null,
  primary key(run_id,slice_key,decision_id)
);
create table demo_private.evidence_bindings (
  run_id text not null,
  slice_key text not null,
  decision_id text not null,
  feature_id text not null,
  primary key(run_id,slice_key,decision_id,feature_id),
  foreign key(run_id,slice_key,decision_id) references demo_private.decisions(run_id,slice_key,decision_id),
  foreign key(run_id,feature_id) references demo_private.features(run_id,feature_id)
);
create table demo_private.review_actions (
  run_id text not null,
  review_id text not null,
  record_id text not null,
  payload jsonb not null,
  primary key(run_id,review_id),
  foreign key(run_id,record_id) references demo_private.cleaning_results(run_id,record_id)
);
create table demo_private.qa_reports (
  run_id text primary key references demo_private.pipeline_runs(run_id),
  payload jsonb not null check(payload->>'business_count'='0')
);
create table demo_private.snapshots (
  snapshot_id text primary key,
  run_id text not null references demo_private.pipeline_runs(run_id),
  content_hash text not null check (content_hash ~ '^[a-f0-9]{64}$'),
  payload jsonb not null check(payload->>'context'='demo' and payload->>'mode'='rules_demo' and payload->'summary'->>'business_count'='0')
);

-- Independent reference/Gold never enters pipeline payloads; no service_role grants.
create table demo_reference.gold_labels (
  reference_id text not null,
  record_id text not null,
  reference_kind text not null check(reference_kind in ('human_gold','synthetic_expected','benchmark')),
  provenance jsonb not null,
  labels jsonb not null,
  primary key(reference_id,record_id)
);

-- Public content is a separate approved copy, never a view of private tables.
create table public.published_demo_snapshots (
  snapshot_id text primary key references demo_private.snapshots(snapshot_id),
  run_id text not null references demo_private.pipeline_runs(run_id),
  context text not null check(context='demo'),
  approved boolean not null default false,
  content_hash text not null check(content_hash ~ '^[a-f0-9]{64}$'),
  payload jsonb not null check(payload->>'context'='demo' and payload->>'mode'='rules_demo'
    and payload->'summary'->>'business_count'='0'
    and payload->>'snapshot_id'=snapshot_id and payload->>'run_id'=run_id)
);

-- RLS is defense in depth; no browser grants/policies on any private layer.
do $block$
declare t record;
begin
  for t in select schemaname,tablename from pg_tables where schemaname in ('demo_private','demo_reference') loop
    execute format('alter table %I.%I enable row level security',t.schemaname,t.tablename);
    execute format('alter table %I.%I force row level security',t.schemaname,t.tablename);
  end loop;
end $block$;
revoke all on all tables in schema demo_private, demo_reference from public, anon, authenticated, service_role;
grant select,insert,update on all tables in schema demo_private to service_role;
revoke update on demo_private.datasets,demo_private.raw_records,demo_private.snapshots from service_role;
alter default privileges in schema demo_private revoke all on tables from public,anon,authenticated;
alter default privileges in schema demo_reference revoke all on tables from public,anon,authenticated,service_role;

alter table public.published_demo_snapshots enable row level security;
alter table public.published_demo_snapshots force row level security;
revoke all on public.published_demo_snapshots from public,anon,authenticated,service_role;
grant select on public.published_demo_snapshots to anon;
grant select,insert on public.published_demo_snapshots to service_role;
create policy approved_demo_read on public.published_demo_snapshots for select to anon
  using (approved is true and context='demo');

-- Reject mutation even if an application privilege is later accidentally broadened.
-- An owner/admin can still change schema or disable triggers: this is not administrator-proof.
create function demo_private.reject_immutable_mutation() returns trigger
language plpgsql security invoker set search_path='' as $body$
begin
  raise exception 'Immutable demo archive: update/delete/truncate forbidden' using errcode='55000';
end $body$;
revoke all on function demo_private.reject_immutable_mutation() from public,anon,authenticated,service_role;
do $block$
declare table_name text;
begin
  foreach table_name in array array['datasets','raw_records','snapshots'] loop
    execute format('create trigger immutable_row before update or delete on demo_private.%I for each row execute function demo_private.reject_immutable_mutation()',table_name);
    execute format('create trigger immutable_table before truncate on demo_private.%I for each statement execute function demo_private.reject_immutable_mutation()',table_name);
  end loop;
end $block$;
create trigger immutable_public_snapshot before update or delete on public.published_demo_snapshots
  for each row execute function demo_private.reject_immutable_mutation();
create trigger immutable_public_snapshot_table before truncate on public.published_demo_snapshots
  for each statement execute function demo_private.reject_immutable_mutation();

-- Storage buckets are private. The reference bucket is physically separated and not synced.
insert into storage.buckets(id,name,public) values
 ('demo-raw','demo-raw',false),('demo-artifacts','demo-artifacts',false),('demo-reference','demo-reference',false);
-- Restrictive guards also defeat a pre-existing broad permissive browser policy.
create policy demo_private_bucket_guard on storage.objects as restrictive for all to anon,authenticated
 using (bucket_id not in ('demo-raw','demo-artifacts','demo-reference'))
 with check (bucket_id not in ('demo-raw','demo-artifacts','demo-reference'));

commit;
