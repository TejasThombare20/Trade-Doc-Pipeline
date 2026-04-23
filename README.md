# Nova — Trade Document Pipeline

A multi-agent system that ingests trade documents (Bill of Lading, Commercial Invoice, Packing List, Certificate of Origin), extracts structured fields via a vision LLM, validates them against customer-specific rule books, and routes each document to one of three outcomes: **auto-approve**, **human review**, or **draft amendment**.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Project Structure](#project-structure)
3. [Tech Stack](#tech-stack)
4. [Architecture & Workflow](#architecture--workflow)
5. [Agent Design](#agent-design)
   - [Extractor Agent](#1-extractor-agent)
   - [Validator Agent](#2-validator-agent)
   - [Router / Decision Agent](#3-router--decision-agent)
   - [Rule Book Extractor](#4-rule-book-extractor-agent)
6. [Tool Schemas — Input / Output Contracts](#tool-schemas--input--output-contracts)
7. [API Reference](#api-reference)
8. [Database Schema](#database-schema)
9. [Storage Layer](#storage-layer)
10. [Frontend Pages](#frontend-pages)
11. [Configuration Reference](#configuration-reference)
12. [Engineering Trade-offs](#engineering-trade-offs)
13. [Failure Handling & Safety Guarantees](#failure-handling--safety-guarantees)
14. [Observability](#observability)
15. [Cost Model](#cost-model)
16. [Sample Queries](#sample-queries)

---

## Quick Start

### Prerequisites

| Tool | Version |
|------|---------|
| Python | ≥ 3.11 |
| Node.js | ≥ 18 |
| PostgreSQL | ≥ 14 |
| poppler-utils | any (for `pdf2image`) |

```bash
# Install poppler (Ubuntu/Debian)
sudo apt-get install poppler-utils

# macOS
brew install poppler
```

### 1. Clone & Configure

```bash
git clone <repo-url>
cd trade-document-pipeline
```

### 2. Backend Setup

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — at minimum set DATABASE_URL and OPENAI_API_KEY
```

Create the database:

```bash
psql -U postgres -c "CREATE DATABASE nova;"
```

Run migrations (auto-applied on startup, or manually):

```bash
python -c "import asyncio; from app.db.migrate import run_migrations; asyncio.run(run_migrations())"
```

Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd client
npm install
npm run dev
```

The frontend dev server runs on `http://localhost:5173` and proxies `/api` and `/public` to the backend.

### 4. First Run

1. Open `http://localhost:5173`
2. Sign in — select the **gocomet** tenant, role **admin**
3. Navigate to **Rule Books** → upload a customer rule book PDF (see `samples/`)
4. Navigate to **Upload** → drop a trade document (PDF, image, or DOCX)
5. Watch the pipeline run live in the timeline — extraction → validation → decision
6. Open the document detail to see per-field confidence, validation result, and routing decision

---

## Project Structure

```
trade-document-pipeline/
├── server/                         # FastAPI backend (Python)
│   ├── app/
│   │   ├── main.py                 # App entrypoint, lifespan hooks
│   │   ├── agents/                 # The three core agents + rule book extractor
│   │   │   ├── extractor.py        # Extractor Agent
│   │   │   ├── validator.py        # Validator Agent
│   │   │   ├── router.py           # Router / Decision Agent
│   │   │   ├── rule_book_extractor.py  # Rule book parsing agent
│   │   │   └── _schema_helpers.py  # Pydantic → OpenAI strict JSON schema converter
│   │   ├── api/                    # FastAPI route handlers
│   │   │   ├── auth.py             # Tenant login / session management
│   │   │   ├── documents.py        # Upload, list, detail, SSE timeline
│   │   │   ├── rule_books.py       # Rule book management (admin only)
│   │   │   ├── files.py            # File serving
│   │   │   ├── health.py           # Liveness probe
│   │   │   ├── deps.py             # JWT auth dependency (request-scoped)
│   │   │   └── errors.py           # Global error handlers
│   │   ├── services/               # Business logic / orchestration
│   │   │   ├── pipeline.py         # Sequential pipeline: parse→extract→validate→decide
│   │   │   ├── documents.py        # Upload handling + pipeline kick-off
│   │   │   ├── llm.py              # OpenAI client wrapper (tool-use enforced)
│   │   │   ├── preprocessing.py    # PDF/image/DOCX → text + base64 images
│   │   │   ├── events.py           # In-memory SSE event bus (per session)
│   │   │   └── rule_books.py       # Rule book upload orchestration
│   │   ├── prompts/                # LLM system + user prompt templates
│   │   │   ├── extractor.py
│   │   │   ├── validator.py
│   │   │   ├── router.py
│   │   │   └── rule_book.py
│   │   ├── schemas/                # Pydantic models — agent I/O contracts
│   │   │   ├── common.py           # Enums: DocType, FieldStatus, Outcome, Severity
│   │   │   ├── extraction.py       # ExtractorOutput, ExtractedField
│   │   │   ├── validation.py       # ValidatorOutput, FieldValidation
│   │   │   ├── decision.py         # RouterOutput, Discrepancy
│   │   │   ├── rules.py            # RuleSpec, RuleBookExtractionOutput
│   │   │   ├── pipeline.py         # DocumentDetail, DocumentListItem, TimelineStep
│   │   │   └── api.py              # API request/response wrappers
│   │   ├── core/                   # Shared utilities
│   │   │   ├── config.py           # Settings loaded from .env
│   │   │   ├── auth.py             # JWT generation + validation
│   │   │   ├── errors.py           # Custom exceptions (AppError, LLMError, …)
│   │   │   ├── logging.py          # Structured logging + correlation IDs
│   │   │   └── pricing.py          # Token cost tracking helpers
│   │   ├── db/
│   │   │   ├── pool.py             # AsyncPG connection pool lifecycle
│   │   │   └── migrate.py          # SQL migration runner
│   │   ├── repositories/           # SQL data access layer
│   │   │   ├── documents.py        # CRUD: documents, sessions, runs, extractions, validations, decisions
│   │   │   ├── tenants.py          # Tenant CRUD
│   │   │   └── customers.py        # Customer CRUD
│   │   └── storage/                # File storage abstraction
│   │       ├── base.py             # Storage protocol (abstract interface)
│   │       ├── factory.py          # Creates local or S3 storage from config
│   │       ├── local.py            # Local filesystem storage
│   │       └── s3.py               # AWS S3 storage
│   ├── migrations/
│   │   ├── 001_init.sql            # Full schema (tenants, documents, pipeline tables)
│   │   └── 002_seed_gocoment_tenant.sql  # Merge customers into tenants; seed dev tenant
│   ├── requirements.txt
│   └── .env.example
│
├── client/                         # React + TypeScript frontend
│   ├── src/
│   │   ├── App.tsx                 # Route definitions
│   │   ├── pages/
│   │   │   ├── SignInPage.tsx       # Tenant + role picker
│   │   │   ├── DocumentsListPage.tsx   # Documents table with status + outcome
│   │   │   ├── DocumentDetailPage.tsx  # Extraction / validation / decision detail + timeline
│   │   │   ├── UploadPage.tsx      # Drag-drop upload + live progress
│   │   │   └── RuleBooksPage.tsx   # Rule book listing (admin only)
│   │   ├── components/
│   │   │   ├── AppShell.tsx        # Nav, sidebar, layout
│   │   │   ├── Timeline.tsx        # SSE-driven live pipeline step view
│   │   │   ├── UploadDropzone.tsx  # Drag-drop file input
│   │   │   ├── StatusBadges.tsx    # Color-coded status / outcome badges
│   │   │   └── ui/                 # Radix UI component wrappers
│   │   ├── contexts/
│   │   │   └── AuthContext.tsx     # Global session state (tenant, role, JWT)
│   │   ├── services/
│   │   │   ├── api.ts              # Typed fetch wrappers for all API endpoints
│   │   │   └── types.ts            # TypeScript mirrors of backend Pydantic schemas
│   │   └── lib/
│   │       └── utils.ts            # cn(), date formatting helpers
│   ├── package.json
│   └── vite.config.ts              # Proxies /api and /public to :8000
│
└── samples/                        # Sample documents for testing
    ├── clean_invoice.pdf           # Clean commercial invoice (all fields present)
    └── messy_bol.jpg               # Low-quality Bill of Lading scan
```

---

## Tech Stack

### Backend

| Layer | Choice | Version | Why |
|-------|--------|---------|-----|
| Web framework | **FastAPI** | 0.115.0 | Async-native, OpenAPI docs built in, Pydantic integration |
| Database | **PostgreSQL** + AsyncPG | 0.29.0 | JSONB for agent outputs, strong ACID guarantees, audit trail |
| LLM | **OpenAI API** (gpt-4o) | 1.51.0 | Vision + reasoning in one model; strict tool-use enforces structured output |
| Orchestration | Custom sequential | — | Three fixed steps; no branching needed. LangGraph pulled in for checkpoint storage only |
| Document parsing | pdfplumber + pdf2image | 0.11.4 / 1.17.0 | Native text extraction first; vision fallback for image-only PDFs |
| DOCX support | python-docx | 1.1.2 | Handles DOCX trade documents |
| Image processing | Pillow | 10.4.0 | PNG conversion for vision LLM |
| Retry logic | Tenacity | 9.0.0 | Exponential back-off on OpenAI transient failures |
| Auth | PyJWT | 2.9.0 | Tenant-level JWT sessions (no per-user auth needed for POC) |
| File storage | Local FS / AWS S3 | aioboto3 13.1.1 | Switchable via env var |
| Schema validation | Pydantic v2 | 2.9.2 | Strict models with `extra="forbid"` prevent silent field drift |

### Frontend

| Layer | Choice | Version |
|-------|--------|---------|
| Framework | React | 18.3.1 |
| Routing | React Router | v6 |
| Styling | Tailwind CSS + Radix UI | 3.4.13 |
| Build | Vite | 5.4.8 |
| Language | TypeScript | 5.6.2 |
| Icons | lucide-react | 0.446.0 |

---

## Architecture & Workflow

### Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DOCUMENT UPLOAD                               │
│    User drops PDF / image / DOCX via React UI                        │
│    POST /api/documents/upload → returns {document_id, session_id}    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ async background task (FastAPI)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 1 — PARSING  (mode: manual, no LLM tokens)                      │
│  services/preprocessing.py                                            │
│  • pdfplumber → extract native text  (fast path)                      │
│  • pdf2image + Pillow → PNG pages    (vision fallback)                │
│  • python-docx → text for DOCX                                        │
│  Output: PreprocessedDocument { text, images_b64[], page_count }      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 2 — EXTRACTOR AGENT  (mode: llm, model: gpt-4o vision)          │
│  agents/extractor.py                                                  │
│  • Sends text + base64 images to gpt-4o                               │
│  • Forces tool call: extract_trade_document                           │
│  • Returns ExtractorOutput: {doc_type, fields{value, confidence,      │
│    source_snippet}, notes}                                            │
│  • Stored in DB: extractions table (tool_content + tool_output)       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 3 — VALIDATOR AGENT  (mode: llm, model: gpt-4o)                 │
│  agents/validator.py                                                  │
│  • Receives ExtractorOutput + active rule book rules                  │
│  • Forces tool call: submit_validation                                │
│  • Post-processing: confidence floor enforced in Python (not LLM)    │
│  • Returns ValidatorOutput: {overall_status, results{}, summary}     │
│  • Stored in DB: validations table                                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 4 — ROUTER / DECISION AGENT  (mode: llm, model: gpt-4o)         │
│  agents/router.py                                                     │
│  • Receives ValidatorOutput                                           │
│  • Forces tool call: submit_decision                                  │
│  • Post-processing: outcome invariants enforced in Python (not LLM)  │
│  • Returns RouterOutput: {outcome, reasoning, discrepancies[]}        │
│  • Stored in DB: decisions table                                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STORAGE + SSE                                                        │
│  • Every step → pipeline_runs row in DB (audit trail)                │
│  • Every step → event published to in-memory SessionBus              │
│  • Frontend EventSource GET /api/documents/{id}/timeline             │
│    receives live step_started / step_completed / session_completed   │
└──────────────────────────────────────────────────────────────────────┘
```

### Agent Communication (Structured Handoff)

Agents communicate via **structured Python objects** (Pydantic models), not raw strings or shared memory.

```
ExtractorResult.output (ExtractorOutput)
        │
        ▼
ValidatorResult.output (ValidatorOutput)        ← also reads active RuleBook from DB
        │
        ▼
RouterResult.output (RouterOutput)
```

Each agent's output is also serialised and written to the DB before the next agent starts. If the process crashes mid-pipeline, on restart the pipeline state can be recovered from the `pipeline_sessions` and `pipeline_runs` tables.

### State Persistence

| State | Where stored |
|-------|-------------|
| Raw file | Local disk (`public/`) or S3 |
| Document metadata + status | `documents` table |
| Per-step run log | `pipeline_runs` table |
| Extraction result | `extractions.tool_output` (JSONB) |
| Validation result | `validations.tool_output` (JSONB) |
| Decision result | `decisions.tool_output` (JSONB) |
| Token usage | `pipeline_sessions.total_tokens_in/out` |
| Live events | In-memory `SessionBus` (ephemeral, SSE only) |

---

## Agent Design

### Why Three Agents and Not One?

A single giant prompt collapses three distinct failure modes into one undifferentiated blob:
- **Extraction failures** (the doc is blurry, the field is absent) cannot be distinguished from **validation failures** (the field is present but wrong) in a single output.
- Separation means each agent can be **retried, swapped, or evaluated independently**. You can replace the extractor model without touching the validator logic.
- Each agent has a **single, testable output contract**. The validator's confidence floor is enforced *in Python*, not by hoping the LLM respects it. That deterministic layer is only possible because the extractor and validator are separate.
- **Cost control**: cheapest capable model per step. Parsing is free. Extraction needs vision. Validation and routing are text-only and can use a cheaper model when needed.

### 1. Extractor Agent

**File:** [server/app/agents/extractor.py](server/app/agents/extractor.py)

**Responsibility:** Vision-based field extraction from any trade document format.

**Model:** `gpt-4o` (vision required — must see stamps, logos, handwriting)

**Tool:** `extract_trade_document`

**Input to LLM:**
```
System: extraction instructions + canonical field list + "return null for absent fields"
User:   [text preamble] + [up to 4 base64 PNG pages]
```

**Output (ExtractorOutput):**
```json
{
  "doc_type": "bill_of_lading | commercial_invoice | packing_list | certificate_of_origin | unknown",
  "doc_type_confidence": 0.0–1.0,
  "fields": {
    "consignee_name":      { "value": "ACME CORP LTD", "confidence": 0.97, "source_snippet": "Consignee: ACME CORP LTD" },
    "hs_code":             { "value": "8471.30",        "confidence": 0.91, "source_snippet": "HS: 8471.30" },
    "port_of_loading":     { "value": "SHANGHAI",       "confidence": 0.99, "source_snippet": "Port of Loading: SHANGHAI" },
    "port_of_discharge":   { "value": "FELIXSTOWE",     "confidence": 0.98, "source_snippet": "Port of Discharge: FELIXSTOWE" },
    "incoterms":           { "value": "FOB",            "confidence": 0.95, "source_snippet": "INCOTERMS: FOB" },
    "description_of_goods":{ "value": "LAPTOPS",        "confidence": 0.88, "source_snippet": "Description: LAPTOPS" },
    "gross_weight":        { "value": "450 KG",         "confidence": 0.93, "source_snippet": "Gross Weight: 450 KG" },
    "invoice_number":      { "value": "INV-2024-0042",  "confidence": 0.99, "source_snippet": "Invoice No: INV-2024-0042" }
  },
  "notes": null
}
```

**Absent field representation:** `{ "value": null, "confidence": 0.0, "source_snippet": null }` — never hallucinated.

**Post-processing (Python):** `_ensure_all_required_fields` guarantees all 8 canonical fields exist in the output dict, inserting null stubs for any the LLM omitted.

---

### 2. Validator Agent

**File:** [server/app/agents/validator.py](server/app/agents/validator.py)

**Responsibility:** Field-by-field compliance check against the active customer rule book.

**Model:** `gpt-4o` (text-only; vision not required)

**Tool:** `submit_validation`

**Input to LLM:**
```
System: validation instructions + confidence floor explanation
User:   rules_json (list of RuleSpec) + extraction_json (ExtractorOutput) + low_confidence_threshold
```

**Rule types supported:**

| `rule_type` | `spec` shape | Example |
|-------------|-------------|---------|
| `equals` | `{ "value": "ACME CORP" }` | Consignee must be exact match |
| `regex` | `{ "pattern": "^[0-9]{6,10}$" }` | HS code format validation |
| `one_of` | `{ "values": ["FOB", "CIF", "EXW"] }` | Incoterms whitelist |
| `required` | `{}` | Field must be present and non-null |
| `range` | `{ "min": 0, "max": 100000 }` | Weight range check |
| `custom` | `{ "description": "free text constraint" }` | Passed as-is to the LLM |

**Output (ValidatorOutput):**
```json
{
  "overall_status": "all_match | has_uncertain | has_mismatch",
  "results": {
    "consignee_name": {
      "status": "match | mismatch | uncertain",
      "found": "ACME CORP LTD",
      "expected": "ACME CORP",
      "severity": "critical | major | minor",
      "reasoning": "Consignee name has extra 'LTD' suffix",
      "rule_id": "rule-0"
    }
  },
  "summary": "One consignee mismatch found. All other fields match."
}
```

**Post-processing (Python — not LLM):**

Two deterministic enforcement layers run after the LLM responds:

1. `_enforce_confidence_floor`: Any field where `extraction.confidence < LOW_CONFIDENCE_THRESHOLD (0.70)` is **forced to `uncertain`**, regardless of what the LLM said. This runs in Python with no LLM involvement — the model cannot override it.

2. `_recompute_overall`: `overall_status` is recomputed deterministically from the result set. The LLM's declared overall status is discarded.

---

### 3. Router / Decision Agent

**File:** [server/app/agents/router.py](server/app/agents/router.py)

**Responsibility:** Translate the validation signal into a concrete action with human-readable reasoning.

**Model:** `gpt-4o` (text-only)

**Tool:** `submit_decision`

**Input to LLM:**
```
System: routing rules + outcome definitions
User:   validation_json (ValidatorOutput)
```

**Output (RouterOutput):**
```json
{
  "outcome": "auto_approve | human_review | draft_amendment",
  "reasoning": "Invoice number matches and all fields are confirmed. Auto-approving.",
  "discrepancies": [
    {
      "field": "consignee_name",
      "found": "ACME CORP LTD",
      "expected": "ACME CORP",
      "severity": "critical",
      "reasoning": "Name suffix mismatch may cause customs rejection"
    }
  ]
}
```

**Outcome rules (Python-enforced — the LLM cannot override):**

| Condition | Forced outcome |
|-----------|---------------|
| Any field with `status=mismatch` AND `severity=critical` | `draft_amendment` |
| Any field with `status=mismatch` OR `status=uncertain` | `human_review` |
| All fields `status=match` | `auto_approve` |

If the LLM's stated outcome conflicts with these invariants, `_enforce_outcome_invariants` overrides it and prepends `[override]` to the reasoning string, creating an audit trail of the correction.

**Discrepancy ordering:** Critical → Major → Minor (deterministic sort, not LLM-ordered).

---

### 4. Rule Book Extractor Agent

**File:** [server/app/agents/rule_book_extractor.py](server/app/agents/rule_book_extractor.py)

**Responsibility:** Parse a customer-provided PDF into a structured rule set.

**Model:** `gpt-4o` (vision — rule books are often scanned PDFs)

**Output (RuleBookExtractionOutput):**
```json
{
  "customer_name_in_book": "ACME CORP",
  "rules": [
    { "field_name": "consignee_name", "rule_type": "equals", "spec": { "value": "ACME CORP" }, "severity": "critical" },
    { "field_name": "incoterms",      "rule_type": "one_of", "spec": { "values": ["FOB","CIF"] }, "severity": "major" },
    { "field_name": "hs_code",        "rule_type": "regex",  "spec": { "pattern": "^[0-9]{6,10}$" }, "severity": "critical" }
  ],
  "notes": null
}
```

Rules are stored as `JSONB` in the `documents.extracted_rules` column and activated per-tenant.

---

## Tool Schemas — Input / Output Contracts

All agents use **OpenAI function calling** with `tool_choice="required"` — the model is forced to emit a tool call; free-text responses are rejected. Schemas are auto-generated from Pydantic models via `_schema_helpers.openai_strict_schema()`.

### `extract_trade_document` tool parameters

```json
{
  "type": "object",
  "properties": {
    "doc_type": { "type": "string", "enum": ["bill_of_lading","commercial_invoice","packing_list","certificate_of_origin","unknown"] },
    "doc_type_confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 },
    "fields": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "value":          { "type": ["string", "null"] },
          "confidence":     { "type": "number", "minimum": 0.0, "maximum": 1.0 },
          "source_snippet": { "type": ["string", "null"] }
        },
        "required": ["value", "confidence", "source_snippet"],
        "additionalProperties": false
      }
    },
    "notes": { "type": ["string", "null"] }
  },
  "required": ["doc_type", "doc_type_confidence", "fields", "notes"],
  "additionalProperties": false
}
```

### `submit_validation` tool parameters

```json
{
  "type": "object",
  "properties": {
    "overall_status": { "type": "string", "enum": ["all_match","has_uncertain","has_mismatch"] },
    "results": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "status":    { "type": "string", "enum": ["match","mismatch","uncertain"] },
          "found":     { "type": ["string", "null"] },
          "expected":  { "type": ["string", "null"] },
          "severity":  { "type": "string", "enum": ["critical","major","minor"] },
          "reasoning": { "type": "string" },
          "rule_id":   { "type": ["string", "null"] }
        },
        "required": ["status","found","expected","severity","reasoning","rule_id"],
        "additionalProperties": false
      }
    },
    "summary": { "type": "string" }
  },
  "required": ["overall_status","results","summary"],
  "additionalProperties": false
}
```

### `submit_decision` tool parameters

```json
{
  "type": "object",
  "properties": {
    "outcome":   { "type": "string", "enum": ["auto_approve","human_review","draft_amendment"] },
    "reasoning": { "type": "string" },
    "discrepancies": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "field":     { "type": "string" },
          "found":     { "type": ["string","null"] },
          "expected":  { "type": ["string","null"] },
          "severity":  { "type": "string", "enum": ["critical","major","minor"] },
          "reasoning": { "type": "string" }
        },
        "required": ["field","found","expected","severity","reasoning"],
        "additionalProperties": false
      }
    }
  },
  "required": ["outcome","reasoning","discrepancies"],
  "additionalProperties": false
}
```

---

## API Reference

All endpoints are prefixed `/api`. Authentication is a JWT cookie set by `/api/auth/session`.

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/auth/tenants` | None | List available tenants |
| `POST` | `/api/auth/session` | None | Sign in (body: `{ tenant_slug, role }`) |
| `POST` | `/api/auth/signout` | Any | Clear session cookie |
| `GET` | `/api/auth/me` | Any | Current session info |

### Documents

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/documents/upload` | Any | Upload a trade document; kicks off pipeline async. Returns `{ document_id, session_id }` |
| `GET` | `/api/documents` | Any | Paginated document list with status + outcome |
| `GET` | `/api/documents/{id}` | Any | Full document detail: extraction, validation, decision |
| `GET` | `/api/documents/{id}/timeline` | Any | **SSE stream** — live pipeline events. Events: `session_started`, `step_started`, `step_completed`, `session_completed` |

### Rule Books

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/rule-books/upload` | Admin | Upload a customer rule book PDF; extracts rules and activates |
| `GET` | `/api/rule-books` | Admin | List all rule books for tenant |

### Files

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/files/{storage_key}` | Any | Download an uploaded file |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/health` | None | Liveness check |

---

## Database Schema

```
tenants
  id UUID PK
  name TEXT
  slug TEXT UNIQUE
  created_at TIMESTAMPTZ

documents
  id UUID PK
  tenant_id UUID FK → tenants
  session_id UUID
  type TEXT  ('document' | 'rule_book')
  storage_key TEXT
  original_name TEXT
  mime_type TEXT
  size_bytes BIGINT
  doc_type TEXT          -- set after extraction
  status TEXT            -- uploaded → extracting → validating → deciding → completed | failed
  is_active BOOLEAN      -- for rule books: is this the active rule book for the tenant?
  extracted_rules JSONB  -- populated for rule_book type
  created_at, updated_at TIMESTAMPTZ

  INDEX: (tenant_id, status), (tenant_id, created_at DESC), (session_id)
  UNIQUE INDEX: one active rule_book per tenant WHERE type='rule_book' AND is_active=TRUE

pipeline_sessions
  id UUID PK
  tenant_id UUID FK
  document_id UUID FK
  type TEXT              -- 'document' | 'rule_book'
  pipeline_status TEXT   -- pending | success | fail
  started_at, completed_at TIMESTAMPTZ
  total_tokens_in INTEGER
  total_tokens_out INTEGER
  error_message TEXT

pipeline_runs                -- per-step audit log, one row per attempt
  id UUID PK
  session_id UUID FK
  document_id UUID FK
  step_type TEXT             -- parsing | extraction | validation | decision
  mode TEXT                  -- manual | llm
  status TEXT                -- pending | success | fail
  response JSONB             -- step-specific payload
  total_tokens_in INTEGER
  total_tokens_out INTEGER
  started_at, completed_at TIMESTAMPTZ

extractions
  id UUID PK
  document_id UUID FK
  session_id UUID FK
  pipeline_run_id UUID FK
  tool_content JSONB         -- raw OpenAI tool call arguments
  tool_output JSONB          -- post-processed ExtractorOutput
  created_at TIMESTAMPTZ

validations  (same shape as extractions)
decisions    (same shape as extractions)
```

---

## Storage Layer

The storage layer is abstracted behind a protocol with four methods:

```python
async def put(key: str, data: bytes, content_type: str) -> StoredObject
async def get(key: str) -> bytes
async def delete(key: str) -> None
async def exists(key: str) -> bool
```

**Key convention:**
- Trade documents: `documents/{tenant_id}/{document_id}{ext}`
- Rule books: `rule_books/{tenant_id}/{document_id}{ext}`

| `STORAGE_BACKEND` | Implementation | Use case |
|-------------------|---------------|---------|
| `local` (default) | Files in `public/` dir, served via `/api/files/` | Development, local demo |
| `s3` | AWS S3 via `aioboto3` | Production deployments |

Switch backends by setting `STORAGE_BACKEND=s3` and providing S3 credentials in `.env`.

---

## Frontend Pages

| Page | Route | Role | Description |
|------|-------|------|-------------|
| Sign In | `/` | Public | Tenant picker + role selector (admin/default) |
| Documents | `/documents` | Any | Table of all processed documents with live status + outcome badges |
| Upload | `/upload` | Any | Drag-drop upload with progress bar and live SSE timeline |
| Document Detail | `/documents/:id` | Any | Full pipeline result: extracted fields, per-field confidence, validation table, routing decision + reasoning |
| Rule Books | `/rule-books` | Admin | Upload and list active customer rule books |

**Live pipeline view:** The Upload page and Document Detail page both subscribe to `GET /api/documents/{id}/timeline` via the browser `EventSource` API. Each pipeline step (`parsing → extraction → validation → decision`) emits events that update the UI in real time.

---

## Configuration Reference

Copy `.env.example` to `server/.env` and fill in the required values.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL DSN, e.g. `postgresql://user:pass@localhost:5432/nova` |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `ENV` | No | `dev` | `dev` / `prod` / `test` |
| `RUN_ENV` | No | `local` | `local` uses local storage; `cloud` uses S3 |
| `LOG_LEVEL` | No | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `OPENAI_MODEL_VISION` | No | `gpt-4o` | Model for Extractor + Rule Book agents (vision required) |
| `OPENAI_MODEL_REASONING` | No | `gpt-4o` | Model for Validator + Router agents |
| `OPENAI_MODEL_CHEAP` | No | `gpt-4o-mini` | Reserved for future lightweight tasks |
| `STORAGE_BACKEND` | No | `local` | `local` or `s3` |
| `LOCAL_STORAGE_ROOT` | No | `public` | Root dir for local file storage |
| `S3_BUCKET` | If s3 | — | S3 bucket name |
| `S3_REGION` | If s3 | — | AWS region |
| `AWS_ACCESS_KEY_ID` | If s3 | — | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | If s3 | — | AWS credentials |
| `COST_CAP_USD_PER_RUN` | No | `0.50` | Maximum spend per pipeline run; run aborts if exceeded |
| `MAX_RETRIES_PER_NODE` | No | `2` | Tenacity retry limit for OpenAI transient failures |
| `LOW_CONFIDENCE_THRESHOLD` | No | `0.70` | Fields below this confidence are forced to `uncertain` |
| `MAX_UPLOAD_BYTES` | No | `26214400` (25 MB) | Upload size limit |
| `ALLOWED_ORIGINS` | No | `http://localhost:5173` | CORS allowed origins |
| `JWT_SECRET` | No | `dev-secret-change-me` | **Change in production** |
| `JWT_ALGORITHM` | No | `HS256` | JWT signing algorithm |
| `SESSION_TTL_SECONDS` | No | `604800` (7 days) | Session cookie lifetime |

---

## Engineering Trade-offs

### 1. Custom sequential pipeline vs. LangGraph

LangGraph is installed but used only for checkpoint storage (Postgres adapter). The pipeline itself is a plain Python `async` function in `services/pipeline.py`.

**Why:** The pipeline has no branching: parsing → extraction → validation → decision, always in that order. LangGraph's graph + node model adds runtime overhead and a non-trivial debugging surface for what is fundamentally a linear chain. The sequential approach keeps failure handling explicit: each step has a try/except, writes its own DB row, and short-circuits cleanly on failure. LangGraph would be the right call once the pipeline needs conditional re-extraction, parallel sub-agent fanout, or human-in-the-loop mid-pipeline gates.

### 2. Tool-use enforcement for all agent outputs

Every agent output goes through a tool call (`tool_choice="required"`). Free-text LLM responses are never parsed.

**Why:** Tool use guarantees the output matches the declared JSON schema. Without it, the LLM might omit a field, use a different key name, or return prose instead of JSON. Combined with Pydantic's `extra="forbid"`, the schema is a hard contract — invalid responses fail fast rather than silently propagating bad data downstream.

### 3. Deterministic post-processing over LLM-enforced invariants

The confidence floor and outcome invariants are enforced in Python *after* the LLM responds, not by asking the LLM to enforce them in its prompt.

**Why:** LLMs are probabilistic. A prompt instruction like "if confidence is below 0.7, set status to uncertain" will be followed 99% of the time but not 100%. The Python post-processing layers (`_enforce_confidence_floor`, `_enforce_outcome_invariants`) are unconditional — they run on every response. This separation of concerns means: the LLM contributes reasoning; Python enforces safety invariants. Both are logged, creating an audit trail when the override fires.

### 4. Per-step DB writes vs. in-memory handoff

Each agent output is written to the DB before the next step starts, rather than being passed in-memory through the whole pipeline.

**Why:** If the process crashes after step 2 (extraction succeeded, validation hasn't run), the extraction result is not lost. The DB row acts as an implicit checkpoint. This costs one extra DB round-trip per step but makes the pipeline resumable and creates an audit trail at no extra design cost.

### 5. JSONB for agent outputs vs. normalised columns

Agent outputs (`tool_output`) are stored as `JSONB` rather than having every field as a separate column.

**Why:** The field set will evolve. New canonical fields can be added to the extractor schema without a migration. The JSONB column is still queryable (`->>` operators, GIN indexes). Trade-off: no foreign-key–style integrity on field names; the Pydantic schemas are the contract instead.

### 6. Multi-tenant at the DB row level vs. separate schemas/databases

Every query filters on `tenant_id`. There are no per-tenant schemas or databases.

**Why:** For a POC with a small number of tenants, row-level isolation is operationally simpler. The unique index on `(tenant_id, customer_id) WHERE type='rule_book' AND is_active=TRUE` enforces the "one active rule book per tenant" invariant at the database level.

### 7. In-memory SSE event bus vs. Redis pub/sub

The `SessionBus` in `services/events.py` is a dict of asyncio queues keyed by session ID.

**Why:** For a single-process deployment (Uvicorn with one worker), this is sufficient and eliminates an external dependency. Trade-off: events are lost on restart and the approach does not scale horizontally. The upgrade path is clear: replace `SessionBus` with a Redis pub/sub adapter behind the same interface.

---

## Failure Handling & Safety Guarantees

### Hallucination prevention

- **Absent fields must be null.** The extractor prompt and schema both require `value: null` for missing fields. The `_ensure_all_required_fields` post-processor adds null stubs for any field the LLM omitted entirely.
- **Source snippets are required.** Every extracted field must include a `source_snippet` pointing to where in the document the value was found. A value without a source is a signal of hallucination.
- **Confidence floor.** Any field with `confidence < 0.70` is forced to `uncertain` in Python — the validator can never mark it as a match regardless of the rule check result.

### Outcome enforcement

- Router outcome is determined deterministically from validator signals, not solely from LLM reasoning.
- If the LLM's stated outcome conflicts with the validator signal, Python overrides it and logs the correction with `[override]` prefix.
- `auto_approve` is only possible when **all fields** have `status=match`. One uncertain or mismatched field blocks it.

### Cost and loop control

- `COST_CAP_USD_PER_RUN` (default $0.50) — pipeline aborts if accumulated token cost exceeds the cap.
- `MAX_RETRIES_PER_NODE` (default 2) — Tenacity retry limit; prevents infinite retry loops on transient OpenAI errors.
- `max_tokens` is set per agent call (1500 for extractor, 2000 for validator, 1200 for router) — prevents runaway token consumption on large documents.
- Temperature is `0.0` on all agent calls — deterministic outputs; reduces variance between runs on the same document.

### Pipeline failure modes

| Failure | Behaviour |
|---------|-----------|
| No active rule book | Pipeline aborts immediately with `no_active_rule_book` error before any LLM call |
| Parsing fails | Step marked `fail`, document status → `failed`, session closed |
| LLM call fails (network/rate limit) | Tenacity retries up to `MAX_RETRIES_PER_NODE` times; on exhaustion, step marked `fail`, pipeline halts |
| LLM returns invalid schema | Pydantic validation fails, step marked `fail`, pipeline halts — bad output never reaches next step |
| LLM violates outcome invariant | Python enforces correct outcome; pipeline continues with corrected output |
| Crash mid-pipeline | All completed steps are already in DB; session row shows last known status |

---

## Observability

### Structured logging

Every log line is JSON. The `set_correlation_id` call at pipeline start tags every subsequent log line in that async context with `sess-{session_id_prefix}`. This means a single `grep` on the session ID gives the complete execution trace.

```
{"timestamp": "...", "level": "INFO", "correlation_id": "sess-a3f2b1c9d0e1", "event": "extractor_done",
 "doc_type": "commercial_invoice", "doc_type_confidence": 0.97, "fields_present": 8, "fields_total": 8}
```

### SSE timeline (live)

Clients subscribe to `GET /api/documents/{id}/timeline` and receive a stream:

```
event: step_started
data: {"step_type": "extraction", "mode": "llm", "run_id": "..."}

event: step_completed
data: {"step_type": "extraction", "status": "success", "tokens_in": 850, "tokens_out": 312}

event: session_completed
data: {"status": "success", "total_tokens_in": 2100, "total_tokens_out": 780}
```

### Per-run token tracking

Every pipeline run records `total_tokens_in` and `total_tokens_out`. The session-level rollup is in `pipeline_sessions`. This is the data source for cost dashboards.

### Production dashboard (what to build next)

| Metric | Source |
|--------|--------|
| Documents processed / hour | `pipeline_sessions.started_at` |
| Pipeline success rate | `pipeline_sessions.pipeline_status` |
| Outcome distribution (auto-approve / human-review / amendment) | `decisions.tool_output ->> 'outcome'` |
| Avg tokens per document | `pipeline_sessions.total_tokens_in + total_tokens_out` |
| P95 pipeline latency | `pipeline_sessions.completed_at - started_at` |
| Confidence distribution per field | `extractions.tool_output -> 'fields' -> 'hs_code' ->> 'confidence'` |
| Override rate (LLM overridden by Python) | grep `[override]` in `decisions.tool_output ->> 'reasoning'` |

---

## Cost Model

Back-of-envelope per document (gpt-4o pricing as of 2024):

| Step | Tokens in | Tokens out | Cost (approx.) |
|------|-----------|-----------|----------------|
| Extraction (vision) | ~1,200 | ~400 | ~$0.016 |
| Validation (text) | ~800 | ~600 | ~$0.014 |
| Decision (text) | ~600 | ~300 | ~$0.009 |
| **Total per document** | **~2,600** | **~1,300** | **~$0.04** |

Cost blows up when:
- Documents exceed 4 pages (more images = more tokens)
- Rule books are large (more rules = longer validation prompt)
- Retries fire (doubles or triples cost for that step)

Cost controls: `COST_CAP_USD_PER_RUN=0.50`, `max_tokens` per call, `MAX_RETRIES_PER_NODE=2`.

---

## Sample Queries

Once documents are processed, you can query the PostgreSQL database directly. A natural-language query layer is available via the `/api/documents` list endpoint.

**How many documents were processed this week?**
```sql
SELECT COUNT(*) FROM pipeline_sessions
WHERE pipeline_status = 'success'
  AND started_at >= NOW() - INTERVAL '7 days';
```

**How many documents were flagged for human review?**
```sql
SELECT COUNT(*) FROM decisions d
JOIN documents doc ON doc.id = d.document_id
WHERE doc.status = 'completed'
  AND d.tool_output ->> 'outcome' = 'human_review';
```

**What is the outcome distribution this week?**
```sql
SELECT
  d.tool_output ->> 'outcome' AS outcome,
  COUNT(*) AS count
FROM decisions d
JOIN pipeline_sessions ps ON ps.id = d.session_id
WHERE ps.started_at >= NOW() - INTERVAL '7 days'
GROUP BY outcome;
```

**Which documents have a low-confidence HS code?**
```sql
SELECT doc.original_name, doc.id,
       (e.tool_output -> 'fields' -> 'hs_code' ->> 'confidence')::float AS hs_confidence
FROM extractions e
JOIN documents doc ON doc.id = e.document_id
WHERE (e.tool_output -> 'fields' -> 'hs_code' ->> 'confidence')::float < 0.70
ORDER BY hs_confidence ASC;
```

**Total tokens used and estimated cost this week?**
```sql
SELECT
  SUM(total_tokens_in) AS total_in,
  SUM(total_tokens_out) AS total_out,
  ROUND((SUM(total_tokens_in) * 0.0000025 + SUM(total_tokens_out) * 0.00001)::numeric, 4) AS est_cost_usd
FROM pipeline_sessions
WHERE started_at >= NOW() - INTERVAL '7 days';
```

**All documents that triggered a Python outcome override?**
```sql
SELECT doc.original_name, d.tool_output ->> 'reasoning' AS reasoning
FROM decisions d
JOIN documents doc ON doc.id = d.document_id
WHERE d.tool_output ->> 'reasoning' LIKE '[override]%';
```
