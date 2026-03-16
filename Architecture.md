# Architecture

## Overview

The WH Foundry project is a demo platform that showcases **Microsoft Foundry IQ** with a knowledge base powered by **Azure AI Search**. It scrapes the Western Health website, indexes the content, and serves it through a Foundry agent that users interact with via a React web app.

## High-Level Architecture

![Architecture Diagram](./Architecture.png)

### Data Ingestion Pipeline

1. **Web Scraper** (`scrape_pages.py`) — Uses Playwright to fetch pages from the Western Health website, expands tabs/accordions, strips boilerplate, and converts to clean Markdown
2. **Azure Blob Storage** (`whkbdocs/wh-kb-docs`) — Stores the Markdown files as the knowledge base source
3. **Azure AI Search Indexer** — Runs daily, cracks documents, and feeds them through the skillset:
   - **SplitSkill** — Chunks documents into 2000-character pages with 200-character overlap
   - **AzureOpenAIEmbeddingSkill** — Generates 1536-dimensional vectors using `text-embedding-3-small`
4. **Azure AI Search Index** (`wh-kb-docs-index`) — Stores chunks with vector embeddings, enabling hybrid (keyword + vector) search with semantic ranking

### Agent & Chat

5. **Microsoft Foundry Agent** (`wh-patient-helper`) — A prompt agent backed by the knowledge base, with memory enabled for personalization
6. **Foundry Memory Store** — Persists user preferences and context across sessions (scoped per user via `{{$userId}}`)
7. **FastAPI Backend** (`web/api/server.py`) — Bridges the React frontend to Foundry:
   - Creates conversations, streams agent responses via SSE
   - Generates time-limited SAS URLs for source document viewing
   - Lists and clears agent memories
8. **React Frontend** (`web/src/`) — Three modes:
   - `/` — Full chat app with sidebar, chat history, memory panel
   - `/widget` — Western Health landing page with floating chat bubble
   - `/embed` — Standalone embeddable chat for iframe integration

## Azure Services

| Service | Purpose | SKU |
| --- | --- | --- |
| **Azure Blob Storage** | Knowledge base document store | Standard_ZRS, Hot |
| **Azure AI Search** | Vector + semantic search over documents | Basic |
| **Azure AI Services (Foundry)** | LLM inference, agent hosting, memory | S0 |
| **Foundry Project** | Agent workspace with connected resources | — |
| **Application Insights** | Trace collection and observability | Workspace-based |
| **Log Analytics** | Telemetry storage for Application Insights | PerGB2018 |

### Model Deployments

| Deployment | Model | SKU | Purpose |
| --- | --- | --- | --- |
| `text-embedding-3-small` | text-embedding-3-small | Standard (120 TPM) | Document + query embeddings |
| `gpt-4.1` | gpt-4.1 | GlobalStandard (50 TPM) | Agent reasoning |
| `gpt-5.1` | gpt-5.1 | GlobalStandard (120 TPM) | Agent reasoning |
| `gpt-5.2` | gpt-5.2 | GlobalStandard (150 TPM) | Agent reasoning (primary) |

### Role Assignments (RBAC)

| From | To | Role | Why |
| --- | --- | --- | --- |
| AI Search (managed identity) | Storage Account | Storage Blob Data Reader | Indexer reads markdown blobs |
| AI Search (managed identity) | AI Services | Cognitive Services User | Skillset calls embedding model |
| Current User | Storage Account | Storage Blob Data Contributor | Upload/manage documents |
| Current User | Storage Account | Storage Blob Delegator | Generate user delegation SAS tokens for source viewing |
| Current User | AI Services | Cognitive Services User | Call models, manage agents |
| AI Services (managed identity) | AI Services (self) | Cognitive Services User | Memory store calls embedding model for vectorizing memories |
| Foundry Project (managed identity) | AI Services | Azure AI User | Memory store authenticates to call chat + embedding models |

## Tracing / Observability

The application uses **OpenTelemetry** with the **Azure Monitor exporter** to send traces to **Application Insights**, which are then surfaced in the **Foundry portal → Observability → Traces**.

### Tracing flow

1. A shared tracing module ([tracing.py](tracing.py)) configures the OpenTelemetry `TracerProvider` at startup
2. If `APPLICATION_INSIGHTS_CONNECTION_STRING` is set, traces are exported to Azure Monitor; otherwise they print to the console
3. `azure-core-tracing-opentelemetry` is enabled so all Azure SDK calls (Foundry, Storage) are automatically instrumented
4. FastAPI is auto-instrumented via `opentelemetry-instrumentation-fastapi` — every HTTP request gets a span

### Instrumented spans

| Span | Location | What it captures |
| --- | --- | --- |
| `create_chat_session` | `POST /api/chats` | New Foundry conversation creation with IDs |
| `agent_chat_turn` | `POST /api/chats/{id}/messages` | Full chat turn: user message → agent response |
| `foundry_agent_call` | nested in above | The actual Foundry agent API call |
| `extract_citations` | nested in above | Citation extraction with count |
| `extract_memories` | nested in above | Memory lookup with count and source |
| `agent_chat_turn_sync` | `POST .../messages/sync` | Same as above for non-streaming path |
| `list_memories` | `GET /api/memories` | Memory store queries |
| `create_conversation` | CLI `chat.py` | CLI conversation creation |
| `agent_chat_turn` | CLI `chat.py` | Each CLI chat turn |

### Infrastructure

- **Log Analytics workspace** — Stores raw telemetry data (90-day retention)
- **Application Insights** — Workspace-based, connected to Log Analytics, provides trace visualization
- Both are provisioned via Bicep ([infra/modules/app-insights.bicep](infra/modules/app-insights.bicep))

### Packages

| Package | Purpose |
| --- | --- |
| `opentelemetry-sdk` | Core OpenTelemetry tracing SDK |
| `azure-monitor-opentelemetry-exporter` | Exports spans to Application Insights |
| `azure-core-tracing-opentelemetry` | Auto-instruments Azure SDK calls |
| `opentelemetry-instrumentation-fastapi` | Auto-instruments FastAPI HTTP requests |

## Memory Store

The Foundry agent uses the **Memory Store** (preview) to persist user preferences, context, and demographics across chat sessions.

### How it works

1. The agent has a `memory_search_preview` tool attached, configured with a **memory store name** and **scope**
2. **Scope** determines memory isolation — set to `{{$userId}}` which resolves to `{tenantId}_{objectId}` from the authentication token, giving each user their own private memory partition
3. During a conversation, the agent automatically extracts memorable information (preferences, location, formatting style) from the chat
4. Memory updates are **debounced** by `update_delay` (set to 10 seconds for this demo; use 300 seconds / 5 minutes in production)
5. At the start of each new conversation, **static memories** (user profile) are injected so the agent has immediate context
6. Per-turn, **contextual memories** are retrieved via semantic search to inform each response

### Memory types

- **User profile** — Long-term facts about the user (e.g. "Lives in Footscray", "Prefers concise answers")
- **Chat summary** — Compressed summaries of past conversations for continuity

### Management

- **List memories** — `GET /api/memories` calls `search_memories()` with scope only (no items) to retrieve static memories
- **Clear scope** — `DELETE /api/memories` calls `delete_scope()` to remove all memories for the current user
- Individual memory deletion is not supported by the Foundry API

## Source Document Viewing (SAS URLs)

When the agent cites a knowledge base document, the citation links point to Azure Blob Storage. Since the storage account has public access disabled, the backend generates **user delegation SAS tokens** with a 15-minute expiry.

This requires:
- **Storage Blob Data Contributor** — to read blobs
- **Storage Blob Delegator** — to call `get_user_delegation_key()` and sign SAS tokens without storage account keys

## Search Index Configuration

- **Algorithm**: HNSW (cosine metric, m=4, efConstruction=400, efSearch=500)
- **Compression**: Scalar quantization (int8) with rescoring enabled (4x oversampling)
- **Vectorizer**: Integrated `text-embedding-3-small` for query-time vectorization
- **Semantic**: BM25 similarity with semantic reranking on the `snippet` field
- **Projection mode**: `skipIndexingParentDocuments` — only chunk-level documents are indexed

## Web App Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn, SSE |
| Frontend | React, TypeScript, Vite |
| State | Zustand |
| Styling | CSS Modules (WH teal palette) |
| Auth | DefaultAzureCredential (Azure CLI) |
| Routing | React Router (`/`, `/widget`, `/embed`) |

## Resources

- [Microsoft Foundry documentation](https://learn.microsoft.com/azure/foundry/)
- [Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/)
- [Memory in Foundry Agent Service (preview)](https://learn.microsoft.com/azure/foundry/agents/how-to/memory-usage)
- [Azure AI Search — vector search](https://learn.microsoft.com/azure/search/vector-search-overview)
- [Azure AI Search — integrated vectorization](https://learn.microsoft.com/azure/search/vector-search-integrated-vectorization)
- [Azure AI Search — semantic ranking](https://learn.microsoft.com/azure/search/semantic-search-overview)
- [Connect to Azure Storage using a managed identity](https://learn.microsoft.com/azure/search/search-howto-managed-identities-storage)
- [Azure OpenAI Embedding Skill](https://learn.microsoft.com/azure/search/cognitive-search-skill-azure-openai-embedding)
- [User delegation SAS tokens](https://learn.microsoft.com/azure/storage/blobs/storage-blob-user-delegation-sas-create-python)
- [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/)
