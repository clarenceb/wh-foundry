# Web Scraper Generator

Generate a Python web scraper that fetches web pages, expands all dynamic content, strips boilerplate, and converts to clean Markdown for use as a knowledge base in Azure AI Search.

## Requirements

### Core Functionality

1. **Fetch pages using Playwright** (headless Chromium) — handles JavaScript-rendered content
2. **Expand all collapsed/hidden content** before extraction:
   - Click all elements with `aria-expanded="false"`
   - Open all `<details>` elements
   - Expand Bootstrap-style `.collapse` elements
   - Click "show more" / "read more" / "expand" buttons
   - Force all tab panels visible (click tab triggers, then set all tab panels to `display: block`)
3. **Strip boilerplate and non-content elements** (configurable via YAML):
   - Navigation, headers, footers, sidebars
   - Cookie/consent banners
   - "Back to top" links, social sharing, feedback forms
   - Scripts, styles, iframes, SVGs, images, videos
   - Site-specific elements (e.g. "Acknowledgement of Country", newsletter signup)
4. **Extract the main content area** using a priority list of CSS selectors (e.g. `main`, `article`, `[role='main']`)
5. **Convert to clean Markdown** using `markdownify`:
   - Preserve headings, lists, tables, links, emphasis
   - Strip remaining HTML artifacts
   - Remove leaked SVG/path elements via regex
   - Remove orphaned navigation links
   - Collapse excessive blank lines
6. **Handle `<br>` tags** — replace with newline text nodes before conversion
7. **Handle label/value concatenation** — insert newlines between short label elements and adjacent text that would otherwise run together (e.g. "Opening hours8:30am" → separate lines)

### Configuration

Use a YAML config file (`scrape-config.yaml`) with these sections:

```yaml
# Azure Blob Storage settings
storage:
  account_name: <storage-account>
  container_name: <container>

# Local output directory
output_dir: <output-folder>

# CSS selectors for elements to remove
strip_selectors:
  - "nav"
  - "header"
  - "footer"
  # ... site-specific selectors

# CSS selectors to find the main content (tried in order, first match wins)
content_selectors:
  - "main"
  - "article"
  - "[role='main']"

# Pages to scrape
pages:
  - url: https://example.com/page1
    name: optional-output-filename  # .md extension added automatically
  - url: https://example.com/page2
    # name derived from URL path if omitted
```

### CLI Interface

```
python scrape_pages.py                          # scrape + save locally
python scrape_pages.py --upload                 # scrape + save + upload to blob
python scrape_pages.py --upload-only            # upload existing local files only
python scrape_pages.py --config my-config.yaml  # use custom config file
```

### Upload to Azure Blob Storage

- Use `DefaultAzureCredential` for authentication (Azure CLI login)
- Set content type to `text/markdown; charset=utf-8`
- Overwrite existing blobs with the same name

### Quality Checks

- After saving each page, report character count and word count
- Warn if extracted content is very short (< 20 words) — may indicate a structural issue

### Dependencies

- `playwright` — headless browser for JS-rendered pages
- `beautifulsoup4` — HTML parsing and element removal
- `markdownify` — HTML to Markdown conversion
- `pyyaml` — config file parsing
- `azure-storage-blob` + `azure-identity` — blob upload

### Site-Specific Customization

When adapting for a new site:

1. Visit a few pages in DevTools and identify:
   - The main content container selector
   - Navigation/sidebar/footer selectors to strip
   - Any collapsed/tabbed content patterns
   - Boilerplate text blocks (e.g. copyright, cookie notices)
2. Add site-specific `strip_selectors` to the config
3. Add any site-specific JS-based boilerplate removal in `remove_boilerplate_via_js()`
4. Add any site-specific text patterns to `_remove_boilerplate_text()`
5. Test with 2-3 representative pages before scraping the full site

## Example

To create a scraper for a hospital website:

```
I need to scrape pages from [website URL]. The pages have:
- Tabbed content (e.g. Overview, Services, Getting There tabs on location pages)
- Accordion sections that need expanding
- Standard nav/header/footer to strip
- [any other site-specific patterns]

Use the scraper pattern from this prompt. Here are some sample URLs:
- [url1]
- [url2]
- [url3]
```
