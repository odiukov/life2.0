-- Widen alert_emissions uniqueness from (rule_id) to (user_id, rule_id).
--
-- The 20260421130000_add_user_id migration added user_id to alert_emissions
-- but only created a non-unique secondary index on (user_id, rule_id), leaving
-- the original PRIMARY KEY (rule_id) in place. shared.db.upsert_alert_emission
-- does ON CONFLICT (user_id, rule_id) → InvalidColumnReferenceError.
--
-- Fix: drop the rule_id PK and replace with a composite (user_id, rule_id) PK.
BEGIN;

ALTER TABLE public.alert_emissions DROP CONSTRAINT IF EXISTS alert_emissions_pkey;
ALTER TABLE public.alert_emissions ADD CONSTRAINT alert_emissions_pkey
  PRIMARY KEY (user_id, rule_id);

COMMIT;
