-- InsightAI schema for Supabase (free tier).
-- Run once in Supabase Dashboard -> SQL Editor -> New query -> Run.
-- Only aggregate metadata, questions and AI outputs are stored; raw school-level data is NOT stored.

create table if not exists public.datasets (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  session_id  text not null,
  file_name   text not null,
  n_rows      integer,
  n_districts integer,
  periods     text
);

create table if not exists public.queries (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  session_id  text not null,
  dataset_id  uuid references public.datasets(id) on delete cascade,
  question    text not null,
  answer      text
);

create table if not exists public.insights (
  id          uuid primary key default gen_random_uuid(),
  created_at  timestamptz not null default now(),
  session_id  text not null,
  dataset_id  uuid references public.datasets(id) on delete cascade,
  kind        text not null,   -- auto_insights | priority_actions | review_brief
  content     text not null
);

create index if not exists queries_session_idx  on public.queries (session_id, created_at desc);
create index if not exists insights_session_idx on public.insights (session_id, created_at desc);
create index if not exists datasets_session_idx on public.datasets (session_id, created_at desc);

-- Row Level Security: the Streamlit server uses the *service_role* key (kept in Streamlit
-- secrets, never sent to the browser), which bypasses RLS. Enabling RLS with no public
-- policies means the anon key cannot read or write anything.
alter table public.datasets enable row level security;
alter table public.queries  enable row level security;
alter table public.insights enable row level security;
