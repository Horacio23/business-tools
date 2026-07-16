---
name: ghl-calendars
description: >
  Create and manage calendars, calendar groups, appointments, and events on GoHighLevel (GHL).
  Use this skill whenever the user wants to create a calendar or calendar group/category,
  create an appointment, see upcoming appointments, list calendar events, book a meeting,
  check their schedule, or manage calendars/appointments in GoHighLevel/GHL/HighLevel.
  Also trigger when the user mentions scheduling, booking, or calendar management in a GHL context,
  including adding a deposit / partial payment / "accept payments" or theming the booking
  widget colors on a calendar.
---

# GHL Calendars & Appointments

Manage appointments on GoHighLevel calendars via the GHL API v2.

## Credentials

**Always ask the user which location/client to run for before doing anything else.** Each client has their own token and location ID stored under `C:\Users\horac\Claude\Clients\{ClientName}\GHL Credentials.txt`. The Cyber Popular account credentials are at `C:\Users\horac\Claude\High Level Credentials.txt`.

1. Ask: "Which GHL location/client should I use for this?" (or if already clear from context, confirm it)
2. Read the corresponding credentials file for that client
3. Set:
   - `GHL_PRIVATE_TOKEN` = the token value
   - `GHL_LOCATION_ID` = the location ID value

If the credentials file is empty or missing, ask the user to provide the token and location ID directly.

## Calendar Types

When creating calendars, always use `"calendarType": "service_booking"` and include a `teamMembers` array. Service booking requires at least one team member:

```json
"teamMembers": [
  {
    "userId": "{userId}",
    "priority": 0,
    "meetingLocationType": "custom",
    "isPrimary": true
  }
]
```

Fetch available users with:
```
GET /users/?locationId={locationId}
```

Use `"calendarType": "event"` only if the user explicitly requests it.

## Calendar Naming

Use only standard English alphabet characters in calendar names and slugs — no accented or special characters (e.g. use "Laser" not "Láser", "Colonica" not "Colónica", "Inyectables" not "Inyectables" with accent).

## API Basics

- **Base URL**: `https://services.leadconnectorhq.com`
- **Required headers** on every request:
  - `Authorization: Bearer <GHL_PRIVATE_TOKEN>`
  - `Version: 2021-07-28`
  - `Content-Type: application/json`
  - `Accept: application/json`

Use `curl` for API calls. Parse responses with `jq` if available, otherwise use Python with `urllib.request` and `json`.

## Workflow: Create Calendars (and Groups)

Use this when the user wants to create one or more calendars, optionally organized into groups (categories).

1. **Confirm the plan before creating anything.** If the user wants calendars organized into categories, propose the category -> calendar mapping (names, prices, durations, descriptions) and get explicit approval BEFORE creating in GHL. Do not create until the user has reviewed.

2. **Fetch a user** to staff the calendars (service_booking requires at least one team member):
   ```
   GET /users/?locationId={locationId}
   ```

3. **Create groups (categories)** if needed, capturing each group `id`:
   ```
   POST /calendars/groups
   ```
   Body: `{ "locationId", "name", "description", "slug", "isActive": true }`
   - Delete a group with `DELETE /calendars/groups/{groupId}`

4. **Create each calendar**, passing `groupId` to associate it with its category:
   ```
   POST /calendars/
   ```
   ```json
   {
     "locationId": "{locationId}",
     "groupId": "{groupId}",
     "name": "{name}",
     "description": "{description}",
     "slug": "{slug}",
     "calendarType": "service_booking",
     "teamMembers": [ { "userId": "{userId}", "priority": 0, "meetingLocationType": "custom", "isPrimary": true } ],
     "eventTitle": "{{contact.first_name}} - {{calendar.name}}",
     "slotDuration": 45,
     "slotDurationUnit": "mins",
     "isActive": true
   }
   ```
   (Omit `groupId` for an ungrouped calendar.)

   **Always set `eventTitle`** (the appointment title template) to:
   ```
   {{contact.first_name}} - {{calendar.name}}
   ```
   This makes every booked appointment read like "Maria - Labios" — the client's first name plus the service — so appointments are self-explanatory in the calendar view, reminders, and notifications. GHL's default is just `{{contact.name}}` (full name, no service); always override it with the template above unless the user asks for something different. If a calendar was created without it, set it after the fact with `PUT /calendars/{calendarId}` and body `{ "eventTitle": "{{contact.first_name}} - {{calendar.name}}" }`.

   > **Token gotcha:** the calendar-name token is `{{calendar.name}}` — **not** `{{appointment.calendar_name}}`. The latter is invalid and renders to an empty string, so titles come out as "Maria - " with the service missing. The `{{contact.first_name}}` half still works, which makes the bug easy to miss.

   **Gotchas:**
   - **Slugs are globally unique across ALL of GHL**, not just the location. Generic slugs (e.g. `botox`, `tirzepatide`) may return 400 "Calendar slug is already taken". Suffix with the client name (e.g. `botox-haus-lab`).
   - `openHours` is finicky (the field is `daysOfTheWeek`, not `daysOfWeek`). If it returns 422, omit it and let GHL apply default availability, then set hours in the UI.

5. **When done, ALWAYS report the result grouped by category, with each calendar ID.** Fetch the final list (`GET /calendars/?locationId={locationId}`) and format like this:

   ```
   ## Calendars Created — {Client}

   ### {Group Name}
   - **{Calendar Name}** — `{calendarId}`
   - **{Calendar Name}** — `{calendarId}`

   ### {Group Name}
   - **{Calendar Name}** — `{calendarId}`

   **Ungrouped**
   - **{Calendar Name}** — `{calendarId}`
   ```

   Always include each calendar's `id` so the user can reference them later. If calendars belong to groups, group them under their group name; list any calendars without a group under **Ungrouped**.

## Workflow (OPTIONAL): Add a Deposit / Partial Payment + Widget Colors

Use this when the user wants a calendar to **collect a deposit / partial payment** at booking, and/or to **theme the booking-widget colors**. This is the native GHL Neo booking widget (payment + card validation happen inside the widget — no card handling on our side).

> ⚠️ These settings are **NOT** on the public API. They live on GHL's **internal** host `https://backend.leadconnectorhq.com` (same PIT token, but `Version: 2021-04-15`). This host is undocumented and could change. **Full details, field schemas, gotchas, and a working Node reference implementation are in the vault: [[GHL Calendar Payment Provisioning]] — read it before running this flow.** Only the essentials are here.

**Prerequisite — availability:** availability lives in a separate **Schedule object**, not on the calendar. A calendar created via the flow above with a `teamMembers` user **auto-subscribes** to that user's schedule, so availability already works. Do NOT set `openHours` on a schedule-based calendar (it detaches it).

**Steps (GET → sanitize → merge → PUT):**

1. **GET** the calendar from the backend host:
   `GET https://backend.leadconnectorhq.com/calendars/{calendarId}` (headers: `Authorization: Bearer <PIT>`, `Version: 2021-04-15`).
2. **Sanitize** the returned object (GET and PUT schemas differ — skipping this returns 422):
   - strip `id`, `traceId`, `notifications`, `locationId`
   - rename `formSubmitRedirectUrl` → `formSubmitRedirectURL`
   - **drop `openHours` if empty** (`{}`) and **drop `availabilities` if empty** (`[]`) — sending either empty **detaches the calendar from its schedule and kills availability**.
3. **Merge in** the payment + color blocks and PUT the whole object back to `PUT https://backend.leadconnectorhq.com/calendars/{calendarId}`:
   ```json
   {
     "isLivePaymentMode": true,
     "stripe": { "amount": 100, "currency": "USD", "deposit": 35, "depositType": "percentage", "chargeDescription": "Booking deposit", "isCouponEnabled": false },
     "widgetConfig": {
       "primarySettings": { "primaryColor": "#2563EBFF", "backgroundColor": "#FFFFFFFF", "buttonText": "Book & Pay Deposit", "showCalendarTitle": true, "showCalendarDescription": true, "showCalendarDetails": true },
       "default": false,
       "pageOrder": [ {"kind":"calendar","position":0}, {"kind":"form","position":1} ]
     }
   }
   ```
   - `amount` = full price; `deposit` + `depositType` (`"percentage"` or `"flat"`) = the deposit taken at booking.
   - **`isLivePaymentMode`: always `true`** (real charges) — this is the default for real client calendars. Only use `false` (test mode) if the user explicitly asks to test.
   - **Attach the account's custom booking form** via `formId`. Look it up with `GET /forms/?locationId={loc}` (Version `2021-07-28`) and use the form named **"Calendar Form"** (accounts that take payments have one custom form). Setting `formId` is what makes the calendar use that custom form at submission — required for things like passing a **language** variable through on submit. When embedding, the site should append the current language as a query param on the widget URL (e.g. `.../widget/booking/{id}?language=es`).
   - **Widget colors — source from the client's brand:** read the client's website / brand colors from `Clients/{Name}/brand-context.md` (or their live site). Map **primaryColor** ← the brand's **primary accent / button** color, and **backgroundColor** ← a **light** brand background color (page background). The widget has only an accent + a background surface — do NOT put two saturated brand colors adjacent (contrast breaks); pair the accent with a light background. **If brand colors are not available, ASK the user for the primary and secondary/background colors before applying.**
   - Colors **must** be UPPERCASE 8-digit RGBA (`#RRGGBBFF`) — convert any 6-digit brand hex by appending `FF`. `widgetConfig.default` **must** be `false`, or the widget ignores them. `widgetType` stays `"default"` (that is the Neo widget).

4. **Blind write — verify in the UI.** A PIT never reads `stripe`/`widgetConfig` back (GET omits them), so a 200 is not proof. Confirm in GHL: Calendar → Forms & Payments (deposit + live/test) and the widget preview (colors), and that bookable times still show.

5. **Embed** (deterministic, no API): 
   ```html
   <iframe src="https://{BRANDED_DOMAIN}/widget/booking/{calendarId}" style="width:100%;border:none;overflow:hidden;" scrolling="no" allow="payment *"></iframe>
   <script src="https://{BRANDED_DOMAIN}/js/form_embed.js" type="text/javascript"></script>
   ```
   `allow="payment *"` is required for the payment step. `{BRANDED_DOMAIN}` = the sub-account's API Domain.

6. **REMIND THE USER (language passthrough).** After attaching payments + the custom form, tell the user: *"Update your AI Studio site so every booking embed appends the currently-selected site language as a query param — the calendars now use the custom Calendar Form, which reads it on submit."* Then give them this ready-to-paste **AI Studio prompt** (adjust the param key if their form field's query key isn't `language`):

   > On every booking/calendar embed on the site, append the visitor's currently-selected language as a query parameter named `language` on the widget URL. Per-service widgets: `https://{domain}/widget/booking/{calendarId}?language={lang}`. Category menus: `https://{domain}/widget/group/{groupId}?language={lang}`. `{lang}` is the active language code (e.g. `en` or `es`) from the site's language switcher, and it must update reactively when the visitor changes languages. Keep `allow="payment *"` on each iframe and keep loading `form_embed.js`.

   Confirm the query-param key matches the query key of the language field on their Calendar Form, or the value won't map on submit.

**Safety:** real client sub-accounts. Test against one throwaway calendar (test mode) before bulk-applying. See the vault SOP for the dry-run reference implementation.

## Workflow: View Appointments

1. **Get calendars** to know which calendar(s) exist:
   ```
   GET /calendars/?locationId={locationId}
   ```
   This returns a `calendars` array. Note each calendar's `id` and `name`.

2. **List events** for a time range:
   ```
   GET /calendars/events?locationId={locationId}&startTime={ISO8601}&endTime={ISO8601}
   ```
   Optional filters: `calendarId`, `userId`.

   - If the user asks for "today's appointments", use today's date 00:00:00 to 23:59:59 in the location's timezone.
   - If the user asks for "this week", use Monday 00:00:00 to Sunday 23:59:59.
   - If no time range is specified, default to showing the next 7 days.

3. **Format results** clearly for the user:
   ```
   ## Appointments ({date range})

   1. **{title}** — {date} at {time}
      - Status: {appointmentStatus}
      - Contact: {contactId}
      - Calendar: {calendarName}

   2. ...
   ```

   If no appointments found, say so clearly.

## Default Calendar

When the user wants to book an appointment for a client, use the **Sales Calendar - ES** by default:
- **Calendar ID**: `SG9krkfDB2Y8CJgjsmwK`
- **Calendar Name**: Sales Calendar - ES

Only ask which calendar to use if the user specifically mentions a different calendar.

## Workflow: Create an Appointment

1. **Gather required information** from the user. You need:
   - **Title**: What is the appointment for?
   - **Date & Time**: When? (start time and duration or end time)
   - **Contact**: Who is it with? (need a contactId — search contacts if user gives a name)
   - **Calendar**: Defaults to **Sales Calendar - ES** — only ask if user specifies otherwise

2. **Look up the contact** if the user provides a name instead of an ID:
   ```
   GET /contacts/?locationId={locationId}&query={name}
   ```
   If multiple matches, ask the user to pick. If no match, ask if they want to create a new contact.

3. **Get the calendar ID** if not already known:
   ```
   GET /calendars/?locationId={locationId}
   ```
   If only one calendar exists, use it. If multiple, ask the user which one.

4. **Confirm with the user** before creating:
   ```
   ## Confirm Appointment

   - **Title**: {title}
   - **Date/Time**: {startTime} — {endTime}
   - **Contact**: {contactName}
   - **Calendar**: {calendarName}

   Create this appointment? (yes/no)
   ```

5. **Create the appointment**:
   ```
   POST /calendars/events/appointments
   ```
   Body:
   ```json
   {
     "calendarId": "{calendarId}",
     "locationId": "{locationId}",
     "contactId": "{contactId}",
     "startTime": "{ISO8601}",
     "endTime": "{ISO8601}",
     "title": "{title}",
     "appointmentStatus": "new",
     "toNotify": true
   }
   ```

6. **Report result**:
   - **200/201 success**: Confirm the appointment was created with the details.
   - **401 error**: Token is invalid — ask user to check their token.
   - **422 error**: Validation issue — show error details.
   - **400/404 error**: Show details, suggest verifying location/calendar ID.

## Error Handling

- **Auth failures (401)**: Token may be expired. Ask user to regenerate at Settings > Private Integrations in GHL.
- **Calendar not found**: List available calendars and ask user to pick.
- **Contact not found**: Offer to search with different terms or create a new contact.
- **Time conflicts**: If the API returns a conflict, inform the user and suggest alternative times.
