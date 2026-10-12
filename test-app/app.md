# EquipFlow — multi-tenant equipment maintenance and field service application

## Overview

EquipFlow is a multi-tenant SaaS application for equipment maintenance and field
service management. Organizations manage customers, customer sites, and
equipment; field technicians receive and complete work orders generated from
service requests and preventive maintenance schedules.

## First release (Phase 1)

Entities, in dependency order:

1. **Organizations** — tenant root. `name`, `slug` (unique), `created_at`.
2. **Users** — belong to an organization. `email` (unique), `name`, `role`
   (`admin | manager | technician`), `password_hash`.
3. **Customer sites** — belong to an org; a named physical location with
   `address`, `city`, `region` (nullable).
4. **Equipment** — belongs to an org and a site. `name`, `serial` (unique per
   org), `model`, `installed_at` (nullable), `status`
   (`operational | degraded | down | retired`).
5. **Service requests** — raised against equipment. `title`, `description`,
   `priority` (`low | medium | high | urgent`), `status`
   (`open | triaged | converted | closed`).
6. **Work orders** — the actionable unit. `code` (human-readable, e.g.
   `WO-2026-0001`), `title`, `description`, `type`
   (`corrective | preventive | inspection`), `priority`,
   `status` (`draft | scheduled | in_progress | blocked | completed | cancelled`),
   `assigned_technician_id` (nullable, must be a technician in the same org),
   `site_id`, `equipment_id`, `scheduled_for` (nullable timestamp).

## Valid work-order transitions

```
draft → scheduled | cancelled
scheduled → in_progress | cancelled
in_progress → blocked | completed | cancelled
blocked → in_progress | cancelled
```

No other transition is valid; invalid transitions return 409 with
`{ error: 'Invalid transition' }`.

## Permissions

- `admin` — full CRUD on all org resources; org management.
- `manager` — CRUD on sites/equipment/requests/WOs; assign technicians.
- `technician` — read sites/equipment/requests; update assigned WO status
  (in_progress → blocked/completed only); no create/delete on resources.
- Cross-org access is always 404 (never 403 — do not leak existence).

## Tenant isolation

- Every table carries `org_id`; every query filters by the authenticated
  user's org.
- Uniqueness scopes: `users.email` global; `orgs.slug` global;
  `equipment.serial` unique per org; work-order `code` unique per org.
- Evidence: cross-org GET/PUT/DELETE returns 404; same-org returns 200.

## Data model & migrations

- Plain SQL migrations under `migrations/`, numbered `NNN_name.sql`, applied
  in order by `scripts/migrate.sh` (records applied files in
  `schema_migrations`).
- Migration 001 creates orgs, users, customer_sites, equipment.
- Migration 002 adds service_requests, work_orders (+ FKs and indexes).
- Preservation: applying 002 to a DB seeded with 001 data must not lose or
  alter existing rows (verified by test).

## Non-goals (Phase 1)

Parts inventory, scheduling backlog, preventive-maintenance scheduling,
offline technician updates, third-party integrations — tracked in backlog.md.
