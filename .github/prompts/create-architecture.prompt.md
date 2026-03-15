# Create Architecture Document & Diagram

Create or update `Architecture.md` and generate an Azure architecture diagram (`architecture.png`) for this project.

## Steps

1. **Gather context** — Read the Bicep templates in `infra/`, the FastAPI backend in `web/api/server.py`, the React frontend structure in `web/src/`, and the scraper scripts (`scrape_pages.py`, `upload_docs.py`).

2. **Write `Architecture.md`** covering:
   - **Overview** — What the project does (Foundry IQ demo with knowledge base)
   - **High-Level Architecture** — Include a link to the `Architecture.png` diagram in the repo
   - **Data ingestion pipeline** — Web scraping (Playwright), Markdown conversion, blob upload, AI Search indexer, skillset (chunking + embedding), index configuration (HNSW, scalar quantization, semantic ranking)
   - **Agent & chat** — Foundry agent with knowledge base grounding, memory store (scope, debounce, memory types), conversations API
   - **Web app** — FastAPI backend (SSE streaming, SAS URL proxy, memory endpoints), React frontend (Zustand stores, three route modes: full app, widget, embed)
   - **Azure services table** — Storage, AI Search, AI Services/Foundry, with SKUs
   - **Model deployments table** — Embedding and chat models with SKU and capacity
   - **RBAC table** — All role assignments between services (include Storage Blob Delegator for SAS)
   - **Search index config** — Algorithm, compression, vectorizer, semantic config, projection mode
   - **Memory store** — How it works, scope isolation, debounce, memory types, management API
   - **Source document viewing** — SAS URL generation, required roles
   - **Web app stack table** — Backend, frontend, state, styling, auth, routing
   - **Resources** — Links to relevant Microsoft Learn docs

3. **Generate the architecture diagram** using the Azure Diagrams Skill based on a summary of the `Architecture.md` file. Include key components like the web scraper, blob storage, AI Search indexer, Foundry agent, FastAPI backend, and React frontend. Use Azure icons where applicable.  Store the output as `Architecture.png` in the repo.

