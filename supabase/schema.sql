-- Run this once in Supabase: Dashboard -> SQL Editor -> New query -> paste -> Run

create table if not exists audit_log (
  id         bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  username   text not null,
  action     text not null,
  target     text default ''
);

create table if not exists incident_overrides (
  incident_id text primary key,
  status      text,
  assignee    text,
  root_cause  text,
  resolved_at timestamptz,
  updated_at  timestamptz not null default now()
);

create table if not exists maintenance_windows (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  scope       text not null,
  start_time  text,
  end_time    text,
  reason      text,
  approved_by text default 'Pending approval'
);

-- Row Level Security: ON, with no public policies.
-- The app uses the *service_role* key from Streamlit secrets (server side only),
-- which bypasses RLS, so nobody can read or write these tables with the public anon key.
alter table audit_log           enable row level security;
alter table incident_overrides  enable row level security;
alter table maintenance_windows enable row level security;
