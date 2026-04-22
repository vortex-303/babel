alter table profile
  add column if not exists self_host_license boolean not null default false;
