---
name: ghl-email-templates
description: >
  Create email templates in GoHighLevel (GHL) sub-accounts from PDF or Word documents.
  Use this skill whenever the user wants to extract email content from a document and
  push it to GoHighLevel, create GHL email templates, upload emails to HighLevel,
  convert a PDF or DOCX to GHL email templates, or mentions GoHighLevel/GHL/HighLevel
  email templates in any context. Also trigger when the user has a document with email
  copy (subject lines, body text, CTAs) and wants those emails created in a marketing
  automation platform like GoHighLevel, even if they don't say "template" explicitly.
---

# GHL Email Templates from Documents

Extract email templates from PDF or DOCX documents and create them as HTML email templates in GoHighLevel sub-accounts via the GHL API v2.

## When to Use

- User provides a PDF or Word document containing email copy
- User wants email templates created in a GoHighLevel sub-account
- User mentions extracting emails from a document for GHL/HighLevel

## Prerequisites

Before starting, you need the following from the user:

- **GHL_PRIVATE_TOKEN**: A Private Integration Token from the GoHighLevel account. The user creates this at Settings > Private Integrations in their GHL dashboard. Check the local client folder first (e.g. a `.env` or `GHL Integration.txt` file) — if not found, ask the user.
- **GHL_LOCATION_ID**: The sub-account (location) ID where templates will be created. Also check the local client folder first — if not found, ask the user.
- **Brand colors**: Ask the user upfront how they want to source brand colors. Present the options clearly:
  - *"I can pull the colors directly from your website — do you have a URL?"*
  - *"Do you have a brand board or style guide I can reference?"*
  - *"Do you know your hex codes and want to provide them directly?"*
  - Always source colors from the live website (using browser tools) or a brand board. **Never infer brand colors from a PDF document** — document colors are often not accurate representations of the true brand palette.

**Credentials security**: Credentials are read from the local client folder and used only within the session. Never share, print in full to the user, log, or transmit credentials anywhere other than the intended GHL API endpoint.

## Workflow

### Phase 1: Extract Email Content

1. **Read the document** using the Read tool directly:
   - Claude can read PDFs and DOCX files natively — no conversion needed
   - If the file format is unsupported, ask the user to convert to PDF or DOCX

2. **Identify email templates** by looking for these structural patterns:
   - **Subject lines**: Text after "Subject:", "Email Subject:", "Subject Line:", or similar labels
   - **Body content**: Paragraphs following the subject line, often under "Body:", "Email Body:", "Copy:", or as the main text block between subject and CTA
   - **CTA (Call to Action)**: Text after "CTA:", "Button:", "Call to Action:", or similar labels
   - **Email boundaries**: Numbered emails ("Email 1", "Email #2"), horizontal rules, page breaks, section headers, or large spacing between emails

3. **Parse each email** into this structure:
   - `name`: A short descriptive template name (derived from the subject or section header)
   - `subject`: The email subject line
   - `body`: The full email body text, preserving paragraph structure
   - `cta_text`: The call-to-action button text (if present)
   - `cta_url`: The CTA link URL (if specified; otherwise use `#` as a placeholder)

4. **Replace all placeholders with GHL merge fields**: Any placeholder for contact or location data found in the document must be replaced with the correct GHL variable — never leave generic placeholders in the final template. Standard mappings:
   - Contact name / `[NOMBRE]` / `[NAME]` → `{{contact.first_name}}`
   - Phone number / `[INSERTAR NÚMERO]` / `[PHONE]` → `{{location.phone}}`
   - Street address → `{{location.address}}`, plus `{{location.city}}`, `{{location.state}}`, `{{location.postal_code}}` as needed
   - Business name → `{{location.name}}`
   - Unsubscribe link / `[UNSUBSCRIBE]` → `{{unsubscribe_link}}`
   - Apply these replacements consistently across the body, CTA sub-text, and footer of every email.

   **Footer rule (always apply):** The footer must show the **address and phone** as GHL location variables — `{{location.address}}` (with city/state/postal as needed) and `{{location.phone}}`. **Do NOT put hours of operation in the footer** — hours are not a reliable GHL variable and go stale. If the source template or a snapshot has a hardcoded hours line (e.g. "Mon–Sat · 9AM–7PM"), remove it; replace any hardcoded address/phone with the variables above. Never carry a previous client's hours, address, or phone into a new template.

4. **Handle mixed content** — if the document contains non-email content (branding guidelines, notes, instructions), skip it. Only extract sections that are clearly email templates. If unsure whether something is an email template, include it in the extraction but flag it for the user in Phase 2.

### Phase 2: Generate HTML & Visual Preview

Generate the HTML emails first so the user can see exactly how they'll look before pushing to GHL. Seeing the raw HTML code isn't helpful — the user needs to see the rendered visual result as it would appear in a recipient's inbox.

**Design one email first, then expand.** Always build and preview Email 1 (or whichever the user selects) before generating the rest of the sequence. Ask for approval on the design — colors, layout, header, footer — before applying it to all other emails. This avoids reworking all templates if the user wants design changes.

1. **Generate HTML for each email**:
   - Read the base template from `assets/email-base-template.html` (relative to this skill's directory)
   - Replace `{{BODY_CONTENT}}` with the email body text, wrapping each paragraph in `<p>` tags
   - Replace `{{CTA_TEXT}}` with the CTA button text
   - Replace `{{CTA_URL}}` with the CTA URL
   - If no CTA exists for this email, remove everything between `<!-- CTA SECTION START -->` and `<!-- CTA SECTION END -->` (inclusive)
   - Preserve bold/italic formatting from the source: use `<strong>` and `<em>` tags

2. **Create a visual preview page**:
   - Save each email's HTML to a temporary file (e.g., `/tmp/ghl-preview-email-1.html`, etc.)
   - Generate a single preview page at `/tmp/ghl-email-preview.html` that shows ALL emails rendered visually in a single scrollable page, with clear labels for each email's template name and subject line
   - Use the preview wrapper template from `assets/preview-wrapper.html`
   - Open the preview page in the user's browser:
     ```bash
     start "" "/tmp/ghl-email-preview.html"    # Windows
     open /tmp/ghl-email-preview.html           # macOS
     xdg-open /tmp/ghl-email-preview.html       # Linux
     ```

3. **Tell the user** to review the preview in their browser and come back to confirm.

### Phase 3: User Confirmation (and Naming)

After the user has seen the visual preview, ask for confirmation before making any API calls. This is a hard requirement — never call the GHL API without explicit user approval.

**Always ask the user for the exact name of each template before uploading.** Never propose names or assume them — the user knows how they organize their GHL account. Ask explicitly and wait for their answer before proceeding. Renaming after upload requires an extra API call per template, so get it right before pushing.

Ask like this:

```
## Email Templates Ready for GHL

I've opened a visual preview of all [N] email template(s) in your browser so you can see exactly how they'll look.

What would you like to name each template in GHL?
1. [Email 1 description] — name?
2. [Email 2 description] — name?
...
```

Wait for the user to provide all names before making any API calls.

Format the final confirmation like this:

```
## Ready to create in GHL

1. "[name 1]" — Subject: "[subject line]"
2. "[name 2]" — Subject: "[subject line]"
...

Create these in GHL location [locationId]?
- **yes** — create all templates with these names
- **rename** — give me a different naming pattern
- **edit** — change the email content (I'll regenerate the preview)
- **cancel** — stop without creating anything
```

If the user says "rename", apply the new pattern, show the updated list, and ask again. If they say "edit", make the content changes, regenerate the HTML preview, reopen it, and ask for confirmation again. Loop until they say "yes" or "cancel".

### Phase 4: Create Templates in GHL

For each confirmed email:

1. **Create the template via GHL API** (two-step process required):
   - The GHL API does NOT support setting HTML content on creation. The `POST` endpoint always creates a template with default placeholder content, regardless of what body/content fields you send. A `PATCH` is required to set the actual HTML.
   - If `jq` is available, use the shell script:
     ```bash
     bash <skill-directory>/scripts/ghl-create-template.sh \
       "$GHL_PRIVATE_TOKEN" \
       "$GHL_LOCATION_ID" \
       "Template Name Here" \
       "$(cat /tmp/ghl-preview-email-1.html)" \
       "Subject Line Here"
     ```
   - If `jq` is not available, prefer **Node.js** (more reliably available on Windows than Python):
     - Use the built-in `https` module with `https.request()` — no npm packages needed
     - Step 1: `POST /emails/builder` with `{ locationId, title, type: "html" }` to create the shell. Extract the `id` from the response.
     - Step 2: `PATCH /emails/builder/{id}` with `{ locationId, title, editorType: "html", editorContent: "<html>...", subjectLine: "..." }` to set the actual content and subject line.
     - **Important — `title` on POST/PATCH does NOT set the displayed template name.** The shell is created with whatever name GHL assigns, and the v1 PATCH endpoint silently ignores the `title` field for renaming. To set the user-visible name, immediately follow with Step 3 (below) per template.
     - Step 3 — set the displayed name: `PATCH /emails/public/v2/locations/{locationId}/templates/{id}` with `{ "name": "Template Name Here" }`. This is the v2 endpoint and the only one that actually renames.
     - All requests require headers: `Authorization: Bearer <token>`, `Version: 2021-07-28`, `Content-Type: application/json`, `Accept: application/json`, `User-Agent: GHL-Email-Skill/1.0`
   - Fall back to Python (`urllib.request` and `json`) only if Node.js is also unavailable. Check with `node --version` before attempting Python.
   - Consult `references/ghl-email-api.md` for API details if you encounter unexpected errors

2. **Handle results**:
   - **201 success**: Note the template name as created
   - **401 error**: Token is invalid or expired — ask the user to check their Private Integration Token
   - **422 error**: Validation issue — show the error message and suggest fixes
   - **400/404 error**: Show details and suggest the user verify their location ID

3. **Report a summary** after processing all templates:
   ```
   ## Results
   - Created: [N] template(s) successfully
   - Failed: [M] template(s) — [error details if any]
   - Location: [locationId]
   ```

## Error Handling

- **No emails found**: If the document contains no identifiable email templates, tell the user and offer to show the raw extracted text so they can point out where the emails are. Suggest checking that emails use recognizable headers (Subject:, Body:, etc.).
- **API auth failures**: GHL Private Integration Tokens can expire. If you get repeated 401 errors, suggest the user regenerate their token at Settings > Private Integrations.
- **Duplicate template names**: GHL may reject templates with names that already exist in the location. If this happens, suggest appending a number or date suffix.
- **Large documents**: If a document has many pages, process it section by section and look for email content throughout the entire document.

## Reference Files

- **`references/ghl-email-api.md`** — GHL Email Builder API specification with endpoints, headers, request/response schemas, and error codes. Read this when you need API details beyond what's in this skill file.

## Scripts

- **`scripts/ghl-create-template.sh`** — Shell script wrapper for the GHL create-template API call. Handles JSON construction via `jq`, proper header formatting, and error code parsing.

## Assets

- **`assets/email-base-template.html`** — Responsive, email-client-compatible HTML template with placeholder variables. Table-based layout with inline styles for maximum compatibility across Outlook, Gmail, Apple Mail, etc.
- **`assets/preview-wrapper.html`** — Visual preview page template that renders all emails in a scrollable, dark-themed viewer. Replace `{{SKILL_TITLE}}` with the batch title, and `{{EMAIL_CARDS}}` with the rendered email card HTML blocks. Each email card should use an `<iframe srcdoc="...">` to render the email's full HTML inline, giving the user a realistic preview of how each email will look in a recipient's inbox. Escape double quotes in the HTML as `&quot;` inside the srcdoc attribute.
