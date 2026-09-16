---
name: meta-ads-report
description: >
  Build a client's monthly Meta (Facebook + Instagram) ads performance breakdown and
  turn it into a branded slide-deck presentation (Spanish by default), published as an
  Artifact. Pulls spend, results, cost per result, CTR/CPC/CPM, weekly pacing, per-campaign
  and per-ad numbers and Meta's quality diagnosis, then writes findings and next-month
  recommendations on a cover + slides in the client's own logo, colors and fonts. Use this
  skill whenever the user asks for an ads report, ads breakdown, "performance breakdown",
  monthly ads recap, "reporte de anuncios", "cómo le fue a los anuncios", results of a client's
  Facebook/Instagram/Meta campaigns for a month, or wants ad results turned into a
  presentation / deck / slides for a client, even if they don't say "Meta" or "presentation"
  explicitly (e.g. "do the ads breakdown for Elite for last month in spanish").
---

# Meta Ads Monthly Report → Branded Deck

What the user gets: a 9-slide presentation for **one client ad account and one month**,
in the client's brand, that they can walk the client through or share as a link.
Slides: cover · summary · weekly spend · budget vs results · campaign table ·
ads + Meta diagnosis · findings · recommendations · closing.

The data is only half the job. The value is the **interpretation**: which campaign earns
its budget, which ads are dragging, and what to change next month, said plainly to a
medspa owner who reads Spanish and doesn't live in Ads Manager.

## Step 0: Settle the inputs (one question round, max)

Work out these from the message, the client folder and memory. Ask only for what's
genuinely missing, and ask it in a **single** AskUserQuestion call.

| Input | Default / where to find it |
|---|---|
| Client | From the message. Folder: `C:\Users\horac\Claude\Clients\<closest match>` |
| Ad account ID | `brand-context.md` in the client folder ("Meta ad account"), else the Meta Ads connector memory note, else `ads_get_ad_accounts` (has returned HTTP 500 before; don't depend on it) |
| Period | "last month" = the previous **calendar** month. "last 30 days" = `last_30d`. "this month" / "hasta hoy" = the 1st through **yesterday** (today's data is incomplete). Explicit dates win. Anything that isn't a whole calendar month is a **partial period** (see "Partial periods" below). |
| Language | Spanish unless the user asks for English |
| **Include appointment measurement?** | **Always ask** unless the user already said, or `brand-context.md` records the client's "Sales process". See below. |

**Why the appointment question matters:** for some clients the agency doesn't control the
sales process (the client books and closes on their own), so the agency can only
guarantee *interest* (conversations, leads), not appointments or revenue. Recommending
"measure appointments" to those clients promises something the agency can't deliver.
Phrase the question like: *"¿Incluimos la medición de citas (cruzar conversaciones con citas
agendadas)? Solo si controlamos el proceso de venta de este cliente."* If the answer is a
lasting fact about the client, offer to record it under "Sales process" in their
`brand-context.md` so you don't have to ask next time.

- **No (default when unsure):** recommendations stay inside the ad account (budgets,
  pausing/scaling ads, new creative variants, audiences). Don't mention appointments,
  CRM, sales or revenue anywhere in the deck.
- **Yes:** add a recommendation to cross-check the month's results against booked
  appointments in GHL for the real cost per appointment. If the client folder has
  `ghl-credentials.md` and the user wants actual numbers, you *may* count the period's
  appointments via the `ghl-calendars` skill. Only show that number if the user asks.

## Step 1: Pull the data (Meta Ads connector)

Every call needs `client_conversation_id` (20 random alphanumerics, the same value all
session) and `advertiser_request` (the user's words, verbatim). Load the tool schemas
with ToolSearch first (`ads_get_ad_entities`, `ads_get_field_context`,
`ads_insights_auction_ranking_benchmarks`, `ads_insights_anomaly_signal`,
`ads_account_get_activity_logs`).

The `ads_get_ad_entities` description tells you to verify fields with `ads_get_field_context`
before querying. These are already verified, so skip that step for them:
`amount_spent, impressions, reach, frequency, cpm, clicks, link_click, ctr, cpc, results,
cost_per_result, lead, cost_per_lead, status, effective_status, delivery, objective,
daily_budget, end_time, spend_cap`. (`issues_info` is **not** valid.) Only verify fields
that aren't on this list. `link_click` and `lead` come back `null` (not 0) when there are none.

Dates: use `date_preset=last_month` for a whole previous month; otherwise
`time_range='{"since":"YYYY-MM-DD","until":"YYYY-MM-DD"}'` on `ads_get_ad_entities` and
`date_from`/`date_to` on the insights tools.

Run these, in parallel where possible:

1. **Account totals** · `level=ad_account`, all the metric fields (not
   `results`/`cost_per_result`, which aren't supported at account level; `lead` works).
2. **Campaigns** · `level=campaign`, metrics + `name, status, effective_status, delivery,
   objective, daily_budget, results, cost_per_result`, filter `campaign.amount_spent GREATER_THAN 0`.
3. **Ad sets** · `level=adset`, `name, status, effective_status, daily_budget, amount_spent`.
   **Why:** a campaign with every ad set paused still reports `status` *and*
   `effective_status` = ACTIVE. The pause only shows at ad set level or in the campaign's
   `delivery` substatus (e.g. `single_all_ad_set_off`). Budgets may also live on ad sets (ABO).
4. **Ads** · `level=ad`, same metrics + `status, effective_status`, filter
   `ad.amount_spent GREATER_THAN 0`, `sort=amount_spent_descending`.
5. **Weekly pacing** · `level=ad_account`, `time_increment="7"`, fields
   `amount_spent, impressions, clicks, ctr, cpm, frequency`.
6. **Previous period** · account totals for the comparison window (see Partial periods).
   An empty result (only id/name returned) means **no spend then**. Say so, don't invent a comparison.
7. **Meta diagnosis** · `ads_insights_auction_ranking_benchmarks` with the same date range.
8. **Delivery health** · `ads_insights_anomaly_signal` (no date range). "No issues found"
   is a real finding: it means the problem, if any, is creative, not setup.
9. **What changed** · `ads_account_get_activity_logs` for the period (read-only). It explains
   gaps in the numbers: who paused or turned on what and when, new ads created, budget edits,
   billing holds ("Payment Needed"), disapprovals. Mention the relevant events in the deck
   ("Láser está en pausa desde el 9 de sep") but not routine noise.

**Under-delivery check:** for each campaign, compare spend ÷ days in the period to its daily
budget. If it's well under (<70%), pull daily spend for that campaign (`time_increment="1"`)
and check ad set status and the activity log to explain it: paused mid-period, started late,
billing hold, limited audience. Never report an under-spending campaign as if it ran the whole time.

`ads_insights_performance_trend` renders a scorecard to the user and takes no date range,
so skip it for monthly reports. `ads_insights_industry_benchmark` usually returns no data for
these small accounts.

### Reading the numbers correctly

- **`results` depends on the campaign's optimization.** Read `results.indicator`:
  `onsite_conversion.messaging_conversation_started_7d` → "conversaciones (chat)";
  `lead` / `leadgen` → "leads"; `link_click` → "clics"; etc. The cohort info in the ranking
  output may say `messaging_deep_conversation`, but still report what `results` counts.
- **The account has no single "results" number.** Sum it from the campaign rows, and only
  when every campaign shares the same result type. With mixed types, report each type
  separately and remove slide 4's cost panel (see the comment in the template).
- `results.value` can be `"Not available"`, which means **0 results** for that ad, not missing data.
- `lead` is counted separately from chat results (leads attributed by Meta). A $230
  "cost per lead" on a chat campaign is misleading; show leads as a count, not a cost.
- **Cross-check before writing:** ad spend and results per campaign must add up to the
  campaign rows, and campaign spend must add up to the account total (±$0.02 rounding). If
  they don't, an ad or campaign is missing from a paginated or filtered response. Fix that first.
- Weekly buckets start on the 1st. Buckets with zero spend are **omitted**, so add them back
  as $0 "sin entrega". A short last bucket (e.g. 29–31) needs its day count on the label.
- An ad missing from the ranking output = "Sin ranking en el período", not an error. It
  happens even for ads with real spend and results, so don't guess the cause on the slide.
- Meta's ranking compares an ad with its auction peers, not with this account. An ad can be
  "all good" by Meta and still be the most expensive per result here. The template's chip
  notes cover how to show that without it reading as praise.

### Partial periods

When the period isn't a whole calendar month (month to date, "primera quincena", custom dates):
- **Compare rates, not totals.** Cost per result, CTR, CPM and CPC can be compared with the
  previous full month; spend and result counts can't. Otherwise pull the **same number of
  days** of the previous month (e.g. Aug 1–15 vs Sep 1–15) and compare everything. Say
  which comparison you used on the closing slide.
- Name it honestly everywhere: cover ("Primera quincena de *septiembre* 2026"), footer
  label ("1–15 sep 2026"), `<title>` ("Elite Medspa 1–15 Sep 2026"), recommendations
  ("para el resto de septiembre").
- Weekly chart: plot spend **per day** when any bucket is shorter than 7 days (template comment explains).
- File name gets the day range so a later full-month report doesn't overwrite it (Step 4).

## Step 2: Analyze

Compute and keep these handy (numbers are formatted US style: `$1,234.56`, `2.61%`):

- Cost per result for the account = total spend ÷ total results.
- Each campaign's **share of spend vs share of results**. The gap between the two is the
  main story. A campaign getting 20% of spend and 34% of results should get more budget.
- Rank campaigns by cost per result, and flag best/worst CTR, CPC and CPM.
- Per ad: spend with zero results; variants beating their original; Meta's "below
  average" flags (quality / engagement / conversion).
- Pacing: $/day per week (spend ÷ days in bucket), CTR trend across weeks, and when
  delivery actually started (mention it if the month is partial).
- Status changes during the period (from the ad set pull + activity log): a paused winner
  is often the biggest finding. Recommend turning it back on only "si la pausa ya no es
  necesaria", because the pause may have been deliberate (e.g. the client ran out of stock or schedule).

**Findings (exactly 4)** each lead with one number. Good patterns: the winner; the
biggest money leak; a structural issue (too many ads splitting a small budget, an ad with
no results); delivery health (anomaly signal + frequency).

**Recommendations (4, or 6 with appointments)**: concrete actions in the ad account,
ordered by expected impact, each naming the exact campaign/ad and the number that
justifies it. Prefer moving budget between campaigns over raising total spend. When
raising a budget, suggest doing it gradually (~20–50% steps) so Meta doesn't restart learning.
Say "pausar", not "eliminar". Don't recommend things you can't back with this month's
data. Don't change anything in the ad account: the deck *recommends*, the user decides.

**Tone:** warm, plain Spanish for a medspa owner (the Maria avatar: Latina, South Florida,
busy). Short sentences. Keep the metric acronyms Meta shows (CTR, CPC, CPM) but explain in
words what matters ("la campaña que más conversaciones trae por dólar"). Use "tú"/neutral
forms, not "usted"-heavy corporate language.

## Step 3: Brand

Source of truth, in order:
1. `Clients\<client>\brand-context.md` (logo, colors, fonts, website).
2. The client's website, read through the **Browser pane** (client sites are React SPAs;
   a plain fetch returns an empty shell). Use `javascript_tool` to read `:root` CSS
   variables (`--primary`, `--secondary`, `--accent`, `--background`...; often HSL like
   `22 24% 18%`, so convert to hex), body/h1 `font-family`, and the header logo's `outerHTML`.
3. Logo image files in the client folder (`logo.png`, `og_image.png`, `favicon.png`).

**Logo:** if the site's logo is an HTML text wordmark, recreate it with the template's
`.mark` markup, matching font, italics, tracking and subline. If it's an image in the
client folder, embed it as a base64 data URI (Artifacts block external images). If the
only copy is on the website, **ask before downloading it**. Check that the logo reads
on the dark cover; if not, use a light version or make the cover light.

If `brand-context.md` didn't exist, offer to save what you found there (colors, fonts,
logo description, website, Meta ad account ID) so the next report starts faster.

## Step 4: Build the deck

1. Load the `artifact-design` skill (required before writing an Artifact). The template
   already settles the design, so its job here is the fundamentals check, not a redesign.
   The template deliberately uses one fixed look (light slides, dark cover and closing),
   which artifact-design allows. Don't add dark-mode blocks.
2. Copy `assets/deck-template.html` to
   `C:\Users\horac\Claude\Clients\<client>\reports\meta-ads-<YYYY-MM>.html`
   (partial period: `meta-ads-<YYYY-MM>-<DD>-<DD>.html`, e.g. `meta-ads-2026-09-01-15.html`).
   Saving it in the client folder keeps a record and lets you republish to the same URL.
   If a previous report exists there, reuse its campaign color mapping.
3. Set the brand tokens and fonts, then fill every double-brace placeholder and expand every
   REPEAT block. The comments in the template explain the chart geometry, share bars,
   chip mapping, paused campaigns, ad-name cleanup and table density. Follow them rather
   than re-deriving layouts, and delete each guidance comment once its block is filled.
   For edits, use the Edit/Write tools or PowerShell. **Python isn't installed** on this machine.
4. If you drop a slide (e.g. slide 4 with mixed result types), renumber the `<b>0N</b>`
   page numbers in the footers.
5. Check before publishing:
   - Grep the file for `{{`: no matches.
   - No other client's name, colors or numbers are left over. Grep for names from other
     client folders if you started from an older report.
   - Chart bar heights match `value / SCALE_MAX * 140`, and every label is a real value.
   - Totals on slides 2, 4 and 5 agree with each other.
6. Publish with the Artifact tool:
   - title (in `<title>`): `<Client short name> <Mes> <Año>`, e.g. `Elite Medspa Agosto 2026`
   - `description`: one sentence in the report's language
   - `favicon`: `📈`, `icon`: `chart`
   - Republishing the same file path keeps the URL. Use that for edits.

## Step 5: Report back

Reply in the language the user wrote in (the deck language can differ). Keep it short:
the link, 3–5 bullets with the headline numbers and the top recommendation, and anything
you couldn't verify or assumed (e.g. no previous month to compare, logo recreated as text,
brand colors pulled from the website). Don't paste the whole deck back as text.
Offer a plain-text version for WhatsApp/email, or a PPTX/Canva export, in one line.

## Reference: the first report

`references/example-elite-aug-2026.md` has the numbers, findings and recommendations
from the Elite Medspa August 2026 deck this skill was built from. Read it to calibrate
depth and tone. Don't copy its content.
