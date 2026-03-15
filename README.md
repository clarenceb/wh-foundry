# wh-foundry

Western Health knowledge base scraper and Azure AI Search tooling for Microsoft Foundry IQ demos.

Scrapes web pages from the [Western Health website](https://westernhealth.org.au), converts them to clean Markdown, uploads to Azure Blob Storage, and indexes them via Azure AI Search for use as a Foundry IQ knowledge base.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) for infrastructure provisioning
- Azure CLI (`az`) logged in with access to your Azure subscription
- Chromium (installed automatically by Playwright)

### Azure resources

| Resource | Name |
|---|---|
| Resource Group | `foundry-demos` |
| Storage Account | `whkbdocs` |
| Blob Container | `wh-kb-docs` |
| Azure AI Search | `mydemossrch11617` |
| Microsoft Foundry | `foundrydemoscbx` |
| Foundry Project | `mydemos` |

## Setup

```bash
# Create virtual environment
uv venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -e .

# Install Chromium for Playwright
playwright install chromium

# Install system dependencies required by Chromium (Linux only)
playwright install-deps

# Install frontend dependencies
cd web && npm install && cd ..
```

### Configure `.env`

Copy the sample and fill in your values:

```bash
cp .env.sample .env
```

Edit `.env` with your Foundry project details:

```dotenv
# Foundry project endpoint
# Format: https://<resource_name>.services.ai.azure.com/api/projects/<project_name>
PROJECT_ENDPOINT=https://foundrydemoscbx.services.ai.azure.com/api/projects/mydemos

# Name of the agent created in Foundry
AGENT_NAME=wh-patient-helper

# Memory store config
MEMORY_STORE_NAME=MemoryStore-xxxxxxxxxxxxxx
MEMORY_SCOPE={tenantId}_{objectId}

# Storage account (for SAS-signed source document URLs)
STORAGE_ACCOUNT_NAME=whkbdocs
```

#### Setting `MEMORY_SCOPE`

The agent's memory tool uses `{{$userId}}` as the scope, which resolves to `{tenantId}_{objectId}` from the request auth token. The backend needs the same scope to list and clear memories.

To get your scope value:

```bash
# Get your tenant ID
TENANT_ID=$(az account show --query tenantId -o tsv)

# Get your object ID
OBJECT_ID=$(az ad signed-in-user show --query id -o tsv)

# Combine them
echo "${TENANT_ID}_${OBJECT_ID}"
```

Set the output as `MEMORY_SCOPE` in `.env`:

```dotenv
MEMORY_SCOPE=10000072-868a-4a35-a837-af0477f1d90c_47a15bf4-d265-44e2-bb1b-6e58670304a3
```

#### Setting `MEMORY_STORE_NAME`

Find your memory store name in the Foundry portal under your agent's memory tool configuration, or run:

```bash
source .venv/bin/activate
python -c "
import os
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
load_dotenv()
project = AIProjectClient(endpoint=os.environ['PROJECT_ENDPOINT'], credential=DefaultAzureCredential())
for s in project.beta.memory_stores.list():
    print(f'  {s.name} — {s.description}')
"
```

### Setup Foundry agent and memory store

After infrastructure is provisioned and the knowledge base is connected in the Foundry portal, run:

```bash
source .venv/bin/activate
python setup_agent.py
```

This creates (or verifies):
- **Memory store** — configured with chat/embedding models, user profile extraction
- **Agent** (`wh-patient-helper`) — with knowledge base (MCP), memory search, and web search tools

To delete and recreate everything:

```bash
python setup_agent.py --reset
```

### Run the web app

```bash
./start.sh                  # Full chat app at http://localhost:5173/
./start.sh --mode=widget    # WH landing page + chat bubble at /widget
./start.sh --mode=embed     # Embeddable chat at /embed
```

## Azure infrastructure provisioning

All Azure resources can be provisioned from scratch using Azure Developer CLI (`azd`).

```bash
# Initialise the azd environment (first time only)
azd init

# Set the target region
azd env set AZURE_LOCATION australiaeast

# Optionally set your user principal ID for role assignments
azd env set AZURE_PRINCIPAL_ID $(az ad signed-in-user show --query id -o tsv)

# Provision all Azure resources
azd provision
```

This creates:

- **Resource group** with all resources
- **Storage account** with `wh-kb-docs` blob container
- **Azure AI Search** (Basic tier, system-assigned managed identity, semantic search enabled)
- **AI Services account** (S0) with model deployments (text-embedding-3-small, gpt-4.1, gpt-5.1, gpt-5.2)
- **Foundry project** (`mydemos`)
- **Role assignments** (Search → Storage Blob Data Reader, Search → Cognitive Services User, User → Storage Blob Data Contributor)

The `postprovision` hook automatically deploys the AI Search index, datasource, skillset, and indexer via [infra/scripts/setup-search.sh](infra/scripts/setup-search.sh).

To tear down all resources:

```bash
azd down
```

## Usage

### 1. Configure pages to scrape

Edit `scrape-config.yaml` and add URLs under `pages:`:

```yaml
pages:
  - url: https://westernhealth.org.au/patients-and-visitors/patient-transport-services
    name: wh-patients-and-visitors-patient-transport-services
  - url: https://westernhealth.org.au/location/footscray-hospital
    name: wh-location-footscray-hospital
```

The `name` field is optional — if omitted, a filename is derived from the URL path.

### 2. Scrape pages to Markdown

```bash
# Scrape all configured pages (saves .md files to wh-kb-docs-md/)
python scrape_pages.py

# Scrape and immediately upload to Azure Blob Storage
python scrape_pages.py --upload

# Use a custom config file
python scrape_pages.py --config my-config.yaml
```

The scraper will:

- Load each URL with headless Chromium (via Playwright)
- Expand all tabs (e.g. Overview, Emergency, Services on location pages)
- Expand collapsed/accordion sections
- Strip navigation, headers, footers, sidebars, and boilerplate
- Convert the core content to clean Markdown
- Save to the `wh-kb-docs-md/` directory

### 3. Upload Markdown files to Azure Blob Storage

```bash
# Upload .md files (keeps any existing blobs)
python upload_docs.py

# Delete all existing blobs first (e.g. remove old PDFs), then upload
python upload_docs.py --clean

# Preview what would happen without making changes
python upload_docs.py --dry-run
```

Both scripts read storage settings (`account_name`, `container_name`, `output_dir`) from `scrape-config.yaml`.

### 4. Re-index in Azure AI Search

After uploading, trigger the indexer to re-process the new Markdown files:

```bash
# Reset and re-run the indexer
az search indexer reset --name wh-kb-docs-indexer \
  --service-name mydemossrch11617 \
  --resource-group foundry-demos

az search indexer run --name wh-kb-docs-indexer \
  --service-name mydemossrch11617 \
  --resource-group foundry-demos
```

Or reset and run from the Azure portal under **Azure AI Search > Indexers > wh-kb-docs-indexer**.

### 5. Test the knowledge base

Once indexing completes, test queries in the Azure portal:

- **Azure AI Search > Indexes > wh-kb-docs-index > Search explorer**
- **Microsoft Foundry > Project > Knowledge bases > wh-kb-docs**

### 6. Console chat (CLI)

For a quick demo without the web app, use the standalone console chat:

```bash
source .venv/bin/activate
python chat.py
```

This connects directly to the Foundry agent and lets you type questions in the terminal. Type `q`, `quit`, or `bye` to exit.

## Project structure

```text
wh-foundry/
├── azure.yaml                      # Azure Developer CLI project config
├── pyproject.toml                  # Python project config and dependencies
├── .env.sample                     # Environment variable template
├── start.sh                        # Start both API + frontend dev servers
├── chat.py                         # CLI chat demo (standalone)
├── scrape-config.yaml              # Scraper configuration (URLs, storage, selectors)
├── scrape_pages.py                 # Web scraper script
├── upload_docs.py                  # Blob storage upload script
├── web/
│   ├── api/
│   │   └── server.py               # FastAPI backend (SSE streaming, memory, SAS URLs)
│   └── src/
│       ├── api.ts                   # Frontend API client
│       ├── App.tsx                  # React Router (/, /widget, /embed)
│       ├── stores/
│       │   ├── chatStore.ts         # Zustand chat store
│       │   └── memoryStore.ts       # Zustand memory store
│       ├── components/
│       │   ├── ChatPanel.tsx        # Chat UI with streaming + citations
│       │   ├── Sidebar.tsx          # Chat history sidebar
│       │   ├── ChatWidget.tsx       # Floating chat bubble
│       │   ├── MemoryPanel.tsx      # Memory viewer + clear scope
│       │   └── SourceModal.tsx      # SAS-signed document viewer
│       └── pages/
│           ├── FullAppPage.tsx      # / — full chat app
│           ├── WidgetPage.tsx       # /widget — WH landing + chat bubble
│           └── EmbedPage.tsx        # /embed — standalone embeddable chat
├── infra/                           # Bicep templates + azd config
├── wh-kb-docs-md/                   # Scraped Markdown output (local)
├── wh-kb-docs/                      # Original PDF files (reference only)
└── wh-images/                       # Supporting images
```

## Configuration reference

`scrape-config.yaml` supports the following settings:

| Key | Description |
|---|---|
| `storage.account_name` | Azure Storage account name |
| `storage.container_name` | Blob container name |
| `output_dir` | Local directory for scraped Markdown files |
| `strip_selectors` | CSS selectors for elements to remove from pages |
| `content_selectors` | CSS selectors to locate the main content area (tried in order) |
| `pages` | List of pages to scrape, each with `url` and optional `name` |

## Troubleshooting

### Indexer shows "skill input is missing or empty"

This means the blobs contain no extractable text (e.g. image-only PDFs). Replace them with Markdown files using this scraper.

### Very little content extracted

The page may use a different content structure. Inspect the page HTML and adjust `content_selectors` or `strip_selectors` in the config.

### Upload authentication errors

Ensure you are logged in via Azure CLI:

```bash
az login
```

The upload scripts use `DefaultAzureCredential`, which picks up your Azure CLI session. Your account needs **Storage Blob Data Contributor** and **Storage Blob Delegator** on the `whkbdocs` storage account.

## Future enhancements

- **User authentication** — Add Microsoft Entra ID (AAD) login to the web app so each user gets their own memory scope automatically via `{{$userId}}` (tenant ID + object ID from the auth token). Currently the scope is hardcoded in `.env`.
- **Deploy to Azure App Service** — Package the FastAPI backend and React frontend for deployment to Azure App Service (or Container Apps). The `start.sh` script currently runs both locally; a production deployment would use a reverse proxy (e.g. nginx) or serve the Vite build as static files from FastAPI.
- **Persistent chat history** — Chat history is currently in-memory on the backend. Add Cosmos DB or Azure Table Storage for persistence across restarts.
- **Multi-user support** — With AAD login, each user would have isolated conversations and memory scopes.
- **Admin panel** — Add an admin view to manage the knowledge base (trigger re-indexing, view indexer status, upload new documents).
- **Analytics** — Track common questions, response quality, and user satisfaction for continuous improvement.
