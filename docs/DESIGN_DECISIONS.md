# Design Decisions

Each decision below states the choice, the rationale, and the trade-off accepted. All decisions reflect
the implemented system.

---

## 1. FastAPI over Django/DRF

**Decision.** Use FastAPI with Uvicorn.

**Rationale.** The workload is I/O-bound (outbound HTTP fetches, LLM calls, vector-store calls), so a
native-async framework is a natural fit: every I/O path here is `async`. FastAPI also gives Pydantic-v2
request/response modelling and automatic OpenAPI/Swagger docs "for free", which keeps the API surface
clean and self-documenting.

**Trade-off.** Django brings a batteries-included ORM, admin and auth. Those are not needed for a
stateless RAG service, and adding them would add weight without benefit here. (If the service later
grows an admin UI or relational data model, that calculus could change.)

## 2. Namespace-per-tenant vs. separate indexes

**Decision.** One **namespace** per tenant (`tenant-{tenant_id}`) inside a single index, with `tenant_id`
also stored in every chunk's metadata.

**Rationale.** Namespaces give hard logical separation with a single index to operate and a single place
to manage dimensions/metric, and they scale to many small tenants without provisioning per-tenant
infrastructure. The spec explicitly suggests one namespace per tenant, and metadata filtering is added as
a second layer.

**Trade-off.** A shared index means a mis-scoped query could in principle span tenants if the namespace
were ignored — so the abstraction makes `namespace` a **mandatory** argument to every store method and
exposes no global-search path. Separate indexes per tenant would isolate more strongly but multiply
operational cost and complexity. See [SECURITY.md](SECURITY.md).

## 3. Pinecone primary, with pluggable adapter abstraction

**Decision.** Pinecone is the primary production backend; ChromaDB and an in-memory store are selectable
alternatives. All three implement `BaseVectorStore`, created by `build_vector_store(settings)`.

**Rationale.** Pinecone is serverless and requires no local infrastructure, matching the assignment.
Because business logic depends only on `BaseVectorStore`, the backend is a configuration choice
(`VECTOR_STORE_PROVIDER`), which makes local development and tests possible without external services.
The Chroma adapter maps a tenant to a **collection** (isolation equivalent to a namespace) and is
imported lazily so its dependency stays optional.

**Trade-off.** Maintaining three adapters is more code than one, and each backend has subtly different
score semantics (Chroma returns distances, normalised to `1 - distance`). The abstraction earns its keep
by enabling offline tests and provider portability.

## 4. SHA-256 document identity and `{doc_id}-{chunk_index}` vector ids

**Decision.** `doc_id = SHA-256(tenant_id + "::" + (normalised URL | "text::" + content_hash))`; vector
ids are `{doc_id}-{chunk_index}`.

**Rationale.** Deterministic ids make ingestion **idempotent**: re-ingesting the same document produces
identical ids, and an upsert overwrites in place rather than duplicating. Including the tenant in the
identity guarantees that identical content under two tenants never collides. Hashing (rather than a
sequential id) means no shared counter or central coordination is needed.

**Trade-off.** Two genuinely different documents that share the same URL (e.g. a page whose content
changed) map to the same `doc_id`; the new content overwrites the old, which is the desired behaviour.
Conversely, raw-text documents are keyed by content hash, so editing even one character produces a new
`doc_id` and leaves the old document's vectors behind — an accepted trade-off, since the registry tracks
documents by `doc_id`.

## 5. JSON registry vs. a database for stale-chunk tracking

**Decision.** Track ingested documents (and their `chunk_count`) in a local JSON file
(`DocumentRepository`, path `DOCUMENT_REGISTRY_PATH`). Writes use atomic replacement when supported,
with an in-place fallback for managed Windows/OneDrive folders that deny directory replacement.

**Rationale.** The registry is what closes the idempotency loop: it lets the service detect that a
document's chunk count *shrank* and delete the now-orphaned vector ids
(`{doc_id}-{chunk_index}`) that an upsert would otherwise leave behind. A file keeps the service
dependency-free and survives restarts, and it can be an ephemeral in-memory registry in tests
(`path=None`).

**Trade-off.** A JSON file is **not** safe for multiple processes/hosts writing concurrently — there is
no cross-process locking, and `os.replace` only guarantees per-write atomicity. For a multi-replica
deployment this must move to Postgres/Redis. It is also not a query surface; it stores exactly what the
cleanup logic needs.

## 6. LLM grading vs. a similarity threshold

**Decision.** Grade each retrieved chunk by asking the LLM (structured "relevant: yes/no" per chunk)
instead of keeping chunks above a cosine-similarity threshold.

**Rationale.** Similarity measures topical overlap, not whether a chunk actually helps answer the
question — a chunk can be topically adjacent yet useless. The assignment explicitly defines grading as
asking the LLM to judge relevance, and it makes the "not found" behaviour trustworthy: a high-similarity
but irrelevant chunk is rejected rather than used.

**Trade-off.** Grading costs one LLM call per retrieved chunk (latency and cost scale with
`RETRIEVAL_TOP_K`), whereas a threshold is free. Grading is bounded by a concurrency limit (5) and its
failures are handled gracefully: individual failures count as "rejected", and `LLMError` is raised only
if **every** call fails — so a partial outage degrades rather than fabricating relevance.

## 7. A single, capped retry

**Decision.** When no relevant chunk is found and `retry_count == 0`, rewrite the question once and
re-run retrieval; never retry again.

**Rationale.** A rewrite helps when the first query was phrased poorly, but unbounded retries would
multiply LLM cost and could loop forever. One retry is enough to satisfy the spec's behaviour ("tries
once more with a rephrased question, still finds nothing, and replies that the answer is not in the
corpus") while guaranteeing termination.

**Trade-off.** A genuinely hard question that needs two rewrites will return not-found. This is honest
and bounded rather than expensive and open-ended. The cap lives entirely in `retry_count` +
`route_after_grade`, so raising it later is a small, local change.

## 8. Structured output for grading

**Decision.** Grade with a Pydantic `GradingDecision` schema via the LLM's structured-output mode
(`BaseLLM.ainvoke_structured`), rather than parsing free-form "yes/no" text.

**Rationale.** Structured output returns a validated `relevant: bool` (plus a short `reason`), removing
brittle string parsing and the ambiguity of responses like "not exactly, but...". It also keeps the
decision path provider-agnostic — the LangChain adapter calls `with_structured_output(schema)`.

**Trade-off.** Structured output depends on provider support and adds a small amount of per-call
overhead. The benefit (a reliable boolean for routing) outweighs it, and failures are already handled as
rejections.

## 9. Treat retrieved content as untrusted

**Decision.** Wrap excerpts in `<<<EXCERPT ... EXCERPT>>>` delimiters and instruct the model, in the
system prompt, never to follow instructions found inside them; enforce the not-found contract outside the
LLM.

**Rationale.** Ingested documents are third-party content and a direct prompt-injection vector
("ignore previous instructions and…"). Delimiting the data and constraining the model reduces injection
risk, and because `BrandQAAgent.ask` empties citations and substitutes the not-found message when
`found_in_corpus` is false, a successful injection still cannot make the service fabricate a grounded
answer with citations.

**Trade-off.** Delimiters and a stricter system prompt consume some tokens and can make the model more
conservative. That conservatism is desirable here — this is an evidence-grounded assistant, not a
chatbot. See [SECURITY.md](SECURITY.md).

## 10. In-memory vector store for tests

**Decision.** Ship a real `InMemoryVectorStore` (cosine similarity, namespaces, metadata filtering) and
select it with `VECTOR_STORE_PROVIDER=memory`.

**Rationale.** Tests and local demos must run with no external services and no credentials. A real
in-process implementation (rather than a mock) exercises the same `BaseVectorStore` contract, including
namespace isolation, so the tenant-isolation test is meaningful. It is explicitly labelled as a distinct
backend — it is never presented as Pinecone.

**Trade-off.** It is process-local (data is lost on restart) and not tuned for scale, so it is a dev/test
backend only. The alternative — mocking the store — would give faster tests but far weaker coverage.

## 11. Hashing embeddings for offline tests

**Decision.** Provide a deterministic `HashingEmbeddings` provider (`EMBEDDING_PROVIDER=hashing`): a
feature-hashing bag-of-words embedding, L2-normalised, with unigrams and adjacent bigrams.

**Rationale.** The test-suite and local demos must run without an API key. A deterministic embedding
makes retrieval reproducible and lets the graph's decision logic be tested end-to-end off the network.

**Trade-off.** Feature hashing captures **lexical overlap only**, not deep semantics — it is not a
substitute for a real embedding model, and the docs say so explicitly. It is a development/test
convenience; production uses a real provider (`openai` / `google`).

## 12. Real health probes instead of construction checks

**Decision.** `GET /health` performs actual reachability probes (Pinecone `has_index` +
`describe_index_stats`, Chroma `heartbeat`, an embedding call, a minimal LLM call).

**Rationale.** A dependency is not "healthy" just because its client object was constructed. Real probes
make the endpoint useful for monitoring and for the demo. Overall status distinguishes a critical
failure (vector store → `unavailable`) from a partial one (any other component not healthy →
`degraded`).

**Trade-off.** `/health` is slower and consumes a little provider quota per call; a dedicated
lightweight liveness endpoint would be added separately for orchestrators, with `/health` reserved for
readiness.

## 13. Token-aware chunking (400 / 50)

**Decision.** Use `RecursiveCharacterTextSplitter` with `CHUNK_SIZE=400`, `CHUNK_OVERLAP=50`, and a
`tiktoken`-based length function; both settings are configurable.

**Rationale.** Tokens are the model's native unit, so token-sized chunks align with embedding/LLM
context better than character counts, and the spec suggests exactly this (400/50, recursive splitter).
The 50-token overlap preserves sentences and ideas that straddle a boundary. A character heuristic
(~4 chars/token) is used only if `tiktoken` is unavailable, so the service still runs.

**Trade-off.** Token counting is slightly more expensive than character counting, and chunk sizes are
approximate near separators. Both costs are negligible against the quality gain.

## 14. Consistent error hierarchy and DI container

**Decision.** A single `AppError` hierarchy with stable `code`/`status_code`, centralised exception
handlers, and a lazily-built `Container` for shared dependencies.

**Rationale.** Stable error codes and a single response envelope make the API predictable for clients
and tests, and ensure stack traces/secrets never leak. The container builds expensive objects once per
process and is injectable, so routes stay thin and tests can swap in fakes without touching production
code.

**Trade-off.** A few extra layers of indirection (container + `Depends` callables + factories) versus
constructing objects inline. The payoff — provider portability, testability, and a clean error surface —
is worth it for a service with this many external integrations.
