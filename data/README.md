# Sample data

This directory holds the **sample corpus** used to demonstrate and test the Brand Q&A
agent without any external network access or API key.

## Contents

| Path | Purpose |
| --- | --- |
| `sample_documents/corpus.json` | A JSON array of 12 sample documents used by `scripts/ingest_sample_data.py`. |

## Origin status — these are SYNTHETIC fixtures

The documents in `sample_documents/corpus.json` are **clearly labelled synthetic test
fixtures**. They are **not** real published articles, real reviews, or scraped web
pages, and they should never be presented as such.

Concretely:

- Every document carries the flag `"synthetic": true`.
- Every `source` uses an obviously fake, non-resolvable label with a `synthetic://`
  scheme, for example `synthetic://pm-tools/asana-pricing-overview-1`. There are no
  real review-site URLs anywhere in this corpus.
- The text is deliberately illustrative and generic. It uses hedged phrasing such as
  "reviewers generally describe …" and "entry tiers are commonly described as …".
  It avoids specific prices, specific feature inventories, and any claim attributed to
  a named real publication. No fabricated statistic is presented as a real fact.

This approach follows the assignment guidance that, when internet access or source
extraction is unavailable, synthetic fixtures may be created **provided they are
clearly labelled and explained as not being real public articles**.

## What the corpus covers

- **Category:** Project Management Software.
- **Brands:** Asana, Trello, Notion — 4 documents each, evenly distributed.
- **Topics:** pricing and comparisons, small-team fit, large-organisation /
  enterprise concerns, ease of use, collaboration, integrations, reviewer opinions,
  migration considerations, free tiers and paid tiers, project views
  (boards / timelines / calendars), and documentation / knowledge-base use cases.

Some topics are **intentionally absent** so that the agent's "no supporting evidence"
behaviour can be demonstrated — for example, general-knowledge questions (such as
"what is the capital of France?") and questions about brands that are not in the
corpus.

## Document shape

Each element of the JSON array matches the ingestion API contract exactly:

```json
{
  "url": null,
  "text": "<the document text>",
  "source": "synthetic://pm-tools/<slug>",
  "brand": "Asana | Trello | Notion",
  "synthetic": true
}
```

`url` is always `null`: these are raw-text documents, and the ingestion scripts pass
only `text`, `source` and `brand` to the API / service (as required, since `url` is
`null`).

## How to use it

Ingest the corpus into a running server (defaults to `http://localhost:8000`):

```powershell
.venv\Scripts\python.exe scripts\ingest_sample_data.py --tenant acme --api
```

Ingest the corpus entirely offline, with no server and no API key, using the
in-memory vector store and deterministic hashing embeddings:

```powershell
.venv\Scripts\python.exe scripts\ingest_sample_data.py --tenant acme
```

Verify that the local environment can run the project:

```powershell
.venv\Scripts\python.exe scripts\verify_environment.py
```

The texts are long enough (roughly 200–450 words each) that the default chunking
settings (400-token chunks with 50-token overlap) split several documents into
multiple chunks, which is what makes multi-chunk retrieval meaningful.
