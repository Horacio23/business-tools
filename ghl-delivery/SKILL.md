---
name: ghl-delivery
description: >
  Run GHL delivery work for an onboarded client: update reminder email templates
  with their theme + business info, create calendars for each of their services,
  and brand their chat widget with their colors. Use this skill whenever the user
  asks to "do the delivery", "set up GHL", "run onboarding delivery", or asks for
  any of those delivery tasks *for a client* (e.g. "create the calendars for
  Dermaluxe", "brand the widget for Advanced Hair", "set up the reminder emails
  for the new client"). It loads the client's credentials and brand context, runs
  only the requested tasks via the pure ghl- skills, and checks off the client's
  onboarding checklist. Trigger for one task, several, or "do everything left".
---

# GHL Delivery Orchestrator

Runs delivery tasks for a client by loading their shared context once, then
invoking the relevant pure `ghl-` skills. The tasks are **independent — there is
no required order**. Run one, several, or all, depending on what the user asks.

This skill owns three things the pure skills don't:
1. **Context loading** — client folder, credentials, brand context
2. **Task selection** — which of the delivery tasks to run this time
3. **Bookkeeping** — checking off `onboarding-checklist.md` after each task

## Step 1 — Resolve the client and load context

Identify the client from the user's request. Find their folder under
`C:\Users\horac\Claude\Clients\` (closest-name match). If no folder exists, they
haven't been onboarded — offer the `client-onboarding` skill first.

Read from the client folder:

- **`ghl-credentials.md`** → `token` + `locationId`. If either is a TODO
  placeholder, stop and ask the user for it — nothing can run without them.
- **`brand-context.md`** → logo, website, brand colors, tone.
- **`onboarding-checklist.md`** → package + what's already done. Don't redo
  checked items unless the user explicitly asks.

## Step 2 — Pick the tasks

| Task | Pure skill | Needs from context |
|---|---|---|
| Reminder email templates (theme + business info) | `ghl-email-templates` | credentials, brand colors/logo, business name |
| Calendars — one per service the client offers | `ghl-calendars` | credentials, services list |
| Chat widget branded with client colors | `ghl-chat-widget` | credentials, brand colors |
| Monthly resell email sequence (12mo × 3, EN+ES) — **Full System ($697/mo) only** | `resell-sequence` | credentials, brand colors/logo, booking URL, services list (for offer months) |

The monthly resell sequence is a **Full System ($697/mo)** delivery item, not part of the lower tiers. Only run it when the client's package is Full System (or the user asks for it explicitly). The `resell-sequence` skill pulls its copy from the vault and handles the GHL push itself.

- If the user named specific tasks, run exactly those.
- If the user said "do the delivery" / "do everything left", run all tasks that
  are still unchecked on the checklist.
- Tasks are independent — any order is fine.

**Input gating (the only soft dependency):**
- **Brand colors missing** in `brand-context.md` → the email-template theming and
  widget tasks can't produce on-brand output. Ask the user for the palette (or a
  logo to pull it from) before running those two. **Calendars can proceed** —
  they only need the services list.
- **Services list unknown** → ask the user (or check `brand-context.md` /
  the client's website) before the calendar task.

When you learn new brand facts mid-delivery (colors, services, tone), **write
them back to `brand-context.md`** so the next task and future sessions have them.

## Step 3 — Run each task via its pure skill

Invoke the matching `ghl-` skill for each selected task and follow it as written.
Pass along the loaded context (token, locationId, brand colors, business info) so
the skill doesn't re-ask for what's already known.

Skill-specific notes:
- **Calendars:** create one calendar per service. Remember calendar slugs are
  globally unique across GHL — suffix slugs with the client name.
- **Widget:** use the client's palette from `brand-context.md`; the
  `ghl-chat-widget` skill knows the API mechanics.
- **Email templates:** apply the brand theme (colors/logo) and the client's
  business information (name, address, phone, booking link) to the reminder
  templates.

## Step 4 — Bookkeeping

After **each** task completes (not just at the end):

1. Check off the matching item in the client's `onboarding-checklist.md`
   (`- [ ]` → `- [x]`, optionally append the date).
2. If the checklist doesn't have an item for a task you ran, add it as checked —
   and consider whether the package checklist in
   `Vault\wiki\operations\Client Onboarding Checklists.md` is missing it too.

Finish by reporting: which tasks ran, what was created/updated in GHL, the
checklist state, and anything still blocked on missing input.

## Notes

- Keep this skill thin. The *how* of each task lives in the pure `ghl-` skills;
  the *standard scope per package* lives in the vault SOP
  (`Client Onboarding Checklists.md`). Edit those, not this file, when mechanics
  or scope change.
- This skill never invents credentials or colors. Missing input → ask.
