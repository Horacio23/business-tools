---
name: ghl-calendars
description: >
  Create and manage calendars, calendar groups, appointments, and events on GoHighLevel (GHL).
  Use this skill whenever the user wants to create a calendar or calendar group/category,
  create an appointment, see upcoming appointments, list calendar events, book a meeting,
  check their schedule, or manage calendars/appointments in GoHighLevel/GHL/HighLevel.
  Also trigger when the user mentions scheduling, booking, or calendar management in a GHL context.
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
