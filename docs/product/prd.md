---
id: PRD-GARDEN
title: Garden — product requirements
status: Draft
owner: Argos (draft) · Jaime (approver)
updated: 2026-10-30
---

# PRD-GARDEN — Garden product requirements
## Problem
Seedlings in the chamber and plants in the flat hydroponic channel need monitored, partly automated care, and their history should be visible on terra-hawk.com. The garden must keep working when the Pi (on the Scout) is off.
## Goals
| ID | Goal | Metric |
|---|---|---|
| G-GARDEN-1 | Live telemetry | climate, pH and soil visible on the web < 5 s after measurement |
| G-GARDEN-2 | History | 5-minute aggregates kept ≥ 1 year; raw data 14 days |
| G-GARDEN-3 | Safe actuation | pumps run only with a max-on-time enforced on the MCU, even offline |
| G-GARDEN-4 | One data contract | every device, the ingest service and the UI use IF-MQTT-V1 / IF-DB-SCHEMA |
## Non-goals
Garden vision and timelapse (parked) · aeroponic tower (later) · cloud hosting of the ingest service (after it's proven on the Pi).
## Architecture
Option B (ADR-010): MCU → MQTT (HiveMQ) → ingest (Pi, later the cloud) → Supabase → web.
