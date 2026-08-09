# DIU Admission AI — API Contract

Version: `0.1.0`  
Status: Initial Phase 2 contract

This contract is the shared boundary between the FastAPI backend and the Next.js frontend. JSON examples below demonstrate structure only. They are not verified DIU admission facts.

## Conventions

- Base URL is supplied through deployment configuration; paths below are relative to it.
- Request and response bodies use `application/json` and UTF-8.
- Unknown request fields should be rejected to expose integration mistakes early.
- Required strings must be trimmed, non-empty strings.
- URLs returned as sources must be absolute `https` URLs to official DIU pages.
- Optional fields may be omitted. They should not be returned as empty strings.

## Error response

All application errors use this stable shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request could not be validated.",
    "details": [
      {
        "field": "message",
        "message": "This field is required."
      }
    ]
  }
}
```

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `error.code` | string | yes | Stable machine-readable identifier. |
| `error.message` | string | yes | Safe, user-understandable summary. |
| `error.details` | array | no | Field-level details; each item requires `field` and `message`. |

Expected HTTP statuses:

- `200 OK`: successful request.
- `400 Bad Request`: malformed JSON or structurally invalid request.
- `422 Unprocessable Entity`: well-formed request with failed field validation.
- `500 Internal Server Error`: unexpected server failure; no stack trace or secret is exposed.
- `503 Service Unavailable`: a required model, database, or downstream service is unavailable.

## Health

### `GET /health`

No request body.

Successful response (`200`):

```json
{
  "status": "ok"
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `status` | string | yes | Currently the literal value `ok`. |

## Chat

### `POST /api/chat`

This endpoint is contractual only in Phase 2 and is not implemented yet.

Request:

```json
{
  "message": "What documents are required for DIU admission?",
  "language": "en"
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `message` | string | yes | 1–2000 characters after trimming. |
| `language` | string | yes | One of `en`, `bn`, or `banglish`. |

Successful response (`200`; schema example only):

```json
{
  "answer": "Example response structure only",
  "sources": [
    {
      "title": "DIU official source",
      "url": "https://daffodilvarsity.edu.bd/example-only"
    }
  ],
  "confidence": "high",
  "language": "en"
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `answer` | string | yes | Non-empty generated answer. |
| `sources` | array | yes | May be empty when no source supports the answer. |
| `sources[].title` | string | yes | Non-empty source title. |
| `sources[].url` | string | yes | Absolute official DIU HTTPS URL. |
| `confidence` | string | yes | One of `high`, `medium`, or `low`. |
| `language` | string | yes | One of `en`, `bn`, or `banglish`. |

## Eligibility

### `POST /api/eligibility`

This endpoint is contractual only in Phase 2 and is not implemented yet. Eligibility must be decided by the backend rule engine, never by the frontend.

Request:

```json
{
  "program": "CSE",
  "ssc_gpa": 4.5,
  "hsc_gpa": 4.2,
  "group": "Science",
  "diploma": false
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `program` | string | yes | Non-empty backend-recognized program identifier. |
| `ssc_gpa` | number | no | Between `0.0` and `5.0`, inclusive. |
| `hsc_gpa` | number | no | Between `0.0` and `5.0`, inclusive. |
| `group` | string | no | Non-empty academic group name. |
| `diploma` | boolean | yes | Whether the applicant follows a diploma pathway. |

GPA and group fields are optional so the backend can return `insufficient_information` rather than forcing the client to invent missing values.

Successful response (`200`; schema example only):

```json
{
  "status": "eligible",
  "reason": "Example structure only",
  "source": {
    "title": "Official DIU source",
    "url": "https://daffodilvarsity.edu.bd/example-only"
  }
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `status` | string | yes | `eligible`, `not_eligible`, or `insufficient_information`. |
| `reason` | string | yes | Non-empty explanation from the backend. |
| `source` | object | no | Omitted when no official source supports the result. |
| `source.title` | string | yes when source exists | Non-empty source title. |
| `source.url` | string | yes when source exists | Absolute official DIU HTTPS URL. |

## Programs

### `GET /api/programs`

This endpoint is contractual only in Phase 2 and is not implemented yet. No request body.

Successful response (`200`; schema example only):

```json
{
  "programs": [
    {
      "id": "example-program-id",
      "name": "Example program name",
      "degree": "Example degree",
      "faculty": "Example faculty",
      "admission_url": "https://daffodilvarsity.edu.bd/example-only"
    }
  ]
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `programs` | array | yes | May be empty. |
| `programs[].id` | string | yes | Stable, unique program identifier. |
| `programs[].name` | string | yes | Non-empty official program name. |
| `programs[].degree` | string | no | Non-empty when present. |
| `programs[].faculty` | string | no | Non-empty when present. |
| `programs[].admission_url` | string | no | Absolute official DIU HTTPS URL. |

## Sources

### `GET /api/sources`

This endpoint is contractual only in Phase 2 and is not implemented yet. No request body.

Successful response (`200`; schema example only):

```json
{
  "sources": [
    {
      "id": "example-source-id",
      "title": "Example DIU source title",
      "url": "https://daffodilvarsity.edu.bd/example-only",
      "retrieved_at": "2026-08-10T12:00:00Z"
    }
  ]
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `sources` | array | yes | May be empty. |
| `sources[].id` | string | yes | Stable, unique source identifier. |
| `sources[].title` | string | yes | Non-empty source title. |
| `sources[].url` | string | yes | Absolute official DIU HTTPS URL. |
| `sources[].retrieved_at` | string | no | ISO 8601 UTC timestamp when present. |

## Change policy

Changes require coordination between both members. Prefer additive optional fields. Breaking changes require a contract version update and synchronized backend/frontend work.

