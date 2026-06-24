---
name: resell-sequence
description: >
  Generate the 12-month monthly resell / retention email sequence for a med spa client in
  GoHighLevel (GHL). Use this skill whenever the user wants to create, build, fill out, or push
  the monthly follow-up emails, the "Automated Monthly" series, a monthly resell/retention/nurture
  email sequence, or month-specific marketing emails for a med spa — for one month, several, or the
  whole year, in English and Spanish. Also trigger for "set up the monthly emails for [client]",
  "build the resell sequence", "add the missing months", or fixing/refreshing an existing
  Automated Monthly series. This is part of delivery for the Full System ($697/mo) package.
---

# Monthly Resell Email Sequence

Builds (or repairs) a med spa's **12-month resell/retention email series** in GHL: **3 emails per month, English + Spanish**, educational by default with 5 offer months. The **copy defaults live in the Second Brain** — this skill grabs them from the vault, personalizes per client, and pushes to GHL using the `ghl-email-templates` mechanics.

## Where everything lives (read these first)

- **Email defaults (the copy):** `Vault\wiki\content\Monthly Resell Email Sequence.md` (`[[Monthly Resell Email Sequence]]`). This is the canonical 12×3 library — always pull the copy from here, don't invent it.
- **Per-client fill-in checklist:** `Vault\wiki\operations\Monthly Resell Email Fill-In Checklist.md` (`[[Monthly Resell Email Fill-In Checklist]]`). Tells you what client-specific data to collect.
- **Delivery context:** `Vault\wiki\operations\Client Onboarding Checklists.md` → **Full System ($697/mo)** package. This sequence is a delivery item there.
- **Push mechanics:** the `ghl-email-templates` skill (GHL Email Builder API: POST shell → PATCH content → v2 rename). Reuse it; don't re-implement.

## Template naming convention (MUST match exactly)

GHL templates in the existing series are named:

```
Automated Monthly - {Month} - Email {N}              ← English
Automated Monthly - {Month} - Email {N} - Spanish    ← Spanish
```

- `{N}` = 1, 2, or 3.
- `{Month}` tokens — **match the existing account exactly.** The existing series abbreviates February as **`Feb`** and spells every other month in full. Use this map:

  | Month | Token | | Month | Token |
  |---|---|---|---|---|
  | January | `January` | | July | `July` |
  | February | `Feb` ⚠️ | | August | `August` |
  | March | `March` | | September | `September` |
  | April | `April` | | October | `October` |
  | May | `May` | | November | `November` |
  | June | `June` | | December | `December` |

- Before creating, **list existing templates** (`GET /emails/builder?locationId=...`) and reuse the exact token style already present so you don't create duplicates with mismatched names.

## Workflow

### Step 1 — Resolve client + load context
- Find the client folder under `C:\Users\horac\Claude\Clients\` (closest-name match). No folder → they aren't onboarded; offer `client-onboarding` first.
- Read `ghl-credentials.md` → `token` + `locationId` (stop and ask if either is a placeholder).
- Read `brand-context.md` (logo, colors, tone) and any `monthly-email-checklist.md` already in the folder.
- Optionally `GET /locations/{locationId}` to confirm business name/address/email/phone/timezone (these auto-fill the merge fields).

### Step 2 — Decide scope
Ask (or infer from the request) which months to build:
- **Whole year** (new client), **specific months**, or **fix/refresh** existing ones.
- Always **list existing templates first** so you know what's already there. Build only what's missing unless told to overwrite.

### Step 3 — Pull defaults + personalize
For each month/email in scope, take the copy from `[[Monthly Resell Email Sequence]]` and apply the **fill-in checklist**:
- Merge fields stay as-is (`{{contact.first_name}}`, `{{location.name}}`, `{{location.email}}`, `{{right_now.year}}`) — GHL fills them.
- **CTA rules (already baked into the defaults):** educational months → no CTA on E1/E2, one soft CTA on E3 (booking link for Jan/Mar/Aug, "just reply" for Apr/Jun/Jul/Oct). Offer months → hard 👉 CTA on E1 + E3 only; E2 is a no-CTA "questions answered" explainer.
- **Offer months (Feb/May/Sep/Nov/Dec):** replace `[SERVICE]` / `[XX% off]` / `[OFFER]` / `[DATE]` with the client's real promo. **Confirm the client offers that treatment** (esp. laser for Sep) — if not, swap the service or use the educational fallback (italic lines in the defaults).
- Wire the client's **booking URL** into every CTA and the soft booking links.
- Apply brand **logo + colors** to the template shell (pull from website/brand board — never guess; never carry another client's address/phone/hours).

### Step 4 — Preview, confirm, push
- Follow `ghl-email-templates`: generate HTML, show a visual preview, get explicit approval **before any API call**.
- Create each template with the **exact name** from the convention above (English first, then ` - Spanish`).
- Spanish = a faithful translation of the same email (match the existing bilingual pattern). Keep merge fields and structure identical.

### Step 5 — Bookkeeping
- Update the client's `monthly-email-checklist.md` (check off what's done, note what's blocked on missing input like booking URL or laser confirmation).
- If this ran as part of delivery, check off **"monthly resell email sequence"** in the client's `onboarding-checklist.md`.

## Common jobs
- **New Full System client:** build all 12 months × 3 × (EN+ES) = 72 templates.
- **Add missing months:** e.g. Jan, Sep, Oct, Nov, Dec for a client who already has Feb–Aug.
- **Fix defects:** wrong/stale copy, missing Email 3, or a Spanish body sitting in an English template — regenerate just those.

## Guardrails
- Never push to GHL without showing a preview and getting explicit approval.
- Never invent copy — pull from the vault defaults and adapt.
- Never guess brand colors or carry a previous client's business info into a template.
- Keep the naming convention exact (it's how the GHL automation/workflow finds the templates).
