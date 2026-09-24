-- Maps a WorkOS Organization (one per customer, holding their SSO
-- connection) to our own tenant. Set by hand for now - Phase 3's admin
-- console is where a real onboarding flow will write this.
alter table tenants add column if not exists workos_organization_id text unique;
