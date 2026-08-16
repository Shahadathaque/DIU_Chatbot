# DIU Admission AI — API Contract

Version: `0.1.0`  
Status: Active shared contract

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
- `503 Service Unavailable`: a required model, database, downstream service, or private data artifact is unavailable. Recovery details are included when a local artifact must be restored or rebuilt.

## Request Validation Behavior

FastAPI validates request bodies before resolving endpoint dependencies. For the
body-based `POST /api/chat` and `POST /api/eligibility` endpoints, invalid JSON
fields, missing required fields, invalid enum values, empty required strings,
and out-of-range values return `422 Unprocessable Entity`. The validation
failure does not construct the chat, retriever, generator, or eligibility
service, so model and data initialization is not performed for rejected
requests.

Validation errors use the same contract envelope described above. Field names in
`error.details[].field` identify the request field without the transport prefix:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request could not be validated.",
    "details": [
      {
        "field": "message",
        "message": "Field required"
      }
    ]
  }
}
```

`GET /api/programs` and `GET /api/sources` are read-only endpoints with no
request body or required request fields. They therefore have no body validation
case that can return 422; unsupported HTTP methods return `405 Method Not
Allowed`, while valid GET requests resolve their dataset service normally.

## Health

### `GET /api/health` (compatibility alias: `GET /health`)

No request body.

Successful response (`200`):

```json
{
  "status": "ok",
  "timestamp": "2026-08-16T12:00:00Z",
  "environment": "production",
  "checks": {
    "database": "ok",
    "model_endpoint": "ok",
    "rag_backend": "ok"
  }
}
```

| Field | Type | Required | Validation |
| --- | --- | --- | --- |
| `status` | string | yes | Process liveness; currently the literal value `ok`. |
| `timestamp` | string | yes | UTC ISO-8601 timestamp ending in `Z`. |
| `environment` | string | yes | Active application environment. |
| `checks.database` | string | yes | `ok`, `not_configured`, or `error`. |
| `checks.model_endpoint` | string | yes | `ok`, `not_configured`, or `error`. |
| `checks.rag_backend` | string | yes | `ok`, `not_configured`, or `error`. |

The endpoint performs bounded dependency checks when services are configured.
`not_configured` is expected for optional services in development. A dependency
failure is reported in `checks` while the process-level liveness response still
uses HTTP `200`; deployment monitors should alert on individual `error` values.

`GET /api/live` is a fast liveness probe. It returns only `status`, `timestamp`,
and `environment` and does not contact PostgreSQL or the model provider.
`GET /api/ready` performs the same bounded dependency checks as `/api/health`.
Use `/api/live` for frequent wake-up checks and `/api/ready` for deployment
readiness checks.

## Chat

### `POST /api/chat`

This endpoint is implemented by the FastAPI backend. Retrieval and generation
are constructed only after the request body passes validation.

The retrieval layer normalizes and classifies common English, Bangla, and
Banglish admission wording before semantic search. Query reformulation only
selects an evidence intent; it never supplies admission facts. Successful
answers remain grounded in verified DIU chunks, and `sources` is populated from
their stored official URLs. Unsupported questions or questions lacking enough
verified evidence return the insufficient-information answer with an empty
`sources` array. Chat eligibility questions never make a decision: they direct
the user to the deterministic eligibility endpoint.

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

### `POST /api/chat/stream`

This additive endpoint accepts the same validated request as `/api/chat` and
returns `text/event-stream`. Each event contains a partial token:

```text
data: {"token":"Bring ","full":"Bring "}
```

The final event is named `done` and contains the normal chat response under
`response`. Invalid requests still return the contract-shaped `422` JSON error
before a chat service or model is initialized. Clients that do not support SSE
should continue using `/api/chat`.

## Eligibility

### `POST /api/eligibility`

This endpoint is implemented by the FastAPI backend. Eligibility must be
decided by the backend rule engine, never by the frontend or the LLM.

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

This endpoint is implemented by the FastAPI backend and derives its catalog from
the verified cleaned DIU dataset. No request body.

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

This endpoint is implemented by the FastAPI backend and derives its source list
from the verified cleaned DIU dataset. No request body.

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

Changes require coordination across backend and frontend consumers. Prefer additive optional fields. Breaking changes require a contract version update and synchronized backend/frontend work.
