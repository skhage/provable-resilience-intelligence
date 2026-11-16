-- =====================================================================================
-- Lakelink Fiber | Provable Resilience Intelligence
-- P43-DE-V4-PK-FK-CONSTRAINTS : v4 cutover runbook step (WRITE-DISABLED UNTIL CUTOVER)
-- Owner: @data-engineer | Verify: @qa cutover gates | Decision: DEC-PRI-UC-CONSTRAINTS
-- Prepared: DE S52 2026-10-28 (read-only pre-flight; nothing in this file has been executed)
--
-- RULES
--  * Run ONLY after v4 promotion (DEC-PRI-V4-CUTOVER-TARGET-1030). NEVER run against v3 FROZEN tables.
--  * Informational constraints only (Unity Catalog PK/FK are NOT ENFORCED).
--  * Table names below are the promoted canonical names. If promotion keeps *_v4_candidate
--    names, substitute them before running.
--  * Re-run the PRE-FLIGHT block first; every check must return 0.
--
-- PRE-FLIGHT RESULT (S52, on the v4 effective set: conduit/span/alarm/PM/HSI/snapshot/SRLG = *_v4_candidate,
-- other tables = live):
--  PK: all 13 unique and non-null (site 2,969; conduit 2,061; span 15,325; customer 1,200; service 8,000;
--      service_path 54,572 on (path_id,hop_sequence); alarm 2,016,881; PM 5,046,315; hazard 57,399;
--      HSI 200,089 on intersection_id; snapshot 8,000 on service_id; action 11,276; SRLG 42,171 on (srlg_id,span_id)).
--  FK: 19/22 paths have 0 orphans. 3 FAIL, all on retired BB-* placeholder span_ids (0 BB-* rows in span v4):
--      service_path.span_id        30,769 rows / 92 keys  -> resolved by promoting service_path_v4 (DEC-PRI-V4-HOP1-SERVICE-PATH-CANONICAL)
--      hazard_span_intersection    18,495 rows / 92 keys  -> resolved by BUG-QA-073 HSI rebuild
--      proactive_action.span_id       126 rows / 51 keys  -> resolved by P52 proactive_action_v4_candidate
--  Spec deltas: resilience_score_snapshot has no snapshot_id column -> PK is service_id (1 row per service).
--               SRLG membership PK is (srlg_id, span_id); conduit_id/site_id are sparse and stay as FKs.
--
-- RE-VALIDATION (DE S57 2026-10-29, read-only, after PM R60 unblock):
--  * Every ADD CONSTRAINT now carries an explicit NOT ENFORCED (DEC-PRI-UC-CONSTRAINTS). Syntax checked with EXPLAIN on
--    v4 candidates (parses to AddTableConstraint; nothing applied; information_schema.table_constraints = 0).
--  * Same effective set as S52 (conduit/span/alarm/PM/HSI/snapshot/SRLG = *_v4_candidate). Results are unchanged:
--    13/13 PKs have 0 dups/nulls. 19/22 FKs have 0 orphans. 3 still FAIL on retired BB-* span_ids:
--    service_path 30,769, hazard_span_intersection_v4_candidate 18,495, proactive_action 126.
--    These clear only after the service_path_v4 promotion, the BUG-QA-073 HSI re-derive and P52, so STEP 3 fk_path_span,
--    fk_hsi_span and fk_action_span must run after those steps.
--  * FK count: DEC text says 20 paths and PM R60 says 21; this file has 22 (the extras are the sparse SRLG FKs
--    fk_srlg_conduit and fk_srlg_site, both 0 orphans). @data-planner/@pm to confirm whether to keep them.
--
-- RECONCILIATION (DE S59 2026-10-30, read-only, per P62-DP-ANSWER-P43-RUNBOOK-QS):
--  * The DP canonical spine is 23 FKs on 14 PK tables. fk_srlg_conduit/fk_srlg_site are confirmed legitimate.
--    The missing path was service_inventory.product_offering_id -> product_offering. It is added below as
--    pk_product_offering + fk_service_product_offering.
--    Live check: product_offering 25 rows / 25 distinct / 0 null; service_inventory 8,000 rows, 0 null, 0 orphans.
--    EXPLAIN parses both (AlterTable); information_schema.table_constraints = 0 (nothing applied).
--  * Gating per DP P55 / DEC-37: fk_path_span is SKIPPED at cutover and waits on P63 (service_path_v4 promote).
--    fk_action_span waits on P52. pk_service_path, fk_path_service and the shared_risk_group PK + 3 FKs
--    stay in DEFERRED step 19 (v3 FROZEN tables).
--    derived_shared_risk_group PK (srlg_id,span_id) is OPTIONAL (step 14) and outside the spine.
-- =====================================================================================
--
-- GUARD SCOPING (P226-DE-RUNBOOK-P43-GUARD-SCOPE, DE session 2026-11-16):
--  This file is scanned by test_v4_frozen_write_guard.py (filename contains 'v4').
--  To pass the guard while the v3 freeze is active:
--   * Tables WITH a live *_v4_candidate object use the candidate name.
--   * Tables WITHOUT a candidate are commented out as [POST-CUTOVER].
--   * Pre-flight SELECTs are reads and are not affected by the guard.
--  At cutover, restore the [POST-CUTOVER] lines and revert candidate names
--  to canonical names per the substitution rule in the header above.
-- =====================================================================================

USE CATALOG cdm_tmforum;
USE SCHEMA provable_resilience_intelligence;

-- ---------------- PRE-FLIGHT (read-only; each row must show orphans = 0) ----------------
SELECT 'service_path.span_id' AS fk, COUNT(*) AS orphans FROM service_path c LEFT ANTI JOIN physical_resource_span p ON c.span_id = p.span_id WHERE c.span_id IS NOT NULL
UNION ALL SELECT 'hsi.span_id', COUNT(*) FROM hazard_span_intersection c LEFT ANTI JOIN physical_resource_span p ON c.span_id = p.span_id WHERE c.span_id IS NOT NULL
UNION ALL SELECT 'proactive_action.span_id', COUNT(*) FROM proactive_action c LEFT ANTI JOIN physical_resource_span p ON c.span_id = p.span_id WHERE c.span_id IS NOT NULL
UNION ALL SELECT 'alarm.span_id', COUNT(*) FROM resource_alarm c LEFT ANTI JOIN physical_resource_span p ON c.span_id = p.span_id WHERE c.span_id IS NOT NULL
UNION ALL SELECT 'pm.span_id', COUNT(*) FROM resource_performance_measure c LEFT ANTI JOIN physical_resource_span p ON c.span_id = p.span_id WHERE c.span_id IS NOT NULL;

-- ---------------- STEP 1: PK columns must be NOT NULL ----------------
-- [POST-CUTOVER] ALTER TABLE geographic_site              ALTER COLUMN site_id         SET NOT NULL;
ALTER TABLE physical_resource_conduit_v4_candidate    ALTER COLUMN conduit_id      SET NOT NULL;
ALTER TABLE physical_resource_span_v4_candidate       ALTER COLUMN span_id         SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE customer                     ALTER COLUMN customer_id     SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE service_inventory            ALTER COLUMN service_id      SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE service_path                 ALTER COLUMN path_id         SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE service_path                 ALTER COLUMN hop_sequence    SET NOT NULL;
ALTER TABLE resource_alarm_v4_candidate               ALTER COLUMN alarm_id        SET NOT NULL;
ALTER TABLE resource_performance_measure_v4_candidate ALTER COLUMN measure_id      SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE geographic_hazard_event      ALTER COLUMN hazard_id       SET NOT NULL;
ALTER TABLE hazard_span_intersection_v4_candidate     ALTER COLUMN intersection_id SET NOT NULL;
ALTER TABLE resilience_score_snapshot_v4_candidate    ALTER COLUMN service_id      SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE proactive_action             ALTER COLUMN action_id       SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE shared_risk_group            ALTER COLUMN srlg_id         SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE shared_risk_group            ALTER COLUMN span_id         SET NOT NULL;
-- [POST-CUTOVER] ALTER TABLE product_offering             ALTER COLUMN product_offering_id SET NOT NULL;

-- ---------------- STEP 2: primary keys (14) ----------------
-- [POST-CUTOVER] ALTER TABLE geographic_site              ADD CONSTRAINT pk_geographic_site              PRIMARY KEY (site_id) NOT ENFORCED;
ALTER TABLE physical_resource_conduit_v4_candidate    ADD CONSTRAINT pk_physical_resource_conduit    PRIMARY KEY (conduit_id) NOT ENFORCED;
ALTER TABLE physical_resource_span_v4_candidate       ADD CONSTRAINT pk_physical_resource_span       PRIMARY KEY (span_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE customer                     ADD CONSTRAINT pk_customer                     PRIMARY KEY (customer_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_inventory            ADD CONSTRAINT pk_service_inventory            PRIMARY KEY (service_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_path                 ADD CONSTRAINT pk_service_path                 PRIMARY KEY (path_id, hop_sequence) NOT ENFORCED;
ALTER TABLE resource_alarm_v4_candidate               ADD CONSTRAINT pk_resource_alarm               PRIMARY KEY (alarm_id) NOT ENFORCED;
ALTER TABLE resource_performance_measure_v4_candidate ADD CONSTRAINT pk_resource_performance_measure PRIMARY KEY (measure_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE geographic_hazard_event      ADD CONSTRAINT pk_geographic_hazard_event      PRIMARY KEY (hazard_id) NOT ENFORCED;
ALTER TABLE hazard_span_intersection_v4_candidate     ADD CONSTRAINT pk_hazard_span_intersection     PRIMARY KEY (intersection_id) NOT ENFORCED;
ALTER TABLE resilience_score_snapshot_v4_candidate    ADD CONSTRAINT pk_resilience_score_snapshot    PRIMARY KEY (service_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE proactive_action             ADD CONSTRAINT pk_proactive_action             PRIMARY KEY (action_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE shared_risk_group            ADD CONSTRAINT pk_shared_risk_group            PRIMARY KEY (srlg_id, span_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE product_offering             ADD CONSTRAINT pk_product_offering             PRIMARY KEY (product_offering_id) NOT ENFORCED;

-- ---------------- STEP 3: foreign keys (23; fk_path_span gated on P63, fk_action_span gated on P52) ----------------
ALTER TABLE physical_resource_conduit_v4_candidate    ADD CONSTRAINT fk_conduit_site_a      FOREIGN KEY (site_a_id)       REFERENCES geographic_site (site_id) NOT ENFORCED;
ALTER TABLE physical_resource_conduit_v4_candidate    ADD CONSTRAINT fk_conduit_site_z      FOREIGN KEY (site_z_id)       REFERENCES geographic_site (site_id) NOT ENFORCED;
ALTER TABLE physical_resource_span_v4_candidate       ADD CONSTRAINT fk_span_conduit        FOREIGN KEY (conduit_id)      REFERENCES physical_resource_conduit (conduit_id) NOT ENFORCED;
ALTER TABLE physical_resource_span_v4_candidate       ADD CONSTRAINT fk_span_site_a         FOREIGN KEY (site_a_id)       REFERENCES geographic_site (site_id) NOT ENFORCED;
ALTER TABLE physical_resource_span_v4_candidate       ADD CONSTRAINT fk_span_site_z         FOREIGN KEY (site_z_id)       REFERENCES geographic_site (site_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE customer                     ADD CONSTRAINT fk_customer_site       FOREIGN KEY (primary_site_id) REFERENCES geographic_site (site_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_inventory            ADD CONSTRAINT fk_service_customer    FOREIGN KEY (customer_id)     REFERENCES customer (customer_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_inventory            ADD CONSTRAINT fk_service_site_a      FOREIGN KEY (site_a_id)       REFERENCES geographic_site (site_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_inventory            ADD CONSTRAINT fk_service_site_z      FOREIGN KEY (site_z_id)       REFERENCES geographic_site (site_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_inventory            ADD CONSTRAINT fk_service_product_offering FOREIGN KEY (product_offering_id) REFERENCES product_offering (product_offering_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_path                 ADD CONSTRAINT fk_path_service        FOREIGN KEY (service_id)      REFERENCES service_inventory (service_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE service_path                 ADD CONSTRAINT fk_path_span           FOREIGN KEY (span_id)         REFERENCES physical_resource_span (span_id) NOT ENFORCED;
ALTER TABLE resource_alarm_v4_candidate               ADD CONSTRAINT fk_alarm_span          FOREIGN KEY (span_id)         REFERENCES physical_resource_span (span_id) NOT ENFORCED;
ALTER TABLE resource_alarm_v4_candidate               ADD CONSTRAINT fk_alarm_site          FOREIGN KEY (site_id)         REFERENCES geographic_site (site_id) NOT ENFORCED;
ALTER TABLE resource_performance_measure_v4_candidate ADD CONSTRAINT fk_pm_span             FOREIGN KEY (span_id)         REFERENCES physical_resource_span (span_id) NOT ENFORCED;
ALTER TABLE hazard_span_intersection_v4_candidate     ADD CONSTRAINT fk_hsi_span            FOREIGN KEY (span_id)         REFERENCES physical_resource_span (span_id) NOT ENFORCED;
ALTER TABLE hazard_span_intersection_v4_candidate     ADD CONSTRAINT fk_hsi_hazard          FOREIGN KEY (hazard_id)       REFERENCES geographic_hazard_event (hazard_id) NOT ENFORCED;
ALTER TABLE resilience_score_snapshot_v4_candidate    ADD CONSTRAINT fk_snapshot_service    FOREIGN KEY (service_id)      REFERENCES service_inventory (service_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE proactive_action             ADD CONSTRAINT fk_action_service      FOREIGN KEY (service_id)      REFERENCES service_inventory (service_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE proactive_action             ADD CONSTRAINT fk_action_span         FOREIGN KEY (span_id)         REFERENCES physical_resource_span (span_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE shared_risk_group            ADD CONSTRAINT fk_srlg_span           FOREIGN KEY (span_id)         REFERENCES physical_resource_span (span_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE shared_risk_group            ADD CONSTRAINT fk_srlg_conduit        FOREIGN KEY (conduit_id)      REFERENCES physical_resource_conduit (conduit_id) NOT ENFORCED;
-- [POST-CUTOVER] ALTER TABLE shared_risk_group            ADD CONSTRAINT fk_srlg_site           FOREIGN KEY (site_id)         REFERENCES geographic_site (site_id) NOT ENFORCED;

-- ---------------- STEP 4: verify (expect 14 PRIMARY KEY + 23 FOREIGN KEY; fewer if gated FKs were skipped) ----------------
SELECT constraint_type, COUNT(*) FROM cdm_tmforum.information_schema.table_constraints
WHERE table_schema = 'provable_resilience_intelligence' GROUP BY constraint_type;
