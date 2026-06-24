# GoHighLevel Email Builder API Reference

## Table of Contents
1. [Authentication](#authentication)
2. [Create Template](#create-template)
3. [Fetch Templates](#fetch-templates)
4. [Update Template](#update-template)
5. [Delete Template](#delete-template)
6. [Error Codes](#error-codes)
7. [Troubleshooting](#troubleshooting)

## Authentication

All requests require these headers:

```
Authorization: Bearer <PRIVATE_INTEGRATION_TOKEN>
Version: 2021-07-28
Content-Type: application/json
Accept: application/json
```

**Private Integration Tokens** are created in the GHL dashboard at:
Settings > Private Integrations > Create New Integration

Required scopes for email template operations:
- `emails/builder.write` (create/update/delete)
- `emails/builder.readonly` (fetch)

Tokens may expire after 90 days — regenerate if you get 401 errors.

## Create Template

Creates a new email template in a GoHighLevel sub-account.

```
POST https://services.leadconnectorhq.com/emails/builder
```

### Request Body

```json
{
  "locationId": "string (required) - The sub-account/location ID",
  "title": "string (required) - Display name for the template",
  "body": "string (required) - HTML content of the email",
  "type": "string - Template type, use 'html' for raw HTML templates"
}
```

### Success Response (201)

```json
{
  "id": "template-id-string",
  "locationId": "location-id",
  "title": "Template Name",
  "body": "<html>...</html>",
  "type": "html",
  "createdAt": "2026-01-01T00:00:00.000Z",
  "updatedAt": "2026-01-01T00:00:00.000Z"
}
```

### Important: Two-Step Creation Required

The `POST` endpoint creates a template with **default placeholder content** regardless of what `body`, `editorContent`, or other content fields you include. To set the actual HTML content, you must follow up with a `PATCH` request:

```
PATCH https://services.leadconnectorhq.com/emails/builder/{templateId}
```

```json
{
  "locationId": "string (required)",
  "title": "string (required)",
  "editorType": "html",
  "editorContent": "string (required) - The actual HTML content",
  "subjectLine": "string (optional) - The email subject line"
}
```

### Notes
- Template names should be unique within a location
- The `body` field on `POST` does NOT set the email content — use `editorContent` on `PATCH` instead
- Use inline CSS styles for maximum email client compatibility
- The API base URL is `services.leadconnectorhq.com`, NOT `api.gohighlevel.com`
- All requests require `Accept: application/json` and `User-Agent` headers to avoid Cloudflare 403 blocks

> **Important**: The GHL API documentation is JavaScript-rendered and difficult to scrape
> programmatically. If you encounter unexpected fields or errors, verify the current schema
> at https://marketplace.gohighlevel.com/docs/ghl/emails/create-template/

## Fetch Templates

Retrieve email templates for a location.

```
GET https://services.leadconnectorhq.com/emails/builder?locationId={locationId}
```

Returns a list of templates for the specified location.

## Update Template

GHL has **two separate endpoints** for updating an email template, one for content and one for the displayed name. Don't conflate them.

### Update HTML content / subject line / preview text

```
PATCH https://services.leadconnectorhq.com/emails/builder/{templateId}
```

Body:
```json
{
  "locationId": "...",
  "title": "...",
  "editorType": "html",
  "editorContent": "<full HTML>",
  "subjectLine": "...",
  "previewText": "...",
  "fromName": "...",
  "fromEmail": "..."
}
```

This endpoint is being deprecated but still works. It does **NOT** rename the template — `title` here is ignored for the displayed name.

### Rename a template (or update settings: archived, fromName, fromEmail, previewText)

```
PATCH https://services.leadconnectorhq.com/emails/public/v2/locations/{locationId}/templates/{templateId}
```

Body (any subset; all fields optional):
```json
{ "name": "New Template Name" }
```

Returns 200 with the full template object including the updated `name`. This is the **only** endpoint that renames a template. The accepted body fields all work: `name`, `templateName`, and `title` are all interpreted as the displayed name.

### Pitfall — `POST /emails/builder/data`

This endpoint exists and returns `201 {"ok":true,...}` when called with a full payload (`name`, `html`, `editorType`, `updatedBy`, etc.) — but it does NOT change the displayed name. Don't use it for renaming. Use the v2 PATCH above.

> **Reference:** https://marketplace.gohighlevel.com/docs/ghl/emails/update-email-template-v-2

## Delete Template

Delete an email template.

```
DELETE https://services.leadconnectorhq.com/emails/builder/{locationId}/{templateId}
```

## Error Codes

| Code | Meaning | Common Cause |
|------|---------|--------------|
| 201  | Created | Template created successfully |
| 400  | Bad Request | Malformed JSON body or missing required fields |
| 401  | Unauthorized | Invalid, expired, or missing token |
| 404  | Not Found | Invalid locationId or template doesn't exist |
| 422  | Unprocessable Entity | Validation error (e.g., duplicate name, invalid HTML) |

## Troubleshooting

### 401 Unauthorized
- Verify the Private Integration Token is correct and not expired
- Check that the token has `emails/builder.write` scope
- Regenerate the token at Settings > Private Integrations if needed

### 404 Not Found
- Verify the `locationId` is correct — copy it from the GHL URL when viewing the sub-account
- Ensure the Private Integration Token has access to the specified location

### 422 Unprocessable Entity
- Check for duplicate template names in the location
- Verify the HTML body is valid and properly escaped in the JSON payload
- Try a simpler HTML body to isolate the issue

### Connection Errors
- The API base URL is `https://services.leadconnectorhq.com` — verify no typos
- Check network connectivity and firewall rules
