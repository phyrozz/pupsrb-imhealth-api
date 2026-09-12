-- =============================================================================
-- DB Patch: Migrate from Supabase Auth to AWS Cognito
-- =============================================================================
-- Run this against your existing PostgreSQL database.
-- Safe to re-run (uses IF EXISTS / IF NOT EXISTS / ON CONFLICT).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Drop Supabase auth-specific triggers and functions
-- -----------------------------------------------------------------------------
drop trigger if exists on_auth_user_created on auth.users;
drop function if exists public.handle_new_user();
drop function if exists public.is_admin_user();


-- -----------------------------------------------------------------------------
-- 2. Patch `profiles` table
--    - Remove FK to auth.users (Supabase-managed)
--    - Remove auth.uid() default (doesn't exist outside Supabase)
--    Cognito `sub` (a UUID string) is used as the id.
-- -----------------------------------------------------------------------------
alter table public.profiles
  drop constraint if exists profiles_id_fkey;

alter table public.profiles
  alter column id drop default;


-- -----------------------------------------------------------------------------
-- 3. Patch `assessment_reminders` table
--    - Remove auth.uid() default
-- -----------------------------------------------------------------------------
alter table public.assessment_reminders
  alter column id drop default;


-- -----------------------------------------------------------------------------
-- 4. Add `profile_id` to `admins` so the is_admin check works
--    AssessmentsDAL.get_apriori_result joins admins on email;
--    PersonalDetailsDAL.is_admin joins admins → profiles on id.
--    Adding profile_id lets both patterns work.
-- -----------------------------------------------------------------------------
alter table public.admins
  add column if not exists profile_id uuid references public.profiles(id) on delete set null;

create unique index if not exists admins_profile_id_idx on public.admins(profile_id);


-- -----------------------------------------------------------------------------
-- 5. Fix `mental_health_uptrend` and `mental_health_downtrend`
--    cron_dal.py inserts (scenario_id, count, snapshot_date) but the old
--    schema only had (count, created_at). Add the missing columns.
-- -----------------------------------------------------------------------------
alter table public.mental_health_uptrend
  add column if not exists scenario_id integer references public.assessment_scenarios(id) on delete set null,
  add column if not exists snapshot_date date;

alter table public.mental_health_downtrend
  add column if not exists scenario_id integer references public.assessment_scenarios(id) on delete set null,
  add column if not exists snapshot_date date;


-- -----------------------------------------------------------------------------
-- 6. Fix `get_assessments_table` stored function
--    Old param names: search_query, selected_scenario_name, selected_status_name, page_number
--    AssessmentsDAL.list_assessments sends: search, scenario, status, page_size, page
--    Also adds missing columns to the result (counseling_status_id, result_scenario_id,
--    program_initial, year, email, birth_date, marital_status, is_working_student)
--    needed by StudentHistorySidebar and the generate report pages.
-- -----------------------------------------------------------------------------
drop function if exists public.get_assessments_table(text, text, text, text, text);

create or replace function public.get_assessments_table(
  search    text,
  scenario  text,
  status    text,
  page_size text,
  page      text
)
returns table(
  total_count          bigint,
  id                   bigint,
  created_at           timestamptz,
  user_id              uuid,
  first_name           text,
  middle_name          text,
  last_name            text,
  name_suffix          text,
  student_number       text,
  result_scenario      text,
  result_scenario_id   integer,
  counseling_status    text,
  counseling_status_id integer,
  program_initial      text,
  year                 smallint,
  email                text,
  birth_date           date,
  marital_status       text,
  is_working_student   boolean
)
language sql stable as $$
  select
    count(*) over ()                            as total_count,
    ar.id,
    a.created_at,
    ar.user_id,
    pd.first_name,
    pd.middle_name,
    pd.last_name,
    pd.name_suffix,
    pd.student_number,
    s.name                                      as result_scenario,
    ar.apriori_result                           as result_scenario_id,
    coalesce(cs.name, '')                       as counseling_status,
    coalesce(ar.counseling_status_id, 0)        as counseling_status_id,
    p.initial                                   as program_initial,
    pd.year,
    pd.email,
    pd.birth_date,
    ms.status                                   as marital_status,
    pd.is_working_student
  from public.apriori_results ar
  join public.assessments a         on a.id   = ar.assessment_id
  join public.personal_details pd   on pd.user_id = ar.user_id
  join public.assessment_scenarios s on s.id  = ar.apriori_result
  left join public.counseling_statuses cs on cs.id = ar.counseling_status_id
  left join public.programs p        on p.id  = pd.program_id
  left join public.marital_statuses ms on ms.id = pd.marital_status_id
  where (search   is null or search   = '' or concat_ws(' ', pd.first_name, pd.middle_name, pd.last_name, pd.name_suffix, pd.student_number) ilike '%' || search || '%')
    and (scenario is null or scenario = '' or s.name = scenario)
    and (status   is null or status   = '' or coalesce(cs.name, '') = status)
  order by a.created_at desc
  offset ((greatest(coalesce(nullif(page, '')::int, 1), 1) - 1) * greatest(coalesce(nullif(page_size, '')::int, 20), 1))
  limit   greatest(coalesce(nullif(page_size, '')::int, 20), 1);
$$;


-- -----------------------------------------------------------------------------
-- 7. Fix `get_users_with_multiple_assessments` stored function
--    Old param names: selected_program_initial, search_query, page_number
--    PersonalDetailsDAL.list_students sends: result_count, program, search, page_size, page
-- -----------------------------------------------------------------------------
drop function if exists public.get_users_with_multiple_assessments(text, text, text, text, text);

create or replace function public.get_users_with_multiple_assessments(
  result_count text,
  program      text,
  search       text,
  page_size    text,
  page         text
)
returns table(
  total_count      bigint,
  user_id          uuid,
  first_name       text,
  middle_name      text,
  last_name        text,
  name_suffix      text,
  student_number   text,
  email            text,
  birth_date       date,
  program_initial  text,
  program_name     text,
  year             smallint,
  marital_status   text,
  is_working_student boolean
)
language sql stable as $$
  with ac as (
    select user_id, count(*)::int as assessment_count
    from public.assessments
    group by user_id
  )
  select
    count(*) over ()  as total_count,
    pd.user_id,
    pd.first_name,
    pd.middle_name,
    pd.last_name,
    pd.name_suffix,
    pd.student_number,
    pd.email,
    pd.birth_date,
    p.initial         as program_initial,
    p.name            as program_name,
    pd.year,
    ms.status         as marital_status,
    pd.is_working_student
  from public.personal_details pd
  left join public.programs p          on p.id  = pd.program_id
  left join public.marital_statuses ms on ms.id = pd.marital_status_id
  left join ac                         on ac.user_id = pd.user_id
  where (result_count is null or result_count = '' or coalesce(ac.assessment_count, 0) = nullif(result_count, '')::int)
    and (program      is null or program      = '' or p.initial = program)
    and (search       is null or search       = '' or concat_ws(' ', pd.first_name, pd.middle_name, pd.last_name, pd.name_suffix, pd.student_number) ilike '%' || search || '%')
  order by pd.first_name, pd.last_name, pd.student_number
  offset ((greatest(coalesce(nullif(page, '')::int, 1), 1) - 1) * greatest(coalesce(nullif(page_size, '')::int, 20), 1))
  limit   greatest(coalesce(nullif(page_size, '')::int, 20), 1);
$$;


-- -----------------------------------------------------------------------------
-- 8. Disable RLS
--    Access control is now handled by Cognito JWT in the Lambda authorizer.
--    No pg-level RLS is needed.
-- -----------------------------------------------------------------------------
alter table public.admin_roles          disable row level security;
alter table public.admins               disable row level security;
alter table public.profiles             disable row level security;
alter table public.programs             disable row level security;
alter table public.marital_statuses     disable row level security;
alter table public.counseling_statuses  disable row level security;
alter table public.assessment_scenarios disable row level security;
alter table public.assessment_domains   disable row level security;
alter table public.personal_details     disable row level security;
alter table public.assessments          disable row level security;
alter table public.apriori_results      disable row level security;
alter table public.assessment_reminders disable row level security;
alter table public.mental_health_uptrend   disable row level security;
alter table public.mental_health_downtrend disable row level security;
alter table public.pay_up               disable row level security;
