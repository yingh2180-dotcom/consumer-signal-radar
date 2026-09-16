-- Run ONLY in the approved project after schema_preview.sql, using SQL Editor.
-- Transaction rolls back its synthetic checks; it does not modify real datasets.
-- Never report these checks as passed until actually executed against PostgreSQL.
begin;
do $checks$
declare t record;
begin
  for t in select schemaname,tablename from pg_tables where schemaname in ('demo_private','demo_reference') loop
    if has_table_privilege('anon',format('%I.%I',t.schemaname,t.tablename),'SELECT')
       or has_table_privilege('authenticated',format('%I.%I',t.schemaname,t.tablename),'SELECT') then
      raise exception 'Private table readable by a browser role';
    end if;
  end loop;
  if has_table_privilege('service_role','demo_private.raw_records','UPDATE')
     or has_table_privilege('service_role','demo_private.raw_records','DELETE')
     or has_table_privilege('service_role','demo_private.raw_records','TRUNCATE')
     or has_table_privilege('service_role','demo_reference.gold_labels','SELECT') then
    raise exception 'Raw/Gold application privilege unexpectedly present';
  end if;
  if has_table_privilege('anon','public.published_demo_snapshots','INSERT')
     or has_table_privilege('anon','public.published_demo_snapshots','UPDATE')
     or has_table_privilege('anon','public.published_demo_snapshots','DELETE') then
    raise exception 'Anonymous public snapshot write privilege present';
  end if;
end $checks$;

insert into demo_private.datasets values ('permission-check',repeat('0',64),'demo','pipeline_test','synthetic_demo');
insert into demo_private.pipeline_runs values ('permission-check','permission-check','rules_demo',now(),'{}','[]');
insert into demo_private.raw_records values ('permission-check','check-row',repeat('0',64),
 '{"record_id":"check-row","review_text":"synthetic","dataset_role":"pipeline_test","data_kind":"synthetic_demo","is_synthetic":"true","target_product_id":""}');
insert into demo_private.snapshots values
 ('permission-approved','permission-check',repeat('0',64),'{"context":"demo","mode":"rules_demo","summary":{"business_count":0}}'),
 ('permission-unapproved','permission-check',repeat('0',64),'{"context":"demo","mode":"rules_demo","summary":{"business_count":0}}');
insert into public.published_demo_snapshots values
 ('permission-approved','permission-check','demo',true,repeat('0',64),'{"snapshot_id":"permission-approved","run_id":"permission-check","context":"demo","mode":"rules_demo","summary":{"business_count":0}}'),
 ('permission-unapproved','permission-check','demo',false,repeat('0',64),'{"snapshot_id":"permission-unapproved","run_id":"permission-check","context":"demo","mode":"rules_demo","summary":{"business_count":0}}');

set local role anon;
do $checks$
begin
  if (select count(*) from public.published_demo_snapshots where snapshot_id like 'permission-%')<>1 then
    raise exception 'Anonymous approved-only filter failed';
  end if;
  begin
    perform 1 from demo_private.raw_records;
    raise exception 'Raw read unexpectedly succeeded';
  exception when insufficient_privilege then null; end;
  begin
    perform 1 from demo_reference.gold_labels;
    raise exception 'Gold read unexpectedly succeeded';
  exception when insufficient_privilege then null; end;
  begin
    delete from public.published_demo_snapshots where snapshot_id='permission-approved';
    raise exception 'Anonymous write unexpectedly succeeded';
  exception when insufficient_privilege then null; end;
end $checks$;
reset role;

set local role service_role;
do $checks$
begin
  begin
    update demo_private.raw_records set payload='{}' where dataset_id='permission-check';
    raise exception 'Raw overwrite unexpectedly succeeded';
  exception when insufficient_privilege then null; end;
end $checks$;
reset role;

-- Check private bucket flags and restrictive policy, independently of object existence.
select id,public from storage.buckets where id in ('demo-raw','demo-artifacts','demo-reference');
select policyname,permissive,roles,cmd,qual,with_check from pg_policies
 where schemaname='storage' and policyname='demo_private_bucket_guard';
select schemaname,tablename,rowsecurity from pg_tables where schemaname in ('demo_private','demo_reference');
rollback;
