---
name: ghl-chat-widget
description: >
  Read and update existing chat widgets on GoHighLevel (GHL), especially their colors/theme.
  Use this skill whenever the user wants to view a GHL chat widget's settings, list the chat
  widgets on a location, change a chat widget's colors (chat bubble, header, background, buttons,
  message bubbles, avatar), match a widget to brand colors, or update chat widget styling/theme in
  GoHighLevel/GHL/HighLevel. Also trigger when the user mentions reading, editing, or recoloring a
  chat widget, web chat widget, or live chat widget in a GHL context.
---

# GHL Chat Widget — Read & Update

Read, list, and update GoHighLevel chat widgets (primarily colors/theme) via the GHL API v2.

> Full reference + the story of how these endpoints were discovered: vault page **GHL Chat Widget API** (`wiki/operations/`).

## Credentials

**Always ask the user which location/client to run for before doing anything else.** Each client has their own token + location ID at `C:\Users\horac\Claude\Clients\{ClientName}\GHL Credentials.txt`. The Cyber Popular account credentials are at `C:\Users\horac\Claude\High Level Credentials.txt`.

1. Ask: "Which GHL location/client should I use for this?" (or confirm if clear from context).
2. Read the corresponding credentials file (format: `Location Id: ...` and `Token: ...`).
3. Set `GHL_LOCATION_ID` and `GHL_PRIVATE_TOKEN`.

If the file is empty/missing, ask the user for the token and location ID directly.

## API basics

- **Base URL**: `https://services.leadconnectorhq.com`
- **Headers** on every request:
  - `Authorization: Bearer <GHL_PRIVATE_TOKEN>`
  - `Version: 2021-07-28`
  - `Content-Type: application/json`
  - `Accept: application/json`
- Use `curl` for calls. Python is often NOT available on this machine — do not pipe to `python3`. Use `grep`/`jq` (if present) or just print the raw JSON.

## What a Private Integration Token (PIT) can do

| Operation | Route | Status |
|---|---|---|
| **List widgets** | `GET /chat-widget/list?locationId={loc}&limit=20&offset=0` | ✅ `limit`+`offset` REQUIRED (else 422) |
| **Read one widget** | `GET /chat-widget/{id}` | ⛔ 401 IAM-blocked for PIT — do not use |
| **Read (workaround)** | `PATCH /chat-widget/data/{loc}/{id}` body `{}` | ✅ returns full object, no changes |
| **Update** | `PATCH /chat-widget/data/{loc}/{id}` | ✅ partial update |
| **Create** | `POST /chat-widget/?locationId={loc}` | ✅ needs `version`,`chatType`,`name`,`locationId` |

**The update/read path is `/chat-widget/data/{locationId}/{id}` — NOT `/chat-widget/{id}`.**

## Workflow: List widgets

```bash
curl -s "https://services.leadconnectorhq.com/chat-widget/list?locationId={loc}&limit=20&offset=0" \
  -H "Authorization: Bearer {token}" -H "Version: 2021-07-28"
```
Report each widget's `name`, `_id`, `chatType` (`emailChat` vs `liveChat`), and which is `default: true`.

## Workflow: Read a widget

GET-by-id is IAM-blocked, so **read via a no-op PATCH** with an empty body:
```bash
curl -s -X PATCH "https://services.leadconnectorhq.com/chat-widget/data/{loc}/{id}" \
  -H "Authorization: Bearer {token}" -H "Version: 2021-07-28" \
  -H "Content-Type: application/json" -d '{}'
```
Then report the active values — especially `settings.widgetPrimaryColor` and `settings.theme.colors.*`.

## Workflow: Update colors

Colors live in two places under `settings`:
- `settings.widgetPrimaryColor` — overall primary (top-level).
- `settings.theme = { "name": "custom", "colors": { ... } }` — the themeable map. **`name` must be `"custom"`** to use custom colors.

**Exact `colors` keys** (any other key name is silently dropped):

| Key | Controls |
|---|---|
| `chatBubbleColor` | Floating launcher bubble |
| `headerColor` | Header bar |
| `backgroundColor` | Chat window background |
| `buttonColor` | Send / CTA buttons |
| `senderMessageColor` | Visitor's message boxes |
| `receivedMessageColor` | Agent's message boxes |
| `avatarBackgroundColor` | Avatar background |
| `avatarBorderColor` | Avatar ring |

(Separately, `settings.advanceSettings.voiceAiAnimationColor` controls the Voice-AI animation accent — NOT part of `theme.colors`.)

**Steps:**
1. **Read first** (no-op PATCH) to get the current `theme.colors` object.
2. **Confirm the color → field mapping with the user** before writing (show a table of which hex goes where). If matching a brand/site, pull the brand hex values first.
3. **Read-modify-write the whole `colors` object** — resend every color key, not just the changed ones (the `colors` sub-object is not reliably deep-merged). Sibling `settings` fields like `advanceSettings` DO survive a partial PATCH, so you only need to send `settings.widgetPrimaryColor` + `settings.theme`.
4. **PATCH:**
   ```bash
   curl -s -X PATCH "https://services.leadconnectorhq.com/chat-widget/data/{loc}/{id}" \
     -H "Authorization: Bearer {token}" -H "Version: 2021-07-28" \
     -H "Content-Type: application/json" \
     -d '{"settings":{"widgetPrimaryColor":"#HEX","theme":{"name":"custom","colors":{
           "chatBubbleColor":"#HEX","headerColor":"#HEX","backgroundColor":"#HEX",
           "buttonColor":"#HEX","avatarBackgroundColor":"#HEX","avatarBorderColor":"#HEX",
           "senderMessageColor":"#HEX","receivedMessageColor":"#HEX"}}}}'
   ```
5. **Verify** the response echoes back the colors you sent (stripped keys = wrong key name). Confirm `advanceSettings.aTwoPCompliance` is still present.
6. **Report** the final color set as a table and tell the user to confirm contrast in **GHL → Sites → Chat Widget → {widget}**.

## Critical safety rules

- **Never wipe the A2P compliance block.** `settings.advanceSettings.aTwoPCompliance` holds legal opt-in text. It deep-merges and survives partial PATCHes, so just don't resend `advanceSettings` at all when only changing colors. If you ever must resend it, copy it verbatim from a fresh read.
- **No text-color field exists** — only backgrounds. On a dark `backgroundColor`, message text may be hard to read; flag it and offer a lighter variant.
- **Confirm before writing** to a live client account. Reads are safe; writes change the live widget.
- Clean up any temp JSON files you create for request bodies.

## Error handling

- **401** on the data/update route with *"route not yet supported by the IAM Service"* → that specific route isn't enabled for token auth; use the PATCH-based read/update path instead of GET-by-id.
- **401 Unauthorized** generally → token invalid/expired; ask the user to regenerate at Settings → Private Integrations in GHL.
- **422** on list → you forgot `limit`/`offset`.
- **422** on create → missing one of `version`, `chatType`, `name`, `locationId`.
- **404 "Cannot PATCH ..."** → wrong path; the update path is `/chat-widget/data/{locationId}/{id}`.
- Colors not saving → wrong `colors` key name (must match the table exactly) or `theme.name` not set to `"custom"`.

## Notes

- `chatType` is `emailChat` (form-style; the default A2P widget) or `liveChat` (full real-time webchat). Theme colors apply to both; some live-chat-only UI only renders on `liveChat`. This API can't convert an existing widget's type — you'd create a new one.
- To create a new `liveChat` widget, `POST /chat-widget/?locationId={loc}` with at least `version`, `chatType: "liveChat"`, `name`, `locationId`, then PATCH its theme colors.
