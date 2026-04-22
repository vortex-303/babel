-- Profile table — one row per authenticated user. user_id matches
-- auth.users.id (UUID) but we store as text for easy admin joins.
create table if not exists profile (
  user_id text primary key,
  email text,
  credits_balance integer not null default 0,
  credits_used integer not null default 0,
  created_at timestamp without time zone not null default now(),
  updated_at timestamp without time zone not null default now()
);

-- Append-only audit of every credit movement.
create table if not exists creditledger (
  id serial primary key,
  user_id text not null,
  delta integer not null,
  reason text not null,
  job_id integer references job(id),
  stripe_session_id text,
  created_at timestamp without time zone not null default now()
);

create index if not exists creditledger_user_id_idx on creditledger (user_id);
create index if not exists creditledger_stripe_session_id_idx on creditledger (stripe_session_id);
