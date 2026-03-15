#!/usr/bin/env python3
"""
Upload markdown files from the local wh-kb-docs-md folder to Azure Blob Storage.

Optionally clears the container first (removing old PDFs or stale files).

Usage:
    python upload_docs.py                # upload .md files (keeps existing blobs)
    python upload_docs.py --clean        # delete all existing blobs first, then upload
    python upload_docs.py --dry-run      # show what would be uploaded without doing it
"""

import argparse
import sys
from pathlib import Path

import yaml
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

DEFAULT_CONFIG = "scrape-config.yaml"


def load_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_container_client(account_name: str, container_name: str):
    credential = DefaultAzureCredential()
    blob_service = BlobServiceClient(
        account_url=f"https://{account_name}.blob.core.windows.net",
        credential=credential,
    )
    return blob_service.get_container_client(container_name)


def clean_container(container_client, dry_run=False):
    """Delete all blobs in the container."""
    blobs = list(container_client.list_blobs())
    if not blobs:
        print("  Container is already empty.")
        return

    print(f"  Deleting {len(blobs)} existing blob(s)...")
    for blob in blobs:
        if dry_run:
            print(f"    [dry-run] Would delete: {blob.name}")
        else:
            print(f"    Deleting: {blob.name}")
            container_client.delete_blob(blob.name)

    if not dry_run:
        print(f"  Deleted {len(blobs)} blob(s).")


def upload_files(container_client, local_dir, account_name, container_name, dry_run=False):
    """Upload all .md files from local_dir to the container."""
    md_files = sorted(Path(local_dir).glob("*.md"))

    if not md_files:
        print(f"  No .md files found in {local_dir}/")
        sys.exit(1)

    print(f"  Uploading {len(md_files)} file(s) from {local_dir}/...\n")

    for filepath in md_files:
        blob_name = filepath.name
        size_kb = filepath.stat().st_size / 1024

        if dry_run:
            print(f"    [dry-run] Would upload: {blob_name} ({size_kb:.1f} KB)")
        else:
            print(f"    Uploading: {blob_name} ({size_kb:.1f} KB)")
            with open(filepath, "rb") as data:
                container_client.upload_blob(
                    name=blob_name,
                    data=data,
                    overwrite=True,
                    content_settings=ContentSettings(
                        content_type="text/markdown; charset=utf-8",
                    ),
                )

    if not dry_run:
        print(f"\n  Uploaded {len(md_files)} file(s) to {account_name}/{container_name}.")


def main():
    parser = argparse.ArgumentParser(
        description="Upload markdown docs to Azure Blob Storage."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete all existing blobs in the container before uploading.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        help="Path to YAML config file (default: scrape-config.yaml)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    storage = config.get("storage", {})
    account_name = storage.get("account_name")
    container_name = storage.get("container_name")
    local_dir = config.get("output_dir", "wh-kb-docs-md")

    if not account_name or not container_name:
        print("ERROR: storage.account_name and storage.container_name must be set in config.")
        sys.exit(1)

    print(f"Config:  {args.config}")
    print(f"Target:  {account_name}/{container_name}")
    print(f"Source:  {local_dir}/\n")

    container_client = get_container_client(account_name, container_name)

    if args.clean:
        print("Cleaning container...")
        clean_container(container_client, dry_run=args.dry_run)
        print()

    print("Uploading files...")
    upload_files(container_client, local_dir, account_name, container_name, dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
