# Engineering Report — Brand Q&A Agent

**Project:** Multi-tenant Brand Q&A RAG backend
**Deliverable:** `brand-qa-agent/` (FastAPI + LangChain + LangGraph + Pinecone)

This report documents what was built, how it was verified, and how every
requirement in the assignment maps to an implementation artifact. Statuses use
`PASS` / `PARTIAL` / `BLOCKED` / `FAIL`. `BLOCKED` means the code exists and is
exercised by tests, but a live end-to-end run could not be performed in this
environment (missing external credentials).

---

## 1. Executive summary

A clean, layered, production-minded backend was implemented end-to-end:

- **Ingestion** (`POST /tenants/{tenant_id}/ingest`) fetches or accepts text,
  extracts readable content, computes a stable SHA-256 `doc_id`, splits it with
  `RecursiveCharacterTextSplitter` (400 tokens / 50 overlap), embeds it, and
  upserts into a per-tenant vector namespace using `{doc_id}-{chunk_index}` ids.
  Re-ingesting the same document **overwrites** instead of duplicating.
- **Question answering** (`POST /tenants/{tenant_id}/ask`) runs a real LangGraph
  `StateGraph`: `retrieve → grade → (answer | rewrite → retrieve | END)`, with
  exactly **one** rewrite/retry, LLM relevance grading, grounded answers, real
  citations and a per-node execution `trace`.
- **Health** (`GET /health`) reports the *actual* reachability of the vector
  store, embedding provider and LLM provider.
- **Tenant isolation** is enforced in the vector-store layer via mandatory
  namespaces (`tenant-{tenant_id}`), not in route handlers, so it cannot be
  bypassed by any entry point.

The automated suite uses deterministic doubles and does not require provider
credentials. Live provider checks depend on the deployment's configured keys,
network access, and selected vector-store backend.

---

## 2. Requirement compliance matrix

### 2.1 Required technologies (B.1)

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| T1 | Python 3.11+ | PASS | Runs on Python 3.11.4; `requires-python = ">=3.11"` in [pyproject.toml](../pyproject.toml) |
| T2 | FastAPI web framework | PASS | [app/main.py](../app/main.py), [app/api/v1](../app/api/v1) |
| T3 | Pydantic v2 for all request/response bodies | PASS | [app/schemas/](../app/schemas) (`ask.py`, `ingest.py`, `citation.py`, `health.py`, `common.py`) |
| T4 | LangChain + LangGraph | PASS | [app/agents/graph_builder.py](../app/agents/graph_builder.py) (real `StateGraph`), `langchain-text-splitters` in [requirements.txt](../requirements.txt) |
| T5 | Pinecone as primary production vector DB | PASS | [app/integrations/vectorstores/pinecone_store.py](../app/integrations/vectorstores/pinecone_store.py); selected via `VECTOR_STORE_PROVIDER=pinecone` |
| T6 | ChromaDB as optional local/dev backend | PASS | [app/integrations/vectorstores/chroma_store.py](../app/integrations/vectorstores/chroma_store.py); in-memory store for tests |
| T7 | Configurable LLM provider (OpenAI/Anthropic/Google) | PASS | [app/integrations/llm/factory.py](../app/integrations/llm/factory.py) |
| T8 | Configurable embedding provider | PASS | [app/integrations/embeddings/factory.py](../app/integrations/embeddings/factory.py) (openai / google / hashing) |
| T9 | `RecursiveCharacterTextSplitter` | PASS | [app/pipelines/document_chunker.py](../app/pipelines/document_chunker.py) |
| T10 | BeautifulSoup4 for web extraction | PASS | [app/pipelines/text_extractor.py](../app/pipelines/text_extractor.py) |
| T11 | HTTPX for async HTTP | PASS | [app/pipelines/document_loader.py](../app/pipelines/document_loader.py) |
| T12 | Pytest + pytest-asyncio | PASS | [pyproject.toml](../pyproject.toml) (`asyncio_mode = "auto"`), [tests/](../tests) |
| T13 | Docker + Docker Compose | PASS | [Dockerfile](../Dockerfile), [docker-compose.yml](../docker-compose.yml) |
| T14 | Ruff (lint + format) | PASS | `ruff check .` and `ruff format --check .` pass |
| T15 | MyPy static type checking | PASS | `mypy app scripts` → *Success: no issues found in 71 source files* |
| T16 | All config via environment variables + `.env.example` | PASS | [app/core/config.py](../app/core/config.py), [.env.example](../.env.example) |
| T17 | No hardcoded credentials | PASS | Keys read only from settings; `.env` gitignored; `.env.example` holds placeholders |

### 2.2 API surface (B.2)

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| A1 | `POST /tenants/{tenant_id}/ingest` with `{documents:[...]}` (url **or** text + brand + optional source) | PASS | [app/api/v1/ingest.py](../app/api/v1/ingest.py), [app/schemas/ingest.py](../app/schemas/ingest.py) |
| A2 | Ingest response `{documents_stored, chunks_stored}` | PASS | Same; live run returned `{"documents_stored":1,"chunks_stored":1,"errors":[]}` |
| A3 | Stable `doc_id` (SHA-256), re-ingest overwrites (no duplicates) | PASS | [app/pipelines/document_hasher.py](../app/pipelines/document_hasher.py); verified live (counts unchanged on 2nd call) and in `tests/unit/test_ingestion.py` |
| A4 | `POST /tenants/{tenant_id}/ask` with `{question}` | PASS | [app/api/v1/ask.py](../app/api/v1/ask.py) |
| A5 | Ask response `{answer, found_in_corpus, citations[], trace[]}` | PASS | [app/schemas/ask.py](../app/schemas/ask.py); `tests/integration/test_ask_api.py` |
| A6 | Not-found → `found_in_corpus=false`, empty `citations`, honest answer | PASS | [app/agents/brand_qa_agent.py](../app/agents/brand_qa_agent.py#L87-L95) |
| A7 | `GET /health` → HTTP 200 with vector DB + LLM reachability | PASS | [app/api/v1/health.py](../app/api/v1/health.py); live run returned 200 + per-component statuses |

### 2.3 Tenant isolation (B.3) — *most important rule*

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| I1 | Data for one tenant is never returned for another | PASS | Namespaces in the vector store; [tests/security/test_tenant_isolation.py](../tests/security/test_tenant_isolation.py) |
| I2 | One namespace per tenant (or metadata filter — both OK) | PASS | `tenant-{tenant_id}` **and** metadata `tenant_id` are both applied; `metadata_filter` can only narrow, never widen |
| I3 | Isolation enforced at the data layer, not the handler | PASS | [app/services/retrieval_service.py](../app/services/retrieval_service.py), [app/integrations/vectorstores/base.py](../app/integrations/vectorstores/base.py) |

### 2.4 Ingestion pipeline (B.4)

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| P1 | Fetch URL / use raw text | PASS | [app/pipelines/document_loader.py](../app/pipelines/document_loader.py) |
| P2 | Extract readable text | PASS | [app/pipelines/text_extractor.py](../app/pipelines/text_extractor.py) |
| P3 | Compute `doc_id` | PASS | [app/pipelines/document_hasher.py](../app/pipelines/document_hasher.py) |
| P4 | Chunk with deliberate size/overlap (400 / 50, `RecursiveCharacterTextSplitter`) | PASS | [app/pipelines/document_chunker.py](../app/pipelines/document_chunker.py); `CHUNK_SIZE=400`, `CHUNK_OVERLAP=50` |
| P5 | Chunk metadata: `tenant_id, doc_id, chunk_index, source, brand` | PASS | [app/pipelines/embedding_pipeline.py](../app/pipelines/embedding_pipeline.py); asserted in `tests/unit/test_chunking.py` |
| P6 | Embed + upsert under tenant namespace, vector id `{doc_id}-{chunk_index}` | PASS | [app/pipelines/embedding_pipeline.py](../app/pipelines/embedding_pipeline.py); asserted in `tests/unit/test_chunking.py` |

### 2.5 Question-answering agent (B.5)

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| G1 | Real LangGraph `StateGraph` (not a single chain) | PASS | [app/agents/graph_builder.py](../app/agents/graph_builder.py) |
| G2 | State is a `TypedDict` holding tenant/question, retrieved/relevant chunks, retry and empty-corpus flags, answer, citations and trace | PASS | [app/agents/graph_state.py](../app/agents/graph_state.py) |
| G3 | Three nodes + one conditional edge | PASS | `retrieve`, `grade`, `answer` + conditional `grade → {answer \| rewrite \| END}`; `rewrite` returns to `retrieve` |
| G4 | `retrieve`: embed question, top-5 chunks, tenant-only | PASS | [app/agents/nodes/retrieve_node.py](../app/agents/nodes/retrieve_node.py); `RETRIEVAL_TOP_K=5` |
| G5 | `grade`: per-chunk LLM yes/no; keep "yes" chunks | PASS | [app/agents/nodes/grade_node.py](../app/agents/nodes/grade_node.py), [app/services/grading_service.py](../app/services/grading_service.py) |
| G6 | Decision: relevant → answer; empty tenant → END; otherwise rewrite and retry **once** | PASS | [app/agents/edges/conditional_edges.py](../app/agents/edges/conditional_edges.py); `tests/agent/test_graph_workflow.py` |
| G7 | `answer`: answer only from relevant chunks + build citations | PASS | [app/agents/nodes/answer_node.py](../app/agents/nodes/answer_node.py), [app/services/citation_service.py](../app/services/citation_service.py) |
| G8 | Every node appends one `trace` entry | PASS | Each node returns `{"trace":[TraceEntry(...)]}` with an additive reducer; asserted via trace in `tests/agent/test_graph_workflow.py` |

### 2.6 Code quality & operations (B.6)

| # | Requirement | Status | Evidence |
|---|-------------|--------|----------|
| Q1 | Pydantic models for every request/response body | PASS | [app/schemas/](../app/schemas) |
| Q2 | Async for LLM calls and URL fetching | PASS | `ainvoke`, `httpx.AsyncClient`, async services throughout |
| Q3 | Config from env vars, `.env.example`, never commit keys | PASS | [.env.example](../.env.example), [.gitignore](../.gitignore) |
| Q4 | One-command start (Dockerfile **or** Makefile/script) | PASS | [Dockerfile](../Dockerfile), [docker-compose.yml](../docker-compose.yml), [Makefile](../Makefile) |
| Q5 | Two automated pytest tests with the LLM mocked (no API key) | PASS | (1) [tests/security/test_tenant_isolation.py](../tests/security/test_tenant_isolation.py) (2) [tests/agent/test_graph_workflow.py](../tests/agent/test_graph_workflow.py) |
| Q6 | Clear errors for: unreachable URL, tenant with no data, LLM timeout | PASS | `document_fetch_failed` (502), `empty_corpus`/not-found (200 honest response), `llm_timeout` (504); [app/core/exceptions.py](../app/core/exceptions.py), [app/core/middleware.py](../app/core/middleware.py) |
| Q7 | Corpus of 10–15 documents about 2+ brands | PASS | 12 synthetic docs across Asana/Trello/Notion in [corpus.json](../data/sample_documents/corpus.json) → 24 chunks |

### 2.7 Evaluation-criteria coverage (Part E)

| Area | Status | How it is addressed |
|------|--------|---------------------|
| RAG quality | PASS | 400/50 chunking with full metadata; top-5 retrieval; LLM grading; honest not-found |
| Agent design | PASS | Real `StateGraph`, conditional edge, one retry, grounded answers, readable trace |
| API & code quality | PASS | Layered structure, Pydantic everywhere, async I/O, the two tests, error handling |
| Multi-tenancy & production sense | PASS | Namespace isolation, idempotent ingest, env config, one-command run |
| Communication | PASS | [README.md](../README.md), [docs/](../docs), [VIDEO_WALKTHROUGH.md](../VIDEO_WALKTHROUGH.md) |

---

## 3. Verification evidence

All commands run from the project root with the `.venv` interpreter.

| Check | Command | Result |
|-------|---------|--------|
| Tests | `python -m pytest -q` | **120 passed** (one upstream deprecation warning) |
| Lint | `python -m ruff check .` | **All checks passed** |
| Format | `python -m ruff format --check .` | **All Python files formatted** |
| Types | `python -m mypy app scripts` | **Success: no issues found in 71 source files** |
| Environment | `python scripts/verify_environment.py` | **RESULT: PASS** (exit 0) |
| Corpus ingest | `python scripts/ingest_sample_data.py --tenant acme` | **12 documents, 24 chunks, 0 errors, 24 vectors** |
| Registry permission fallback | Repository regression test + local corpus ingest | **Permission-denied replace falls back; ingest succeeds** |
| API contract | FastAPI integration tests | Health, ingest, ask, not-found and validation paths covered |

### Mandatory tests (run without an LLM API key)

Both are driven by a deterministic `FakeLLM` in
[tests/conftest.py](../tests/conftest.py)
and an offline `hashing` embedding + in-memory store — no network, no key.

1. **Tenant isolation** — ingest under `acme`; `globex` retrieves nothing
   (`vector_store.count("tenant-globex") == 0`), direct retrieval raises
   `EmptyCorpusError`, and `globex` returns `found_in_corpus=false` with empty
   citations. A second test covers the case where *both* tenants have data.
2. **Decision logic** — against the compiled graph:
   - relevant chunks → `["retrieve","grade","answer"]`.
   - none relevant, first attempt → one `rewrite`, two `retrieve`s, `rewrite_calls == 1`.
   - none relevant after retry → `["retrieve","grade","rewrite","retrieve","grade"]`,
     no `answer`, `found_in_corpus=false`.

---

## 4. Design decisions (summary)

Full rationale in [docs/DESIGN_DECISIONS.md](../docs/DESIGN_DECISIONS.md).

- **Namespace-per-tenant + metadata filter.** Namespacing is the hard boundary;
  a caller-supplied metadata filter is applied *in addition* and can only narrow.
- **Provider abstractions.** `BaseLLM`, `BaseEmbeddings`, `BaseVectorStore`
  keep business logic vendor-neutral and make tests trivial and key-free.
- **Idempotency via content identity.** `doc_id = SHA-256(tenant + url|text_hash)`
  and vector ids `{doc_id}-{chunk_index}`; a JSON document registry enables
  removal of *obsolete* chunks when a document shrinks on re-ingest.
- **One bounded retry.** `route_after_grade` caps retries at exactly one, so the
  graph can never loop.
- **Prompt-injection defence.** Retrieved excerpts are untrusted data, wrapped in
  `<<<EXCERPT … EXCERPT>>>`; system prompts forbid following embedded instructions.
- **SSRF-safe fetching.** Scheme/host checks, IP-literal checks, DNS resolution
  against private/reserved ranges, and re-validation of every redirect hop.

---

## 5. Known limitations and honest caveats

These are stated explicitly, per the assignment's emphasis on honesty.

1. **Live Pinecone run — BLOCKED.** The Pinecone adapter
   ([pinecone_store.py](../app/integrations/vectorstores/pinecone_store.py))
   is implemented and selectable via `VECTOR_STORE_PROVIDER=pinecone`, but no live
   Pinecone index was exercised in this environment (no credentials). All
   isolation/idempotency behaviour is verified against the in-memory store, which
   shares the same interface and the same tenant-scoping contract.
2. **Live LLM vendor call — BLOCKED.** The OpenAI/Anthropic/Google adapters are
   implemented; without an API key the LLM health probe correctly reports
   `unavailable` and `/ask` cannot produce an answer. The full question-answering
   path is verified with a deterministic fake LLM instead.
3. **Corpus is synthetic.** The 12 documents in `data/sample_documents/corpus.json`
   are synthetic, written to be realistic about Asana/Trello/Notion rather than
   scraped verbatim. The assignment explicitly permits composing text files.
4. **In-memory document registry by default.** `DOCUMENT_REGISTRY_PATH` defaults to
   a local JSON file; for horizontal scaling this should move to a shared store
   (e.g. Redis/Postgres). Noted as a next step.
5. **`hashing` embeddings are for offline dev/test only.** They are deterministic
   and dependency-free, not semantically strong; production requires a real
   embedding provider.

---

## 6. Repository layout

```
brand-qa-agent/
├── app/
│   ├── main.py                  # FastAPI app factory + lifespan
│   ├── api/                     # routes, DI container, router
│   ├── agents/                  # LangGraph state, nodes, edges, agent
│   ├── core/                    # config, security, exceptions, logging, middleware
│   ├── integrations/            # llm / embeddings / vectorstores (base + factory + providers)
│   ├── models/                  # internal domain models
│   ├── pipelines/               # loader, extractor, hasher, chunker, embedding pipeline
│   ├── repositories/            # document registry
│   ├── schemas/                 # Pydantic request/response models
│   ├── services/                # ingestion, retrieval, grading, answer, citation
│   └── utils/                   # text utils, retry, validators
├── tests/                       # unit / integration / security / agent
├── data/sample_documents/       # synthetic corpus (12 docs)
├── docs/                        # architecture, API, security, workflow, decisions
├── scripts/                     # verify_environment, ingest_sample_data
├── Dockerfile · docker-compose.yml · Makefile · pyproject.toml
└── .env.example · requirements*.txt
```

---

## 7. Next steps (with more time)

1. Run the full stack against a live Pinecone index and a live LLM vendor key,
   then record the walkthrough video using the real providers.
2. Move the document registry to a shared store and add connection pooling for
   the vector DB; add per-tenant rate limiting and auth (API keys/JWT).
3. Add observability: OpenTelemetry traces, metrics for retrieval/grade latencies,
   and dashboards.
4. Expand the evaluation harness with a labelled Q/A set to measure retrieval
   precision and answer grounding automatically.
