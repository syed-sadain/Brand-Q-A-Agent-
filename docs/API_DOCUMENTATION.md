# API Documentation

Complete reference for the Brand Q&A Agent HTTP API.

- **Base URL (local):** `http://localhost:8000`
- **Interactive docs:** [`/docs`](http://localhost:8000/docs) (Swagger UI), [`/redoc`](http://localhost:8000/redoc) (ReDoc)
- **OpenAPI schema:** [`/openapi.json`](http://localhost:8000/openapi.json)
- **Content type:** `application/json`
- **Diagnostics:** every response includes an `X-Request-ID` correlation header and a
  `Server-Timing` header with server-side application processing time in milliseconds.

All three endpoints are defined in `app/api/v1/` and mounted (with no version prefix) by
`app/api/router.py`.

---

## Endpoint summary

| Method | Path | Tag | Purpose |
| --- | --- | --- | --- |
| `POST` | `/tenants/{tenant_id}/ingest` | ingestion | Ingest URL-based or raw-text documents |
| `POST` | `/tenants/{tenant_id}/ask` | question answering | Ask a question about a tenant's corpus |
| `GET` | `/health` | health | Report dependency reachability |

---

## Path parameters

| Name | Type | Applies to | Rules |
| --- | --- | --- | --- |
| `tenant_id` | string | `/ingest`, `/ask` | 1–64 characters; must start and end with a letter or digit; only lowercase letters, digits, `-` and `_`. Validated against `^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$` (input is lower-cased and trimmed). Example: `acme`. |

An invalid `tenant_id` produces **`400` / `invalid_tenant_id`**.

---

## Error envelope

Every failure returns the same shape (defined by `app/schemas/common.py::ErrorResponse`):

| Field | Type | Notes |
| --- | --- | --- |
| `code` | string | Stable, machine-readable error code. |
| `message` | string | Human-readable, safe description. |
| `details` | object \| null | Optional extra context (present for validation errors). |

```json
{
  "code": "invalid_tenant_id",
  "message": "The tenant identifier is invalid."
}
```

### Error codes

| `code` | HTTP | Raised by | When |
| --- | --- | --- | --- |
| `invalid_tenant_id` | 400 | `InvalidTenantError` | Tenant id fails the regex / length rules. |
| `unsafe_url` | 400 | `UnsafeUrlError` | URL scheme not allowed, host blocked, or resolves to a private/reserved address. |
| `invalid_document_input` | 422 | `DocumentInputError` | Document payload structurally invalid. |
| `empty_document` | 422 | `EmptyDocumentError` | Document yields no usable text after extraction (or produces zero chunks). |
| `request_validation_error` | 422 | FastAPI `RequestValidationError` | Request body fails Pydantic validation (details include the errors). |
| `document_fetch_failed` | 502 | `DocumentFetchError` | Remote URL unreachable, non-2xx, unsupported content type, too large, or too many redirects. |
| `llm_error` | 502 | `LLMError` | The LLM provider failed (and **all** grading calls failed). |
| `llm_timeout` | 504 | `LLMTimeoutError` | The LLM provider timed out. |
| `vector_store_error` | 503 | `VectorStoreError` | The vector database is unavailable or the operation failed. |
| `embedding_error` | 502 | `EmbeddingError` | Embedding generation failed. |
| `empty_corpus` | 404 | `EmptyCorpusError` | Raised by `RetrievalService` when a tenant has no documents. Note: the graph's retrieve node catches this, so `/ask` for an empty tenant returns a normal not-found answer rather than a 404. |
| `configuration_error` | 500 | `ConfigurationError` | Misconfiguration (e.g. missing API key, embedding/index dimension mismatch). |
| `internal_error` | 500 | generic handler | Any unexpected exception; message is deliberately generic. |

---

## 1. `POST /tenants/{tenant_id}/ingest`

Ingest one or more documents. Accepts either URL-based documents (fetched and extracted by the service)
or raw-text documents. Re-ingesting the same document **overwrites** its vectors instead of duplicating
them.

### Request schema — `IngestRequest`

| Field | Type | Required | Constraints | Notes |
| --- | --- | --- | --- | --- |
| `documents` | array of `IngestDocumentRequest` | yes | 1–100 items | The documents to ingest. |

### `IngestDocumentRequest`

| Field | Type | Required | Constraints | Notes |
| --- | --- | --- | --- | --- |
| `url` | string (HTTP URL) \| null | conditional | Must be a valid absolute `http`/`https` URL | Exactly one of `url` / `text` must be present. |
| `text` | string \| null | conditional | `min_length: 1` (non-blank) | Exactly one of `url` / `text` must be present. |
| `source` | string \| null | no | `max_length: 512` | Optional source label. Auto-generated for raw text when omitted. |
| `brand` | string | yes | 1–128 chars | The brand the document discusses. |

Validation (`model_validator`): each document must provide **exactly one** of `url` or `text`; providing
both, or neither, returns `422 request_validation_error`.

### Response schema — `IngestResponse`

| Field | Type | Notes |
| --- | --- | --- |
| `documents_stored` | integer ≥ 0 | Number of documents stored (upserted). |
| `chunks_stored` | integer ≥ 0 | Number of chunks stored (upserted). |
| `errors` | array of `IngestError` | Per-document failures (partial successes are still reported). |

### `IngestError`

| Field | Type | Notes |
| --- | --- | --- |
| `source` | string | Source identifier of the failed document. |
| `code` | string | Machine-readable failure code. |
| `message` | string | Human-readable failure message. |

### Behaviour notes

- Documents are processed with **bounded concurrency** (semaphore, limit 4). One document's failure is
  recorded in `errors` and does not abort the batch.
- If **every** document fails, the first `AppError` is re-raised, so the endpoint returns that error's
  status (e.g. `502 document_fetch_failed`, `400 unsafe_url`).
- Documented error responses: `400`, `422`, `502`, `503`.

### Examples

URL-based:

```bash
curl -X POST http://localhost:8000/tenants/acme/ingest \
  -H "Content-Type: application/json" \
  -d '{
        "documents": [
          {"url": "https://example.com/best-pm-tools-2026", "brand": "Asana"}
        ]
      }'
```

```json
{"documents_stored": 1, "chunks_stored": 7, "errors": []}
```

Raw text:

```bash
curl -X POST http://localhost:8000/tenants/acme/ingest \
  -H "Content-Type: application/json" \
  -d '{
        "documents": [
          {
            "text": "Reviewers say Asana is powerful but pricier per seat than Trello, which offers a generous free tier.",
            "source": "manual-1",
            "brand": "Trello"
          }
        ]
      }'
```

Partial failure (one good document, one unreachable URL):

```json
{
  "documents_stored": 1,
  "chunks_stored": 3,
  "errors": [
    {"source": "https://nonexistent.invalid/x", "code": "document_fetch_failed", "message": "The document could not be retrieved."}
  ]
}
```

---

## 2. `POST /tenants/{tenant_id}/ask`

Answer a question using only the tenant's own ingested documents. Runs the LangGraph workflow
(retrieve → grade → maybe rewrite/retry → answer).

### Request schema — `AskRequest`

| Field | Type | Required | Constraints | Notes |
| --- | --- | --- | --- | --- |
| `question` | string | yes | 1–1000 chars | Natural-language question about the corpus. |

### Response schema — `AskResponse`

| Field | Type | Notes |
| --- | --- | --- |
| `answer` | string | Grounded answer, or the explicit not-found message. |
| `found_in_corpus` | boolean | `true` only when usable evidence was found. |
| `citations` | array of `Citation` | Evidence backing the answer; empty when `found_in_corpus` is `false`. |
| `trace` | array of `TraceEntry` | The actual, ordered graph execution trace. |

### `Citation`

| Field | Type | Notes |
| --- | --- | --- |
| `source` | string | Original source URL or label of the evidence. |
| `brand` | string | Brand the cited chunk belongs to. |
| `chunk_text` | string | Verbatim excerpt from the retrieved chunk (truncated to 500 chars). |

### `TraceEntry`

| Field | Type | Notes |
| --- | --- | --- |
| `node` | string | Node that appended the entry: `retrieve`, `grade`, `rewrite`, or `answer`. |
| `detail` | string | Human-readable description of what the node did. |

### Behaviour notes

- **Not-found contract:** when nothing relevant is found, `found_in_corpus` is `false`, `answer` is the
  constant `"The requested information is not available in the provided documents."`, and `citations`
  is forced to `[]` (see `BrandQAAgent.ask`). The `trace` is still returned.
- **Empty tenant:** the retrieve node catches `EmptyCorpusError` and records
  `"0 chunks retrieved (tenant has no documents)"`.
- **Grading failures** are counted as rejected; `LLMError` (`502`) is raised only if **all** gradings
  fail. A provider timeout surfaces as `504 llm_timeout`.
- Documented error responses: `400`, `422`, `503`, `504`.

### Example — normal answer

```bash
curl -X POST http://localhost:8000/tenants/acme/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What do reviewers say about Asana pricing compared to Trello?"}'
```

```json
{
  "answer": "Reviewers generally describe Asana as more powerful for complex workflows but pricier per seat, while Trello is noted as better value for small teams and offers a generous free tier.",
  "found_in_corpus": true,
  "citations": [
    {
      "source": "https://example.com/best-pm-tools-2026",
      "brand": "Asana",
      "chunk_text": "Reviewers frequently note that Asana's per-seat pricing becomes expensive for larger teams, while Trello offers a generous free tier and cheaper paid plans."
    }
  ],
  "trace": [
    {"node": "retrieve", "detail": "5 chunks retrieved"},
    {"node": "grade", "detail": "3 relevant, 2 rejected"},
    {"node": "answer", "detail": "Answer generated from 3 relevant chunks"}
  ]
}
```

### Example — not found (with rewrite/retry)

```bash
curl -X POST http://localhost:8000/tenants/acme/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'
```

```json
{
  "answer": "The requested information is not available in the provided documents.",
  "found_in_corpus": false,
  "citations": [],
  "trace": [
    {"node": "retrieve", "detail": "5 chunks retrieved"},
    {"node": "grade", "detail": "0 relevant, 5 rejected"},
    {"node": "rewrite", "detail": "Question rewritten and retry #1 scheduled"},
    {"node": "retrieve", "detail": "5 chunks retrieved"},
    {"node": "grade", "detail": "0 relevant, 5 rejected"}
  ]
}
```

### Example — tenant with no documents

```bash
curl -X POST http://localhost:8000/tenants/globex/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What do reviewers say about Asana pricing compared to Trello?"}'
```

```json
{
  "answer": "The requested information is not available in the provided documents.",
  "found_in_corpus": false,
  "citations": [],
  "trace": [
    {"node": "retrieve", "detail": "0 chunks retrieved (tenant has no documents)"},
    {"node": "grade", "detail": "0 relevant, 0 rejected"},
    {"node": "rewrite", "detail": "Question rewritten and retry #1 scheduled"},
    {"node": "retrieve", "detail": "0 chunks retrieved (tenant has no documents)"},
    {"node": "grade", "detail": "0 relevant, 0 rejected"}
  ]
}
```

---

## 3. `GET /health`

Reports the **actual** reachability of the vector store, embeddings and LLM. Always returns HTTP 200 —
the JSON body carries the status, not the HTTP code.

### Response schema — `HealthResponse`

| Field | Type | Notes |
| --- | --- | --- |
| `status` | `"healthy"` \| `"degraded"` \| `"unavailable"` | Overall service status. |
| `app_env` | string | Active environment name. |
| `version` | string | Application version (currently `1.0.0`). |
| `components` | object of `ComponentHealth` | Keyed by `vector_store`, `embeddings`, `llm`. |

### `ComponentHealth`

| Field | Type | Notes |
| --- | --- | --- |
| `status` | `"healthy"` \| `"degraded"` \| `"unavailable"` | Reachability of this dependency. |
| `provider` | string | Backend name, e.g. `pinecone`, `openai`, `hashing`. |
| `detail` | string \| null | Optional diagnostic message. |
| `latency_ms` | number \| null | Round-trip check latency. |

### Overall-status rules

- `unavailable` — the **vector store** is unavailable (critical dependency).
- `degraded` — the vector store is not unavailable, but some component is not `healthy`.
- `healthy` — all components are healthy.

The vector store may itself report `degraded` (e.g. Pinecone index does not exist yet), which makes the
overall status `degraded`.

### Example

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "healthy",
  "app_env": "local",
  "version": "1.0.0",
  "components": {
    "vector_store": {"status": "healthy", "provider": "memory", "detail": "in-memory store", "latency_ms": 0.02},
    "embeddings": {"status": "healthy", "provider": "hashing", "detail": "local deterministic embeddings", "latency_ms": 0.01},
    "llm": {"status": "healthy", "provider": "openai", "detail": null, "latency_ms": 142.5}
  }
}
```

---

## More curl examples

### Invalid tenant id → `400`

```bash
curl -i -X POST http://localhost:8000/tenants/Acme!/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "hello"}'
```

```json
{"code": "invalid_tenant_id", "message": "The tenant identifier is invalid."}
```

### Invalid payload (both `url` and `text`) → `422`

```bash
curl -i -X POST http://localhost:8000/tenants/acme/ingest \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"url": "https://example.com", "text": "x", "brand": "Asana"}]}'
```

```json
{
  "code": "request_validation_error",
  "message": "The request payload failed validation.",
  "details": {"errors": ["..."]}
}
```

### Unsafe URL (SSRF blocked) → `400`

```bash
curl -i -X POST http://localhost:8000/tenants/acme/ingest \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"url": "http://169.254.169.254/latest/meta-data/", "brand": "Acme"}]}'
```

```json
{"code": "unsafe_url", "message": "Fetching private or reserved IP addresses is not allowed."}
```

### Unreachable URL → `502`

```bash
curl -i -X POST http://localhost:8000/tenants/acme/ingest \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"url": "https://nonexistent.invalid/x", "brand": "Acme"}]}'
```

```json
{"code": "document_fetch_failed", "message": "The document could not be retrieved."}
```

### Health (PowerShell)

```powershell
Invoke-RestMethod -Uri http://localhost:8000/health
```
