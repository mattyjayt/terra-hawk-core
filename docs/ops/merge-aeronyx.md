---
id: RB-MERGE
title: Runbook: merge aeronyx-backend into terra-hawk-core
status: Draft
owner: Argos (draft) · Jaime (approver)
updated: 2026-10-30
---

# RB-MERGE — merge aeronyx-backend (history preserved)
**Do not run until DD-GARDEN-INGEST is approved.**
```bash
cd ~/Projects/TerraHawk/terra-hawk-core
git checkout -b feat/merge-aeronyx
git subtree add --prefix=legacy/aeronyx-backend https://github.com/mattyjayt/aeronyx-backend.git main
# then move/refactor: legacy/aeronyx-backend/src/aeronyx_backend/mqtt*.py → services/ingest/
# keep its docs style → docs/; drop SQLite history (replaced by Supabase)
```
After merge: open a PR, archive `aeronyx-backend` on GitHub (Settings → Archive) and add a README pointer.
