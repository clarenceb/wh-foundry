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

## Project structure

```text
wh-foundry/
├── azure.yaml                      # Azure Developer CLI project config
├── pyproject.toml                  # Python project config and dependencies
├── scrape-config.yaml              # Scraper configuration (URLs, storage, selectors)
├── scrape_pages.py                 # Web scraper script
├── upload_docs.py                  # Blob storage upload script
├── infra/
│   ├── main.bicep                  # Main Bicep template (subscription-scoped)
│   ├── main.parameters.json        # Parameter file for azd
│   ├── abbreviations.json          # Resource name abbreviations
│   ├── modules/
│   │   ├── storage.bicep            # Storage account + container
│   │   ├── search.bicep             # Azure AI Search service
│   │   ├── ai-services.bicep        # AI Services account + Foundry project
│   │   ├── model-deployments.bicep  # OpenAI model deployments
│   │   ├── storage-role.bicep       # Storage blob role assignments
│   │   └── ai-services-role.bicep   # AI Services role assignments
│   ├── search-config/
│   │   ├── index.json               # Search index definition
│   │   ├── datasource.json          # Blob data source definition
│   │   ├── skillset.json            # Chunking + embedding skillset
│   │   └── indexer.json             # Indexer definition
│   └── scripts/
│       └── setup-search.sh          # Post-provision: deploy search configs
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

The upload scripts use `DefaultAzureCredential`, which picks up your Azure CLI session. Your account needs **Storage Blob Data Contributor** on the `whkbdocs` storage account.
