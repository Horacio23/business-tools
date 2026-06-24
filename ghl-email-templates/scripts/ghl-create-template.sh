#!/bin/bash
# GHL Email Template Creator
# Creates an email builder template in a GoHighLevel sub-account.
#
# NOTE: The GHL API requires a two-step process:
#   1. POST /emails/builder — creates the template shell (always with default placeholder content)
#   2. PATCH /emails/builder/:id — sets the actual HTML content via editorType + editorContent
#
# Usage: ghl-create-template.sh <TOKEN> <LOCATION_ID> <TEMPLATE_TITLE> <HTML_BODY> [SUBJECT_LINE]
#
# Exit codes:
#   0 - Template created successfully
#   1 - Invalid arguments
#   2 - API authentication error (401)
#   3 - API validation error (422)
#   4 - Other API error
#   5 - Template created but content update failed

set -euo pipefail

API_BASE="https://services.leadconnectorhq.com"
API_VERSION="2021-07-28"

if [ $# -lt 4 ]; then
  echo "Usage: ghl-create-template.sh <TOKEN> <LOCATION_ID> <TEMPLATE_TITLE> <HTML_BODY>" >&2
  echo "  TOKEN          - GHL Private Integration Token" >&2
  echo "  LOCATION_ID    - GHL sub-account/location ID" >&2
  echo "  TEMPLATE_TITLE - Name for the email template" >&2
  echo "  HTML_BODY      - Full HTML content of the email" >&2
  echo "  SUBJECT_LINE   - (Optional) Email subject line" >&2
  exit 1
fi

TOKEN="$1"
LOCATION_ID="$2"
TEMPLATE_TITLE="$3"
HTML_BODY="$4"
SUBJECT_LINE="${5:-}"

COMMON_HEADERS=(
  -H "Authorization: Bearer ${TOKEN}"
  -H "Version: ${API_VERSION}"
  -H "Content-Type: application/json"
  -H "Accept: application/json"
  -H "User-Agent: GHL-Email-Skill/1.0"
)

# ── Step 1: Create the template shell ──
CREATE_PAYLOAD=$(jq -n \
  --arg locationId "$LOCATION_ID" \
  --arg title "$TEMPLATE_TITLE" \
  '{
    locationId: $locationId,
    title: $title,
    type: "html"
  }')

TMPFILE=$(mktemp)
HTTP_CODE=$(curl -s -w '%{http_code}' -o "$TMPFILE" \
  -X POST "${API_BASE}/emails/builder" \
  "${COMMON_HEADERS[@]}" \
  -d "$CREATE_PAYLOAD")

RESPONSE=$(cat "$TMPFILE")
rm -f "$TMPFILE"

case "$HTTP_CODE" in
  200|201)
    TEMPLATE_ID=$(echo "$RESPONSE" | jq -r '.id // "unknown"' 2>/dev/null || echo "unknown")
    if [ "$TEMPLATE_ID" = "unknown" ]; then
      echo "ERROR: Template created but could not extract template ID." >&2
      echo "Response: ${RESPONSE}" >&2
      exit 4
    fi
    ;;
  401)
    echo "AUTH ERROR: Invalid or expired Private Integration Token." >&2
    echo "Response: ${RESPONSE}" >&2
    exit 2
    ;;
  422)
    echo "VALIDATION ERROR: The API rejected the template data." >&2
    ERROR_MSG=$(echo "$RESPONSE" | jq -r '.message // .error // "Unknown validation error"' 2>/dev/null || echo "$RESPONSE")
    echo "Details: ${ERROR_MSG}" >&2
    exit 3
    ;;
  *)
    echo "API ERROR: Unexpected status code ${HTTP_CODE} on create." >&2
    echo "Response: ${RESPONSE}" >&2
    exit 4
    ;;
esac

# ── Step 2: Patch the template with actual HTML content and subject line ──
if [ -n "$SUBJECT_LINE" ]; then
  PATCH_PAYLOAD=$(jq -n \
    --arg locationId "$LOCATION_ID" \
    --arg title "$TEMPLATE_TITLE" \
    --arg editorContent "$HTML_BODY" \
    --arg subjectLine "$SUBJECT_LINE" \
    '{
      locationId: $locationId,
      title: $title,
      editorType: "html",
      editorContent: $editorContent,
      subjectLine: $subjectLine
    }')
else
  PATCH_PAYLOAD=$(jq -n \
    --arg locationId "$LOCATION_ID" \
    --arg title "$TEMPLATE_TITLE" \
    --arg editorContent "$HTML_BODY" \
    '{
      locationId: $locationId,
      title: $title,
      editorType: "html",
      editorContent: $editorContent
    }')
fi

TMPFILE=$(mktemp)
HTTP_CODE=$(curl -s -w '%{http_code}' -o "$TMPFILE" \
  -X PATCH "${API_BASE}/emails/builder/${TEMPLATE_ID}" \
  "${COMMON_HEADERS[@]}" \
  -d "$PATCH_PAYLOAD")

RESPONSE=$(cat "$TMPFILE")
rm -f "$TMPFILE"

case "$HTTP_CODE" in
  200|201)
    echo "SUCCESS: Template '${TEMPLATE_TITLE}' created and content set."
    echo "Template ID: ${TEMPLATE_ID}"
    echo "Response: ${RESPONSE}"
    exit 0
    ;;
  401)
    echo "PATCH AUTH ERROR: Template ${TEMPLATE_ID} created but content update failed (401)." >&2
    echo "Response: ${RESPONSE}" >&2
    exit 5
    ;;
  *)
    echo "PATCH ERROR: Template ${TEMPLATE_ID} created but content update failed (HTTP ${HTTP_CODE})." >&2
    echo "Response: ${RESPONSE}" >&2
    exit 5
    ;;
esac
