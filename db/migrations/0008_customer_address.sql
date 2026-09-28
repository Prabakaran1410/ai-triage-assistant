-- Approved replies had nowhere to go: a triage event recorded what a
-- customer asked and what we would answer, but never who they were. The
-- console's "Send to customer" therefore set a status and transmitted
-- nothing.
--
-- Nullable on purpose. A message can legitimately arrive without a reply
-- address (a web form, an internal test), and that is not an error - it
-- just means the reply cannot be delivered, which the console now says
-- rather than offering a button that does nothing.
alter table triage_events add column if not exists customer_email text;
