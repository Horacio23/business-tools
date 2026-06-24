---
name: client-onboarding
description: >
  Onboard a new client by scaffolding their folder, credentials, brand context,
  and a package-specific delivery checklist. Use this skill whenever the user wants
  to onboard a new client, set up a new client, create a client folder, kick off a
  new account, or start delivery for a new med spa / business. Also trigger when the
  user says "new client", "onboard [name]", "set up [company]", or references getting
  a newly-signed client ready for delivery. The skill asks for the company name and
  package, creates the folder under C:\Users\horac\Claude\Clients, and builds the
  credentials, brand-context, and onboarding-checklist files.
---

# Client Onboarding

Scaffolds a new client so everything delivery needs lives in one folder: GHL
credentials, brand context for asset generation, and a checklist of what's been
done — pulled from the package they bought.

## Base location

All clients live under:

```
C:\Users\horac\Claude\Clients\<Company Name>\
```

## The checklist is owned by the Second Brain

The per-package delivery checklist is **not hardcoded here**. It comes from the
vault SOP:

```
C:\Users\horac\Claude\Vault\wiki\operations\Client Onboarding Checklists.md
```

Always read that page to get the current checklist for the chosen package. If the
standard scope ever changes, it changes there — not in this skill.

## Steps

### 1. Get the Company Name

Ask the user for the client's **Company Name** if they didn't already give it.
Use it verbatim as the folder name (keep spaces and capitalization as the user
writes the brand — e.g. `Gentle Zap Laser`).

Check whether a folder already exists for that name (or a close match) under
`C:\Users\horac\Claude\Clients\`. If a similar folder exists, confirm with the
user before creating a new one — don't create a duplicate.

Create the folder:

```
C:\Users\horac\Claude\Clients\<Company Name>\
```

### 2. Ask which package they bought

Ask: **"Which package is this client on?"**

Read `Vault\wiki\operations\Client Onboarding Checklists.md` and offer the package
names listed there (e.g. Free Website Offer, Bilingual FID Offer, Fast Start).
Match the user's answer to the closest package heading.

If the package isn't in the SOP yet, ask the user what the checklist should be,
**add it to the SOP page first** (so it's reusable), then continue.

### 3. Create the credentials file

Create `ghl-credentials.md` in the client folder. Ask the user for the GHL **token**
and **locationId** if they have them; otherwise scaffold the template for them to
fill in later. Use this exact format (other skills read `token` + `locationId`):

```markdown
# GHL Credentials — <Company Name>

token: <pit-... or "TODO: paste GHL Private Integration Token">
locationId: <... or "TODO: paste GHL Location ID">
```

### 4. Ask for logo and/or website → brand context

Ask the user for the client's **logo** (file path or URL) and/or **website URL**.
At least one is enough to proceed; note whichever is missing as TODO.

Create `brand-context.md` — this is the reference any asset-generation work
(images, ads, social posts, site visuals) reads to stay on-brand. Capture what you
can; if a website was given, you may note brand colors/tone you can infer from it.

```markdown
# Brand Context — <Company Name>

Used as context for generating on-brand assets (images, ads, posts, site visuals).

- **Logo:** <path or URL, or "TODO: none provided yet">
- **Website:** <URL, or "TODO: none provided yet">
- **Brand colors:** <hex values if known/inferable, else TODO>
- **Tone / style notes:** <short notes if known, else TODO>
- **Notes:** <anything else useful for asset generation>
```

### 5. Create the onboarding checklist

Copy the **Checklist** block for the chosen package from the SOP page verbatim into
`onboarding-checklist.md`:

```markdown
# Onboarding Checklist — <Company Name>

**Package:** <package name>
**Started:** <today's date>

<the package's checklist items, copied from Client Onboarding Checklists.md>
```

For example, the **Free Website Offer** checklist is:

```markdown
- [ ] reminder email templates
- [ ] website first draft done
- [ ] A2P application submitted
- [ ] Domain hooked to site
```

### 6. Confirm

Tell the user what was created and where. List the three files
(`ghl-credentials.md`, `brand-context.md`, `onboarding-checklist.md`) and flag any
TODO fields still waiting on input (missing token/locationId, missing logo/website).

## Notes

- Keep credentials accurate — the `ghl-*` skills read `token` and `locationId` from
  `ghl-credentials.md` to make GHL API calls for this client.
- This skill only scaffolds. It does not start GHL delivery — use the relevant
  `ghl-*` skills for email templates, calendars, and chat widgets.
- As delivery progresses, check items off `onboarding-checklist.md`.
