#!/usr/bin/env node
/**
 * ghl-cal.mjs — GHL calendar provisioning helper (create + add deposit/payment + widget colors).
 *
 * Adds a deposit / partial payment and Neo-widget theming to a GHL calendar via GHL's INTERNAL
 * backend host, which the public API cannot do. See the vault SOP "GHL Calendar Payment Provisioning".
 *
 * CREDENTIALS (never hardcoded / never commit a token):
 *   Set env vars before running:
 *     GHL_TOKEN=pit-xxxx  GHL_LOCATION_ID=xxxx
 *   (Cyber Popular creds live in "High Level Credentials.txt"; client creds in Clients/<name>/ghl-credentials.md)
 *
 * USAGE:
 *   # Create a calendar assigned to a user (auto-joins that user's availability schedule):
 *   node ghl-cal.mjs create --name "Botox Consult" --user <userId>
 *
 *   # Add a deposit + colors to an existing calendar (GET->sanitize->merge->PUT).
 *   # LIVE by default (real charges) — pass --test for test mode. Colors from the client's brand:
 *   node ghl-cal.mjs pay <calendarId> --amount 100 --deposit 35 --type percentage \
 *        --primary "#8C9C86FF" --bg "#FAF6EFFF" --button "Book & Pay Deposit" [--test] [--dry-run]
 *
 *   # Print the embed snippet:
 *   node ghl-cal.mjs embed <calendarId> --domain book.yourclient.com
 *
 * NOTES:
 *   - PIT writes to the backend are BLIND: deposit/colors are not readable back via API. Verify in the GHL UI.
 *   - Colors must be UPPERCASE 8-digit RGBA (#RRGGBBFF); widgetConfig.default must be false.
 *   - Never send empty openHours/availabilities on a schedule-based calendar (it detaches availability).
 */

const PUB = 'https://services.leadconnectorhq.com';
const BE = 'https://backend.leadconnectorhq.com';

function ctx() {
  const token = process.env.GHL_TOKEN;
  const locationId = process.env.GHL_LOCATION_ID;
  if (!token) { console.error('ERROR: set GHL_TOKEN env var (the PIT token).'); process.exit(1); }
  return { token, locationId };
}
const headers = (token) => ({ Authorization: `Bearer ${token}`, Version: '2021-04-15', 'Content-Type': 'application/json', Accept: 'application/json' });
const j = async (r) => { try { return await r.json(); } catch { return null; } };

// ---- core API ----
export async function getCalendar(token, id) {
  return (await j(await fetch(`${BE}/calendars/${id}`, { headers: headers(token) })))?.calendar;
}
export async function getSchedule(token, scheduleId) {
  const s = await j(await fetch(`${BE}/calendars/schedules/${scheduleId}`, { headers: headers(token) }));
  return s?.schedule || s;
}

/** Make a GET-returned calendar safe to PUT back to the backend host. */
export function sanitizeForPut(cal) {
  const c = { ...cal };
  for (const k of ['id', 'traceId', 'notifications', 'locationId']) delete c[k];
  if ('formSubmitRedirectUrl' in c) { c.formSubmitRedirectURL = c.formSubmitRedirectUrl; delete c.formSubmitRedirectUrl; }
  if (!Array.isArray(c.openHours) || c.openHours.length === 0) delete c.openHours;           // keep schedule availability
  if (!Array.isArray(c.availabilities) || c.availabilities.length === 0) delete c.availabilities; // prevents schedule DETACH
  return c;
}

/** Create a calendar assigned to a user (auto-subscribes to that user's schedule). */
export async function createCalendar(token, locationId, { name, userId, slotDuration = 30 }) {
  const body = {
    locationId, name, calendarType: 'personal', eventType: 'RoundRobin_OptimizeForAvailability',
    widgetType: 'default', eventTitle: '{{contact.name}}',
    teamMembers: [{ userId, priority: 0.5, selected: true, isPrimary: true,
      locationConfigurations: [{ location: '', position: 0, kind: 'custom', zoomOauthId: '', meetingId: 'custom_0' }] }],
    slotDuration, slotDurationUnit: 'mins', slotInterval: slotDuration, slotIntervalUnit: 'mins',
    isLivePaymentMode: false, autoConfirm: true,
  };
  const r = await fetch(`${PUB}/calendars/`, { method: 'POST', headers: headers(token), body: JSON.stringify(body) });
  const out = await j(r);
  if (r.status >= 400) throw new Error(`create failed ${r.status}: ${JSON.stringify(out?.message)}`);
  return out.calendar.id;
}

/** Build the payment PUT body without sending (used for --dry-run and by addPayment).
 *  live defaults to TRUE (real charges). Widget colors are applied ONLY when both are provided —
 *  otherwise the calendar's existing theme is preserved (a PIT can't read colors back to merge them). */
export function buildPaymentBody(cal, { amount, deposit, depositType = 'percentage', live = true,
  formId, primaryColor, backgroundColor, buttonText = 'Book & Pay Deposit',
  chargeDescription = 'Booking deposit' }) {
  const body = {
    ...sanitizeForPut(cal),
    isLivePaymentMode: live,
    stripe: { amount, currency: 'USD', deposit, depositType, chargeDescription, isCouponEnabled: false },
  };
  if (formId) body.formId = formId; // attach the account's custom "Calendar Form" (needed for language var passthrough)
  if (primaryColor && backgroundColor) {
    body.widgetConfig = {
      primarySettings: { primaryColor, backgroundColor, buttonText, showCalendarTitle: true, showCalendarDescription: true, showCalendarDetails: true },
      default: false, pageOrder: [{ kind: 'calendar', position: 0 }, { kind: 'form', position: 1 }],
    };
  }
  return body;
}

/** Add deposit + colors to an existing calendar. Blind write — verify in UI. */
export async function addPayment(token, id, opts) {
  const cal = await getCalendar(token, id);
  if (!cal) throw new Error(`calendar ${id} not found`);
  const body = buildPaymentBody(cal, opts);
  const r = await fetch(`${BE}/calendars/${id}`, { method: 'PUT', headers: headers(token), body: JSON.stringify(body) });
  if (r.status >= 400) throw new Error(`pay failed ${r.status}: ${JSON.stringify((await j(r))?.message)}`);
  return r.status;
}

export const embedSnippet = (id, domain) =>
  `<iframe src="https://${domain}/widget/booking/${id}" style="width:100%;border:none;overflow:hidden;" scrolling="no" allow="payment *"></iframe>\n` +
  `<script src="https://${domain}/js/form_embed.js" type="text/javascript"></script>`;

// ---- tiny CLI ----
function argMap(argv) {
  const m = {}; const pos = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) { const k = a.slice(2); const v = (argv[i + 1] && !argv[i + 1].startsWith('--')) ? argv[++i] : true; m[k] = v; }
    else pos.push(a);
  }
  return { m, pos };
}

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const { m, pos } = argMap(rest);
  const { token, locationId } = ctx();

  if (cmd === 'create') {
    const id = await createCalendar(token, locationId, { name: m.name, userId: m.user, slotDuration: Number(m.slot) || 30 });
    console.log('created calendar:', id);
  } else if (cmd === 'pay') {
    const id = pos[0];
    const opts = { amount: Number(m.amount), deposit: Number(m.deposit), depositType: m.type || 'percentage',
      live: !m.test, formId: m.form, primaryColor: m.primary, backgroundColor: m.bg, buttonText: m.button }; // live by default; --test forces test mode
    if (m['dry-run']) {
      const cal = await getCalendar(token, id);
      console.log('DRY RUN — would PUT to', `${BE}/calendars/${id}`);
      console.log(JSON.stringify(buildPaymentBody(cal, opts), null, 2));
    } else {
      const status = await addPayment(token, id, opts);
      console.log(`payment applied (HTTP ${status}). Blind write — verify deposit/colors + availability in the GHL UI.`);
    }
  } else if (cmd === 'embed') {
    console.log(embedSnippet(pos[0], m.domain));
  } else {
    console.log('commands: create --name --user | pay <id> --amount --deposit --type [--live] [--dry-run] [--primary --bg --button] | embed <id> --domain');
  }
}

// run CLI only when invoked directly
if (import.meta.url === `file://${process.argv[1].replace(/\\/g, '/')}` || process.argv[1]?.endsWith('ghl-cal.mjs')) {
  main().catch((e) => { console.error(e.message); process.exit(1); });
}
