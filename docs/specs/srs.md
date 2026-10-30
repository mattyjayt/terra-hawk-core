---
id: SRS-GARDEN
title: Garden — requirements
status: Draft
owner: Argos (draft) · Jaime (approver)
updated: 2026-10-30
---
# SRS-GARDEN

| ID | Requirement | Prio | Verified by |
|---|---|---|---|
| REQ-GARDEN-001 | Devices shall publish telemetry per IF-MQTT-V1 every 10–60 s. | M | TC-GARDEN-001 |
| REQ-GARDEN-002 | Devices shall publish a retained `state` with an LWT so offline devices are visible. | M | TC-GARDEN-002 |
| REQ-GARDEN-003 | The ingest service shall validate payloads against the v1 schema and reject invalid ones with a logged reason. | M | TC-GARDEN-003 |
| REQ-GARDEN-004 | The ingest service shall write raw readings and maintain `latest` within 2 s of receipt. | M | TC-GARDEN-004 |
| REQ-GARDEN-005 | A scheduled job shall compute 5-minute aggregates and delete raw readings older than 14 days. | M | TC-GARDEN-005 |
| REQ-GARDEN-006 | Commands from the web shall be recorded in `commands` and acknowledged by the device. | S | TC-GARDEN-006 |
| REQ-GARDEN-007 | Pumps shall stop after a firmware-enforced max-on-time regardless of commands. | M | TC-GARDEN-007 |
| REQ-GARDEN-008 | No credentials shall be stored in source code; secrets come from untracked headers/env. | M | TC-GARDEN-008 |
| REQ-GARDEN-009 | The ingest service shall reconnect to MQTT and Supabase automatically with backoff. | M | TC-GARDEN-009 |
| REQ-GARDEN-010 | The ingest service shall run as a supervised service (systemd or pm2) on the Pi. | S | TC-GARDEN-010 |
