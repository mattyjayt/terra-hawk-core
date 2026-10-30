---
id: IF-DB-SCHEMA
title: Supabase schema v1
status: Draft
owner: Argos (draft) · Jaime (approver)
updated: 2026-10-30
---

# IF-DB-SCHEMA — Supabase (Postgres) schema v1
ERD: [diagrams/data-model-v1](../../diagrams/data-model-v1/data-model-v1.html). Columns are the first proposal; **check them against the live `terra-hawk-db` before approval** (profiles / user_roles / subscribers already exist).

| Table | Columns | Retention |
|---|---|---|
| systems | id text PK, name, kind, location, created_at | — |
| devices | id text PK, system_id → systems, kind, firmware, online bool, last_seen, created_at | — |
| readings | id bigint PK, ts timestamptz, device_id → devices, key text, value double, received_at | 14 days |
| readings_5m | (bucket, device_id, key) PK, min, avg, max, n | long-term |
| latest (view) | device_id, key, ts, value | — |
| events | id bigint PK, ts, device_id, kind, severity, payload jsonb | long-term |
| commands | id bigint PK, ts, device_id, action, params jsonb, source, issued_by → profiles, status, acked_at, result jsonb | long-term |
| detections *(parked)* | id, ts, system_id, source, label, confidence, bbox jsonb, image_id | 30 days |
| images *(parked)* | id uuid, ts, system_id, device_id, storage_path, keep | rolling |
RLS: viewers read; operators insert commands; only the ingest service role writes readings/events.
