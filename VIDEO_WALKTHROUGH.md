# Video Walkthrough Script (10–12 minutes)

A step-by-step demonstration script for the Brand Q&A Agent. It follows the assignment's required order
and covers all 16 steps in roughly 11 minutes.

> ⚠️ **Before you record:** do **not** show any API key, token, `.env` file, or the Pinecone console's
> key/secret fields on camera. Keep the editor/tab showing secrets closed. If you must open `.env`,
> blur or scroll past it. Narration is enough — no need to display credentials.

**Setup before recording**

- Service already built and running (`docker compose up --build` once), or ready to start it live.
- A terminal and a browser (for Swagger `/docs`) side by side.
- Editor open at the project root, with the key files from steps 11–14 in easy reach.
- The sample corpus under `data/sample_documents/` and `scripts/ingest_sample_data.py` available.

**Suggested timing**

| Step | Topic | ~Time |
| --- | --- | --- |
| 1 | One-command start | 0:30 |
| 2 | `/health` | 0:30 |
| 3 | Ingest acme | 0:40 |
| 4 | Re-ingest (no duplicate growth) | 0:30 |
| 5 | Normal question | 0:30 |
| 6 | Answer + citations + trace | 0:40 |
| 7 | Off-topic question | 0:30 |
| 8 | Rewrite/retry + not-found | 0:50 |
| 9 | Same question as globex | 0:30 |
| 10 | Acme data inaccessible | 0:30 |
| 11 | Folder structure | 1:00 |
| 12 | Chunking + metadata | 1:00 |
| 13 | LangGraph state + edges | 1:30 |
| 14 | Tenant isolation | 1:00 |
| 15 | Run the two tests | 1:00 |
| 16 | Trade-off / rough edge / next step | 1:00 |

---

## Step 1 — Start the service with one command (~0:30)

Show the terminal at the project root.

```bash
docker compose up --build
```

Say: *"The whole service starts with one command. This builds the image, starts the container, and
serves the API on port 8000."* Point out the startup log lines that show the configured providers:

```
application starting | app_env=local vector_store=memory llm_provider=openai embedding_provider=hashing
```

Mention the local (non-Docker) alternative you'd use in development:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Step 2 — Show `/health` (~0:30)

```bash
curl http://localhost:8000/health
```

Expected (abridged):

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

Say: *"`/health` always returns HTTP 200, but it reports the **actual** reachability of each dependency —
it performs real probes, it doesn't just report healthy because a client was constructed. The overall
status is `unavailable` if the vector store is down, and `degraded` if anything else is."*

## Step 3 — Ingest for tenant `acme` (~0:40)

Ingest the sample corpus (helper script):

```powershell
.\.venv\Scripts\python.exe scripts\ingest_sample_data.py --tenant acme --api --base-url http://localhost:8000
```

Or ingest one URL document:

```bash
curl -X POST http://localhost:8000/tenants/acme/ingest \
  -H "Content-Type: application/json" \
  -d '{
        "documents": [
          {"url": "https://example.com/best-pm-tools-2026", "brand": "Asana"}
        ]
      }'
```

Expected:

```json
{"documents_stored": 1, "chunks_stored": 7, "errors": []}
```

Say: *"Each document is split into token-sized chunks, embedded, and stored under the tenant's own
namespace. The response reports documents stored, chunks stored, and any per-document errors."*

## Step 4 — Re-ingest and show no duplicate growth (~0:30)

Run the **same** ingest request again.

```bash
curl -X POST http://localhost:8000/tenants/acme/ingest \
  -H "Content-Type: application/json" \
  -d '{
        "documents": [
          {"url": "https://example.com/best-pm-tools-2026", "brand": "Asana"}
        ]
      }'
```

Expected: identical numbers.

```json
{"documents_stored": 1, "chunks_stored": 7, "errors": []}
```

Say: *"Same numbers — nothing grew. Documents get a stable SHA-256 `doc_id`, and vector ids are
`{doc_id}-{chunk_index}`, so a re-ingest **overwrites** the existing vectors instead of duplicating
them."*

## Step 5 — Ask a normal question (~0:30)

```bash
curl -X POST http://localhost:8000/tenants/acme/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What do reviewers say about Asana pricing compared to Trello?"}'
```

Say: *"This runs the LangGraph workflow: retrieve the top 5 tenant-scoped chunks, grade each for
relevance, then answer from the relevant ones."*

## Step 6 — Show answer + citations + trace (~0:40)

Expected:

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

Say: *"`citations` point back to the exact source chunks the answer used. `trace` is the **real** path
the graph took — each node appends its own entry via an `operator.add` reducer, so it's a genuine
execution record, not a fixed string."*

## Step 7 — Ask an off-topic question (~0:30)

```bash
curl -X POST http://localhost:8000/tenants/acme/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'
```

Say: *"The corpus can't answer this. Watch the trace — the grader rejects everything, so the graph
rewrites the question and retries once."*

## Step 8 — Show rewrite/retry and the not-found result (~0:50)

Expected:

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

Say: *"`found_in_corpus` is false, `citations` is empty, and the answer is the explicit not-available
message — it did **not** say 'Paris'. The trace shows the `retrieve → grade → rewrite → retrieve → grade`
path: it retried exactly once, then stopped. The not-found contract is enforced outside the LLM too, so
citations and the answer are cleared whenever no evidence was found."*

## Step 9 — Ask the same normal question as tenant `globex` (~0:30)

```bash
curl -X POST http://localhost:8000/tenants/globex/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What do reviewers say about Asana pricing compared to Trello?"}'
```

Expected:

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

## Step 10 — Show that Acme's data is inaccessible to Globex (~0:30)

Say: *"`globex` has ingested nothing, and even though the question is identical to the one `acme`
answered, `globex` gets a not-found result. The retrieve node records 'tenant has no documents' — it
never sees `acme`'s chunks."*

(Optional, if comfortable and with no secrets on screen: add a few vectors for `globex`, ask again, and
show that only `globex`'s own content appears — never `acme`'s.)

## Step 11 — Walk through the folder structure (~1:00)

Open the project in the editor and narrate the tree:

- `app/api/` — the three routes (`ingest.py`, `ask.py`, `health.py`) and `dependencies.py` (the DI
  container). *"We chose FastAPI because everything here is I/O-bound and async, and we get Pydantic
  models and OpenAPI docs out of the box."*
- `app/core/` — config, exceptions, logging, middleware, security.
- `app/services/` — ingestion, retrieval, grading, answering, citations, prompts.
- `app/pipelines/` — load → extract → normalise → hash → chunk → embed.
- `app/agents/` — the LangGraph graph, state, nodes and the conditional edge.
- `app/integrations/` — swappable LLM, embedding and vector-store adapters behind `BaseLLM`,
  `BaseEmbeddings`, `BaseVectorStore`, plus their factories.
- `app/repositories/` — the JSON document registry.
- `tests/` — `unit/`, `integration/`, `security/`, `agent/`.

## Step 12 — Explain chunking and metadata (~1:00)

Open `app/pipelines/document_chunker.py`.

Say: *"Chunking uses LangChain's `RecursiveCharacterTextSplitter` with a **token** length function —
`CHUNK_SIZE` 400 tokens and `CHUNK_OVERLAP` 50, both configurable. Tokens are the model's native unit, so
chunks align with the embedding context, and the 50-token overlap keeps ideas that straddle a boundary
together. The separator order is paragraph → line → sentence → word, so splits happen on natural
boundaries. Vector ids are `{doc_id}-{chunk_index}`."*

Open the metadata shape (e.g. from `app/pipelines/embedding_pipeline.py` or the ingestion docs):

```json
{
  "tenant_id": "acme",
  "doc_id": "483f254fe3e9935cf563ebc16ec90440600ddc6beac357c96a5c9852fcb89470",
  "chunk_index": 0,
  "source": "https://example.com/best-pm-tools-2026",
  "brand": "Asana",
  "content_hash": "54e489e56434bf51f4665d708fe217c79734b522e31ec6dc5af980b6c7921c2e",
  "text": "Asana's per-seat pricing scales quickly for larger teams..."
}
```

## Step 13 — Explain the LangGraph state and conditional edges (~1:30)

Open `app/agents/graph_state.py`, `app/agents/graph_builder.py`, and
`app/agents/edges/conditional_edges.py`.

Say: *"The graph state is a `TypedDict` holding `tenant_id`, `question`, `rewritten_question`,
`retrieved_chunks`, `relevant_chunks`, `retry_count`, `answer`, `found_in_corpus`, `citations`, and
`trace`. The `trace` field is `Annotated[list[TraceEntry], operator.add]`, which is why every node
appends to it instead of overwriting."*

*"There are four registered nodes: `retrieve`, `grade`, `rewrite`, and `generate_answer`. Route: START →
retrieve → grade, then a conditional edge."* Open `route_after_grade` and read it:

```python
def route_after_grade(state: GraphState) -> str:
    if state.get("relevant_chunks"):
        return ANSWER_NODE  # answer
    if state.get("retry_count", 0) == 0:
        return "rewrite"  # retry once
    return END  # not found
```

*"One detail worth calling out: the answer node is registered as `generate_answer`, not `answer`, because
LangGraph reserves state-key names as node names and `answer` is a state field. The trace label it writes
is still `answer`, so the public trace matches the spec."*

*"Grading uses the original question, so a rewrite can never widen what counts as relevant. And the retry
is capped at one — `retry_count` goes 0 → 1 and then the graph ends."*

## Step 14 — Explain tenant isolation (~1:00)

Open `app/core/security.py` and `app/integrations/vectorstores/base.py`.

Say: *"Isolation is enforced in three places. First, the API validates the tenant id against a strict
regex and rejects anything else with a 400. Second, the id is turned into a deterministic namespace,
`tenant-{id}`. Third, every vector-store method requires that namespace — Pinecone uses namespaces,
Chroma uses one collection per tenant, and the in-memory store uses one dictionary per namespace. There
is no global search API at all, and an optional metadata filter can only narrow results within the
tenant namespace. Every chunk also carries `tenant_id` in its metadata as a second layer."*

## Step 15 — Run pytest and show the mandatory tests (~1:00)

Run only the two mandatory assignment tests (tenant isolation + decision logic). The LLM is mocked, so no
API key is needed:

```powershell
.venv\Scripts\python.exe -m pytest tests/security/test_tenant_isolation.py tests/agent/test_graph_workflow.py -v
```

Expected (indicative):

```
tests/security/test_tenant_isolation.py::test_tenant_a_data_not_returned_for_tenant_b PASSED
tests/security/test_tenant_isolation.py::test_namespace_is_per_tenant PASSED
tests/agent/test_graph_workflow.py::test_relevant_chunks_produce_answer PASSED
tests/agent/test_graph_workflow.py::test_no_relevant_chunks_triggers_retry PASSED
tests/agent/test_graph_workflow.py::test_not_found_after_retry PASSED
============================== 5 passed in 1.23s ==============================
```

Then optionally show the full suite:

```powershell
pytest -q
```

Say: *"The LLM is mocked in tests, so these run offline with no API key. The two mandatory tests check
tenant isolation and the graph's decision logic: relevant chunks → answer; none → retry; none after
retry → not found."*

## Step 16 — Reflect: one trade-off, one rough edge, one future improvement (~1:00)

Be honest and specific.

- **Trade-off.** *"I chose LLM-based grading over a cosine-similarity threshold. Similarity measures
  topical overlap, not whether a chunk actually helps answer the question — grading makes the not-found
  behaviour trustworthy. The cost is one LLM call per retrieved chunk."*
- **Rough edge.** *"Stale-chunk tracking uses a local JSON registry, which isn't safe across multiple
  processes or replicas, and the in-memory vector store is process-local. Fine for this project, but it
  would need a shared store and a real vector DB at scale. Also, there's no authentication — `tenant_id`
  comes from the URL path, so production would need authN and authZ."*
- **Future improvement.** *"Add a shared registry (Postgres/Redis), a reranker to cut grading calls,
  streaming answers over SSE, and hybrid (dense + keyword) retrieval."*

Close by noting the full design write-up lives in `docs/` (`ARCHITECTURE.md`, `API_DOCUMENTATION.md`,
`INGESTION_PIPELINE.md`, `LANGGRAPH_WORKFLOW.md`, `SECURITY.md`, `DESIGN_DECISIONS.md`).

---

## Quick reference — all commands

```bash
# 1. start
docker compose up --build

# 2. health
curl http://localhost:8000/health

# 3. ingest (sample corpus)
.venv\Scripts\python.exe scripts\ingest_sample_data.py --tenant acme --api --base-url http://localhost:8000

# 3-4. ingest / re-ingest (URL)
curl -X POST http://localhost:8000/tenants/acme/ingest -H "Content-Type: application/json" \
  -d '{"documents": [{"url": "https://example.com/best-pm-tools-2026", "brand": "Asana"}]}'

# 5-6. ask (normal)
curl -X POST http://localhost:8000/tenants/acme/ask -H "Content-Type: application/json" \
  -d '{"question": "What do reviewers say about Asana pricing compared to Trello?"}'

# 7-8. ask (off-topic)
curl -X POST http://localhost:8000/tenants/acme/ask -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of France?"}'

# 9-10. ask as a different tenant
curl -X POST http://localhost:8000/tenants/globex/ask -H "Content-Type: application/json" \
  -d '{"question": "What do reviewers say about Asana pricing compared to Trello?"}'

# 15. mandatory tests
.venv\Scripts\python.exe -m pytest tests/security/test_tenant_isolation.py tests/agent/test_graph_workflow.py -v
```

> **Reminder:** keep credentials off camera. Never open or show the `.env` file, API keys, or any secret
> in a terminal, editor, or browser tab while recording.
