---
name: ghl-cadence
description: >
  Convert sales/marketing cadence tables from Word (.docx) or PDF documents into
  optimized prompts for GoHighLevel's AI Workflow Builder. Use this skill whenever
  the user wants to turn a cadence, sequence, or outreach plan from a document into
  a GHL workflow, mentions converting cadence tables to GoHighLevel workflows,
  wants to automate workflow creation from a document, or references building
  GHL/HighLevel workflows from a cadence, sequence, drip campaign, or outreach plan
  in any format. Also trigger when the user has a document with a step-by-step
  outreach sequence (day-by-day actions like emails, calls, SMS, LinkedIn messages)
  and wants it turned into a GHL automation, even if they don't say "cadence" explicitly.
---

# GHL Cadence-to-Workflow Prompt Generator

This skill reads a cadence table from a Word or PDF document and generates a
structured natural-language prompt optimized for GoHighLevel's AI Workflow Builder.
The user pastes the generated prompt into GHL's "Build using AI" feature, and the
AI builder creates the full workflow automatically.

## Why this approach works

GoHighLevel's API does not support creating workflows programmatically — there is
no workflow CRUD endpoint. However, GHL has a powerful AI Workflow Builder that
accepts natural-language prompts and generates complete workflows with triggers,
actions, wait steps, and conditional branches. By generating a well-structured
prompt from the cadence table, we get the best of both worlds: automated parsing
of the source document and AI-powered workflow creation inside GHL.

## Workflow

### Step 1: Get the cadence file

If the user provided a file path as an argument, use that. Otherwise, ask for
the path to their cadence document (.docx or .pdf).

### Step 2: Extract the cadence table

Read the document and extract the table content:

**For .docx files:**
- Use the Read tool to read the file directly. Claude can read .docx files natively.
- Identify the cadence table — look for tabular data with columns related to
  timing/days, action types, and content/messaging.

**For .pdf files:**
- Use the Read tool to read the PDF. Claude can read PDF files natively.
- Identify the cadence table from the extracted content.

### Step 3: Parse the table

Identify the columns by matching against common naming patterns. Be flexible —
cadences come in many formats.

**Timing column** (when the action happens):
- "Day", "Step", "Sequence", "Touch", "Touchpoint", "#", "Day #", "Timeline",
  "When", "Timing", "Schedule"
- Values might be: "Day 1", "1", "D1", "Day 1 (Morning)", "Immediately",
  "Same day", "+2 hours", "Day 3-5"

**Action/channel column** (what type of action):
- "Action", "Type", "Channel", "Activity", "Medium", "Method", "Task",
  "Action Type", "Touch Type", "Outreach Type"
- Values might be: "Email", "Call", "SMS", "LinkedIn", "Voicemail", "Task",
  "Video", "Direct Mail", "Social", "Email + Call"

**Content column** (the message or description):
- "Content", "Message", "Body", "Script", "Template", "Copy", "Notes",
  "Description", "Details", "Subject", "Messaging", "Talk Track"

**Additional columns to look for** (may or may not be present):
- "Subject" or "Subject Line" — email subject lines
- "Goal" or "Purpose" or "Objective" — the intent of the touchpoint
- "Notes" or "Instructions" — additional context
- "Condition" or "If" — conditional logic (e.g., "if no reply")

Build a structured list of steps, where each step has:
- `day`: the day number or timing
- `action`: the action type (normalized — see mapping below)
- `content`: the message content, subject line, script, etc.
- `condition`: any conditional logic (optional)
- `notes`: any additional notes (optional)

### Step 4: Map actions to GHL language

Transform the parsed action types into GHL-specific workflow language:

| Cadence term | GHL workflow action |
|---|---|
| Email, E-mail, Email Send | Send an email |
| Call, Phone, Phone Call, Ring | Create a manual call task |
| SMS, Text, Text Message, MMS | Send an SMS |
| LinkedIn, LI, LI Message, InMail, LI Connection Request | Create a task to send a LinkedIn message |
| Voicemail, VM, Voicemail Drop, Ringless VM | Drop a voicemail |
| Video, Video Email, Video Message | Send an email with a video link |
| Task, Manual Task, To-Do | Create a task |
| Direct Mail, Mail, Letter, Package | Create a task for direct mail |
| Social, Social Touch, Social Engagement | Create a task for social media engagement |

If an action combines multiple channels (e.g., "Email + Call"), split it into
separate sequential steps on the same day.

### Step 5: Ask the user about the trigger

Before generating the prompt, ask the user what should trigger this workflow.
Present these common options:

1. **Contact Added** (default) — "When a contact is added to the workflow"
2. **Tag Added** — "When a contact receives the tag [tag name]"
3. **Pipeline Stage Change** — "When a contact enters [stage] in [pipeline]"
4. **Form Submission** — "When a contact submits [form name]"
5. **Appointment Booked** — "When a contact books an appointment"
6. **Custom** — let the user specify their own trigger

If the user specified a trigger in their original message, use that instead of asking.

### Step 6: Generate the GHL AI builder prompt

Transform the parsed cadence into a structured prompt following these principles:

**Format rules:**
- Use numbered steps for every action
- Include explicit wait steps between different days ("Wait X days")
- State the channel explicitly in each step ("send an email", "send an SMS")
- Use precise timing ("wait 2 days" not "wait a bit")
- Include GHL dynamic values where content references personalization:
  - First name → `{{contact.first_name}}`
  - Last name → `{{contact.last_name}}`
  - Full name → `{{contact.name}}`
  - Company → `{{contact.company_name}}`
  - Email → `{{contact.email}}`
  - Phone → `{{contact.phone}}`
  - Assigned user → `{{user.name}}`
- If the cadence has conditions (e.g., "if no reply"), include If/Else branches
- Keep the prompt instruction-like, not prose — the GHL AI builder responds
  best to clear, imperative instructions

**Prompt template:**

```
When [trigger description]:

1. [First action with channel]:
   [Content details — subject line, body summary, SMS text, task description]

2. Wait [X days/hours]

3. [Next action with channel]:
   [Content details]

[Continue numbering for all steps...]

Additional instructions:
- [Any global notes, like "always include an unsubscribe link" or "use professional tone"]
```

**Content handling:**
- For emails: include the subject line and a summary/outline of the body content.
  Don't try to cram the entire email body into the prompt — the GHL AI builder
  will generate the full email copy. Instead, give it the key points, tone, and
  any specific phrases that must be included.
- For SMS: include the full message text since SMS messages are short.
- For calls: include the talk track summary or key talking points as the task description.
- For LinkedIn: include the connection request note or message text.
- For tasks: include the task description and any relevant instructions.

### Step 7: Present the output

Display the generated prompt clearly with instructions:

1. Show the complete prompt in a code block so the user can easily copy it
2. Tell the user:
   - Open GoHighLevel → Automation → Workflows
   - Click "Create Workflow" → "Build using AI"
   - Paste the generated prompt
   - Review the generated workflow and adjust as needed
   - Test with a sample contact before activating
3. Note any steps that might need manual attention after the AI builds the workflow
   (e.g., uploading voicemail recordings, attaching specific email templates,
   configuring webhook URLs)

### Step 8: Offer to refine

Ask the user if they want to:
- Adjust the trigger
- Modify any steps
- Add conditions or branching logic
- Generate prompts for additional cadences

If the user has more cadence documents, repeat the process for each one.

## Tips for best results

- The GHL AI builder works best with prompts under ~2000 characters. For very long
  cadences (20+ steps), consider splitting into multiple workflows (e.g., "Phase 1:
  Initial outreach" and "Phase 2: Follow-up sequence").
- If the cadence has complex conditional logic, generate the main linear sequence
  first, then suggest the user add conditions manually in the workflow builder
  after the AI creates the skeleton.
- Wait steps should calculate the delta between days, not use the absolute day number.
  For example, if Day 1 is email and Day 3 is call, the wait is "2 days", not "3 days".
