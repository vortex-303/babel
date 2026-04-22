-- Passkey credential store. One row per enrolled authenticator.
create table if not exists passkeycredential (
  credential_id text primary key,
  user_id text not null,
  public_key text not null,
  sign_count integer not null default 0,
  transports text,
  label text,
  created_at timestamp without time zone not null default now(),
  last_used_at timestamp without time zone
);
create index if not exists passkeycredential_user_id_idx on passkeycredential (user_id);

-- Short-lived challenge nonces for register + login ceremonies.
create table if not exists passkeychallenge (
  id text primary key,
  challenge text not null,
  kind text not null,
  user_id text,
  email text,
  created_at timestamp without time zone not null default now()
);
create index if not exists passkeychallenge_created_at_idx on passkeychallenge (created_at);
