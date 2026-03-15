#!/usr/bin/env python3
"""
Western Health web page scraper.

Fetches web pages using Playwright, expands collapsed sections and tabs,
strips navigation/styling, extracts core content as Markdown,
and optionally uploads to Azure Blob Storage.

Usage:
    python scrape_pages.py                          # scrape + save locally
    python scrape_pages.py --upload                 # scrape + save + upload to blob
    python scrape_pages.py --upload-only            # upload existing local files only
    python scrape_pages.py --config my-config.yaml  # use custom config file
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import yaml
from bs4 import BeautifulSoup, Comment, NavigableString
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = "scrape-config.yaml"


def load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Page fetching & expansion
# ---------------------------------------------------------------------------


def click_all_tabs(page) -> None:
    """
    Click on all tab triggers to make their tab panels visible.
    After clicking, force all tab panels to be visible so we capture everything.
    This handles the Western Health location pages (Overview, Emergency, Services, etc.).
    """
    page.evaluate("""
        () => {
            // Click all tab triggers
            const tabTriggers = document.querySelectorAll(
                '[role="tab"], .tab-link, .tab-trigger, ' +
                '.nav-tabs a, .nav-tabs button, ' +
                '[data-bs-toggle="tab"], [data-toggle="tab"], ' +
                '.tabs__tab, .tabs a, .horizontal-tabs a, ' +
                '.field--name-field-tab a, .paragraphs-tabs a'
            );
            tabTriggers.forEach(t => {
                try { t.click(); } catch(e) {}
            });

            // Force all tab panels visible
            const tabPanels = document.querySelectorAll(
                '[role="tabpanel"], .tab-pane, .tab-content > div, ' +
                '.tabs__content > div, .tabs__panel, ' +
                '.horizontal-tabs-panes > div, ' +
                '.field--name-field-tab .paragraph, ' +
                '.paragraphs-tabs-wrapper .paragraph'
            );
            tabPanels.forEach(panel => {
                panel.style.display = 'block';
                panel.style.visibility = 'visible';
                panel.style.opacity = '1';
                panel.style.height = 'auto';
                panel.style.overflow = 'visible';
                panel.classList.add('active', 'show', 'is-active');
                panel.removeAttribute('hidden');
                panel.setAttribute('aria-hidden', 'false');
            });
        }
    """)
    time.sleep(0.5)


def expand_collapsed_sections(page) -> None:
    """Click on common accordion / collapsible triggers to expand all content."""

    # Strategy 1: Click elements with aria-expanded="false"
    page.evaluate("""
        () => {
            document.querySelectorAll('[aria-expanded="false"]').forEach(el => {
                try {
                    el.click();
                    el.setAttribute('aria-expanded', 'true');
                } catch(e) {}
            });
        }
    """)
    time.sleep(0.3)

    # Strategy 2: Toggle common accordion/collapse classes
    page.evaluate("""
        () => {
            // Bootstrap-style collapses
            document.querySelectorAll('.collapse:not(.show)').forEach(el => {
                el.classList.add('show');
                el.style.display = 'block';
                el.style.height = 'auto';
            });

            // Generic collapsed elements
            document.querySelectorAll('.collapsed, .is-collapsed, [data-collapsed="true"]').forEach(el => {
                el.classList.remove('collapsed', 'is-collapsed');
                el.removeAttribute('data-collapsed');
            });

            // Details/summary elements
            document.querySelectorAll('details:not([open])').forEach(el => {
                el.setAttribute('open', '');
            });

            // Elements hidden with inline display:none (skip nav/header/footer)
            document.querySelectorAll('[style*="display: none"], [style*="display:none"]').forEach(el => {
                if (el.closest('nav, header, footer, .sidenav, .sidebar, [role="navigation"]')) return;
                el.style.display = 'block';
            });

            // Accordion panels
            document.querySelectorAll(
                '.accordion-body, .accordion-content, .accordion-collapse, ' +
                '.panel-body, .panel-collapse, .collapse-content'
            ).forEach(el => {
                el.style.display = 'block';
                el.style.height = 'auto';
                el.style.visibility = 'visible';
                el.style.opacity = '1';
                el.classList.add('show');
            });
        }
    """)
    time.sleep(0.3)

    # Strategy 3: Click any remaining "expand" / "show more" / "read more" buttons
    page.evaluate("""
        () => {
            const triggers = document.querySelectorAll(
                'button, [role="button"], .accordion-header, .accordion-toggle, ' +
                '.expand-trigger, .toggle-trigger, .collapsible-header'
            );
            triggers.forEach(el => {
                const text = (el.textContent || '').toLowerCase();
                const ariaExp = el.getAttribute('aria-expanded');
                if (ariaExp === 'false' || text.includes('expand') ||
                    text.includes('show more') || text.includes('read more')) {
                    try { el.click(); } catch(e) {}
                }
            });
        }
    """)
    time.sleep(0.3)


def remove_boilerplate_via_js(page) -> None:
    """
    Remove Western Health-specific boilerplate elements via JS before
    extracting HTML. This catches elements that are hard to target with
    pure CSS selectors.
    """
    page.evaluate("""
        () => {
            // Remove "Skip to main content" link
            document.querySelectorAll('a').forEach(a => {
                if ((a.textContent || '').trim().toLowerCase() === 'skip to main content') {
                    a.remove();
                }
            });

            // Remove "Important update" banners
            document.querySelectorAll('div, section, aside').forEach(el => {
                const text = (el.textContent || '').trim();
                if (text.startsWith('Important update') && text.length < 500) {
                    el.remove();
                }
            });

            // Remove "Was this page helpful?" blocks
            document.querySelectorAll('div, section').forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                if (text.startsWith('was this page helpful')) {
                    el.remove();
                }
            });

            // Remove "Want to hear more from us?" / newsletter blocks
            document.querySelectorAll('div, section').forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                if (text.startsWith('want to hear more from us')) {
                    el.remove();
                }
            });

            // Remove "In the case of a life threatening emergency" blocks
            document.querySelectorAll('div, section').forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                if (text.startsWith('in the case of a life threatening')) {
                    el.remove();
                }
            });

            // Remove Acknowledgement of Country
            document.querySelectorAll('div, section').forEach(el => {
                const heading = el.querySelector('h1, h2, h3, h4, h5, h6');
                if (heading && (heading.textContent || '').trim().toLowerCase().includes('acknowledgement of country')) {
                    el.remove();
                }
            });

            // Remove "On this page" sidebar
            document.querySelectorAll('div, aside, section').forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                if (text.startsWith('on this page') && text.length < 1000) {
                    el.remove();
                }
            });

            // Remove "Related pages" / "Services available here" blocks
            document.querySelectorAll('div, aside, section').forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                if ((text.startsWith('related pages') || text.startsWith('services available here'))
                    && text.length < 1000) {
                    el.remove();
                }
            });

            // Remove Like / Dislike buttons
            document.querySelectorAll('a, button').forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                if (text === 'like' || text === 'dislike') {
                    el.remove();
                }
            });

            // Remove "Back to top" links
            document.querySelectorAll('a, button').forEach(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                if (text === 'back to top') {
                    el.remove();
                }
            });

            // Remove copyright block
            document.querySelectorAll('div, p, span').forEach(el => {
                const text = (el.textContent || '').trim();
                if (text.startsWith('© Copyright') && text.length < 200) {
                    el.remove();
                }
            });
        }
    """)


def fetch_page_html(url: str, timeout: int = 30000) -> str:
    """Fetch a page with Playwright, expand tabs and collapsed sections, return HTML."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        print(f"  Loading: {url}")
        page.goto(url, wait_until="networkidle", timeout=timeout)

        # Dismiss cookie/consent banners
        page.evaluate("""
            () => {
                const banners = document.querySelectorAll(
                    '.cookie-banner, .consent-banner, #cookie-consent, ' +
                    '[class*="cookie"], [class*="consent"], [id*="cookie"]'
                );
                banners.forEach(el => el.remove());
            }
        """)

        print("  Expanding tabs...")
        click_all_tabs(page)

        print("  Expanding collapsed sections...")
        expand_collapsed_sections(page)

        print("  Removing boilerplate...")
        remove_boilerplate_via_js(page)

        html = page.content()
        browser.close()

    return html


# ---------------------------------------------------------------------------
# HTML → Markdown conversion
# ---------------------------------------------------------------------------


def extract_core_content(
    html: str,
    strip_selectors: list[str],
    content_selectors: list[str],
) -> str:
    """
    Parse HTML, strip non-content elements, find the main content area,
    and convert to clean Markdown.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Strip unwanted elements by CSS selector
    for selector in strip_selectors:
        for el in soup.select(selector):
            el.decompose()

    # Find main content area
    content = None
    for selector in content_selectors:
        content = soup.select_one(selector)
        if content:
            break

    if not content:
        content = soup.find("body") or soup

    # Remove remaining boilerplate text patterns in the soup
    _remove_boilerplate_text(content)

    # Remove all class/style/id/data/event attributes to clean up
    attrs_to_remove = [
        "class", "style", "id", "data-toggle", "data-target",
        "data-parent", "data-bs-toggle", "data-bs-target",
        "aria-labelledby", "aria-hidden", "aria-expanded",
        "aria-controls", "aria-selected",
        "onclick", "onload", "role",
    ]
    for tag in content.find_all(True):
        for attr in attrs_to_remove:
            if tag.has_attr(attr):
                del tag[attr]

    # Remove empty block elements
    for tag in content.find_all(["div", "span", "section", "aside"]):
        if not tag.get_text(strip=True) and not tag.find(["table", "pre", "code"]):
            tag.decompose()

    # Remove image/figure/svg tags before conversion (since strip and convert
    # cannot be used together in markdownify)
    for tag in content.find_all(["img", "picture", "figure", "figcaption",
                                  "svg", "video", "audio", "canvas"]):
        tag.decompose()

    # Ensure <br> tags become proper line breaks (insert newline text node)
    for br in content.find_all("br"):
        br.replace_with(NavigableString("\n"))

    # Separate label/heading elements that run into adjacent content.
    # The Western Health site uses sibling <div>/<span> elements for labels
    # like "Opening hours", "Visiting hours", "Address" that get concatenated
    # with the next text node during conversion.
    for tag in content.find_all(["div", "span", "h3", "h4", "h5", "h6"]):
        text = tag.get_text(strip=True)
        # Short label-like text followed immediately by sibling content
        if text and len(text) < 50 and tag.next_sibling:
            # Insert a newline after the tag if the next sibling is a text node
            # that starts without whitespace
            sibling = tag.next_sibling
            if isinstance(sibling, NavigableString):
                stripped = str(sibling).lstrip()
                if stripped and not str(sibling).startswith(('\n', ' ')):
                    sibling.replace_with(NavigableString("\n" + str(sibling)))

    # Remove elements that are just tab labels (duplicate of content headings)
    # e.g. "Overview Emergency department Services Getting there ..."
    for tag in content.find_all(["ul", "div"]):
        children_text = [li.get_text(strip=True) for li in tag.find_all("li", recursive=False)]
        if not children_text:
            children_text = [c.get_text(strip=True) for c in tag.children
                             if hasattr(c, 'get_text')]
        # If all children are short labels (tab triggers), remove the container
        if (len(children_text) >= 3
            and all(len(t) < 40 for t in children_text)
            and any(t.lower() in ("overview", "services", "getting there",
                                   "planning a visit", "features and amenities",
                                   "emergency department")
                    for t in children_text)):
            tag.decompose()

    # Convert to Markdown
    markdown = md(
        str(content),
        heading_style="atx",
        bullets="-",
        convert=[
            "h1", "h2", "h3", "h4", "h5", "h6",
            "p", "a", "ul", "ol", "li",
            "table", "thead", "tbody", "tr", "th", "td",
            "strong", "em", "b", "i", "br", "hr",
            "blockquote", "pre", "code",
            "dl", "dt", "dd",
        ],
    )

    # Clean up the markdown
    markdown = clean_markdown(markdown)

    return markdown


def _remove_boilerplate_text(soup) -> None:
    """Remove remaining Western Health boilerplate that survived JS removal."""
    boilerplate_starts = [
        "skip to main content",
        "important update",
        "was this page helpful",
        "want to hear more from us",
        "in the case of a life threatening",
        "© copyright",
        "privacy policy",
        "back to top",
        "acknowledgement of country",
        "on this page",
        "related pages",
        "services available here",
    ]

    # Check block-level elements for boilerplate text
    for tag in soup.find_all(["div", "section", "aside", "p"]):
        text = tag.get_text(strip=True).lower()
        for bp in boilerplate_starts:
            if text.startswith(bp):
                tag.decompose()
                break


def clean_markdown(text: str) -> str:
    """Clean up converted markdown text."""
    # Remove excessive link references with no useful text
    text = re.sub(r"\[Image:.*?\]\(.*?\)", "", text)

    # Remove any leaked SVG content
    text = re.sub(r"<svg[\s\S]*?</svg>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<defs>[\s\S]*?</defs>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<path[\s\S]*?/>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<rect[\s\S]*?/>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<clipPath[\s\S]*?</clipPath>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<g[\s\S]*?</g>", "", text, flags=re.IGNORECASE)

    # Collapse 3+ blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove lines that are only whitespace
    text = re.sub(r"^[ \t]+$", "", text, flags=re.MULTILINE)

    # Remove trailing whitespace on each line
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)

    # Remove lines that are just "---" separators if they appear excessively
    # (keep at most one in a row)
    text = re.sub(r"(\n---\n){2,}", "\n---\n", text)

    # Remove orphaned link-only lines that are just site nav
    # e.g. "[Home](https://westernhealth.org.au/home)"
    nav_pattern = re.compile(
        r"^\[(?:Home|Patients and visitors|Health professionals|Services and clinics|"
        r"Locations|Work with us|Emergency departments|About us|Research and education|"
        r"News|Donate|Contact us|Social media \w+)\]\(https?://.*?\)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    text = nav_pattern.sub("", text)

    # Remove "Emergency" standalone links
    text = re.sub(
        r"^\[Emergency\]\(https?://westernhealth\.org\.au/emergency-departments\)\s*$",
        "", text, flags=re.MULTILINE,
    )

    # Remove Western Health logo references
    text = re.sub(
        r"^\[Logo Western Health.*?\]\(.*?\)\s*$",
        "", text, flags=re.MULTILINE,
    )

    # Collapse again after removals
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove leading/trailing whitespace
    text = text.strip()

    # Ensure file ends with newline
    text += "\n"

    return text


# ---------------------------------------------------------------------------
# Filename derivation
# ---------------------------------------------------------------------------


def derive_filename(url: str, name: str | None = None) -> str:
    """Derive a markdown filename from a URL or explicit name."""
    if name:
        safe = re.sub(r"[^\w\-]", "-", name).strip("-")
        return f"{safe}.md"

    path = urlparse(url).path
    # Remove trailing slash and extension
    path = path.rstrip("/")
    basename = os.path.basename(path)
    basename = os.path.splitext(basename)[0]

    # Clean up
    safe = re.sub(r"[^\w\-]", "-", basename).strip("-").lower()
    return f"{safe}.md"


# ---------------------------------------------------------------------------
# Azure Blob upload
# ---------------------------------------------------------------------------


def upload_to_blob(
    output_dir: str, account_name: str, container_name: str
) -> None:
    """Upload all .md files from output_dir to Azure Blob Storage."""
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient, ContentSettings

    print(f"\nUploading to blob storage: {account_name}/{container_name}")

    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        credential=credential,
    )
    container = blob_service.get_container_client(container_name)

    md_files = sorted(Path(output_dir).glob("*.md"))
    if not md_files:
        print("  No .md files found to upload.")
        return

    for filepath in md_files:
        blob_name = filepath.name
        print(f"  Uploading: {blob_name}")
        with open(filepath, "rb") as data:
            container.upload_blob(
                name=blob_name,
                data=data,
                overwrite=True,
                content_settings=ContentSettings(
                    content_type="text/markdown; charset=utf-8",
                ),
            )

    print(f"  Uploaded {len(md_files)} file(s).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Western Health web pages to Markdown and upload to Azure Blob Storage."
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG, help="Path to YAML config file"
    )
    parser.add_argument(
        "--upload", action="store_true", help="Upload to Azure Blob Storage after scraping"
    )
    parser.add_argument(
        "--upload-only", action="store_true", help="Skip scraping, only upload existing files"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    output_dir = config.get("output_dir", "wh-kb-docs-md")
    storage = config.get("storage", {})
    strip_selectors = config.get("strip_selectors", [])
    content_selectors = config.get("content_selectors", [])
    pages = config.get("pages", [])

    os.makedirs(output_dir, exist_ok=True)

    if not args.upload_only:
        # Filter out commented/None entries
        pages = [p for p in (pages or []) if p and p.get("url")]

        if not pages:
            print("No pages configured in the config file. Add URLs under 'pages:'.")
            sys.exit(1)

        print(f"Scraping {len(pages)} page(s)...\n")

        for i, entry in enumerate(pages, 1):
            url = entry["url"]
            name = entry.get("name")
            filename = derive_filename(url, name)

            print(f"[{i}/{len(pages)}] {filename}")

            try:
                html = fetch_page_html(url)
                markdown = extract_core_content(html, strip_selectors, content_selectors)

                out_path = os.path.join(output_dir, filename)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(markdown)

                # Quick quality check
                word_count = len(markdown.split())
                if word_count < 20:
                    print(f"  ⚠ WARNING: Very little content extracted ({word_count} words)")
                else:
                    print(f"  ✓ Saved: {out_path} ({len(markdown)} chars, ~{word_count} words)\n")

            except Exception as e:
                print(f"  ✗ ERROR: {e}\n")

    if args.upload or args.upload_only:
        account = storage.get("account_name")
        container = storage.get("container_name")
        if not account or not container:
            print("ERROR: storage.account_name and storage.container_name must be set in config.")
            sys.exit(1)
        upload_to_blob(output_dir, account, container)

    print("\nDone.")


if __name__ == "__main__":
    main()
