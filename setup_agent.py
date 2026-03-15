#!/usr/bin/env python3
"""
Setup the Foundry agent, memory store, and knowledge base connection.

This script creates or updates:
  1. Memory store (for user preferences and context)
  2. Agent (wh-patient-helper) with knowledge base, memory, and web search tools

Prerequisites:
  - Azure resources provisioned (via `azd provision` or manually)
  - Search index, skillset, datasource, indexer deployed (via setup-search.sh)
  - Knowledge base created in Foundry portal (connects AI Search to the project)
  - .env file configured with PROJECT_ENDPOINT, AGENT_NAME, etc.

Usage:
    python setup_agent.py
    python setup_agent.py --reset  # Delete and recreate everything

Environment variables (from .env):
    PROJECT_ENDPOINT          - Foundry project endpoint
    AGENT_NAME                - Agent name (default: wh-patient-helper)
    MEMORY_STORE_NAME         - Memory store name (auto-generated if not set)
    AGENT_MODEL               - Chat model deployment (default: gpt-5.1)
    EMBEDDING_MODEL           - Embedding model deployment (default: text-embedding-3-small)
    MEMORY_UPDATE_DELAY       - Seconds of inactivity before memory update (default: 10, use 300 in prod)
    KB_CONNECTION_ID          - Knowledge base MCP connection ID (from Foundry portal)
    KB_SERVER_URL             - Knowledge base MCP server URL (from Foundry portal)
"""

import os
import sys
import json
import argparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    MemoryStoreDefaultDefinition,
    MemoryStoreDefaultOptions,
    MemorySearchPreviewTool,
    PromptAgentDefinition,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
AGENT_NAME = os.environ.get("AGENT_NAME", "wh-patient-helper")
VOICE_AGENT_NAME = os.environ.get("VOICE_AGENT_NAME", "wh-patient-helper-voice")
MEMORY_STORE_NAME = os.environ.get("MEMORY_STORE_NAME", "wh-patient-memory")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "gpt-5.1")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
# Demo: 10s. Production: set to 300 (5 minutes).
MEMORY_UPDATE_DELAY = int(os.environ.get("MEMORY_UPDATE_DELAY", "10"))
# These come from the Foundry portal after creating a knowledge base connection
KB_CONNECTION_ID = os.environ.get("KB_CONNECTION_ID", "kb-wh-knowledgebase-mmuck")
KB_SERVER_URL = os.environ.get(
    "KB_SERVER_URL",
    "https://mydemossrch11617.search.windows.net/knowledgebases/wh-knowledgebase/mcp?api-version=2025-11-01-Preview",
)

AGENT_INSTRUCTIONS = (
    "You are a helpful AI assistant that answers questions for patients and "
    "visitors to the Western Hospital. You can answer questions about patient "
    "services, transportation to get to the locations, available locations, "
    "procedures and services, helping patient prepare for a visit or surgery. "
    "Use available tools and knowledge bases only. "
    "Do not answer questions not related to Western Hospital and healthcare."
)

MEMORY_STORE_DESCRIPTION = (
    "Use this memory store to recall patient and visitor preferences and "
    "demographics, for example, where they live (suburb), preferred hospital "
    "locations, preferred languages, verbosity of answers (concise, simple "
    "language, detailed, point form, etc.)."
)

MEMORY_USER_PROFILE_DETAILS = (
    "Focus on: location/suburb, preferred hospital, language preferences, "
    "answer style preferences (concise, detailed, dot points), "
    "medical context (upcoming procedures, conditions). "
    "Avoid: sensitive personal data, financial info, credentials."
)

VOICE_AGENT_INSTRUCTIONS = (
    "You are a friendly, conversational voice assistant for Western Health "
    "patients and visitors. Speak naturally in complete sentences as if "
    "talking face-to-face. Never use bullet points, numbered lists, markdown "
    "formatting, headings, or special characters. These sound unnatural when "
    "spoken aloud. Keep responses concise and warm. "
    "When the user speaks a language other than English, respond in that same language. "
    "Supported languages: English, Vietnamese, Greek, Mandarin Chinese, Spanish, Italian. "
    "Use available tools and knowledge bases only. "
    "Do not answer questions not related to Western Hospital and healthcare."
)


# ── Client ─────────────────────────────────────────────────────────

project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)


# ── Memory Store ───────────────────────────────────────────────────

def create_memory_store():
    """Create the memory store if it doesn't exist."""
    # Check if it already exists
    try:
        existing = project.beta.memory_stores.get(MEMORY_STORE_NAME)
        print(f"✓ Memory store already exists: {existing.name}")
        return existing.name
    except Exception:
        pass

    print(f"Creating memory store: {MEMORY_STORE_NAME}")
    definition = MemoryStoreDefaultDefinition(
        chat_model=AGENT_MODEL,
        embedding_model=EMBEDDING_MODEL,
        options=MemoryStoreDefaultOptions(
            chat_summary_enabled=True,
            user_profile_enabled=True,
            user_profile_details=MEMORY_USER_PROFILE_DETAILS,
        ),
    )

    store = project.beta.memory_stores.create(
        name=MEMORY_STORE_NAME,
        definition=definition,
        description=MEMORY_STORE_DESCRIPTION,
    )
    print(f"✓ Created memory store: {store.name}")
    return store.name


def delete_memory_store():
    """Delete the memory store."""
    try:
        project.beta.memory_stores.delete(MEMORY_STORE_NAME)
        print(f"✓ Deleted memory store: {MEMORY_STORE_NAME}")
    except Exception as e:
        print(f"  (Memory store not found or already deleted: {e})")


# ── Agent ──────────────────────────────────────────────────────────

def _build_tools(memory_store_name: str) -> list:
    """Build the shared tools list for both text and voice agents."""
    tools = []

    # 1. Knowledge base (MCP connection to AI Search)
    kb_tool = {
        "type": "mcp",
        "server_label": KB_CONNECTION_ID.replace("-", "_"),
        "server_url": KB_SERVER_URL,
        "require_approval": {
            "never": {"tool_names": ["knowledge_base_retrieve"]}
        },
        "project_connection_id": KB_CONNECTION_ID,
    }
    tools.append(kb_tool)

    # 2. Memory search tool
    memory_tool = MemorySearchPreviewTool(
        memory_store_name=memory_store_name,
        scope="{{$userId}}",
        update_delay=MEMORY_UPDATE_DELAY,
    )
    tools.append(memory_tool)

    # 3. Web search (for supplementary info)
    tools.append({"type": "web_search_preview"})

    return tools


def create_agent(memory_store_name: str):
    """Create or update the text agent with all tools."""
    print(f"Creating/updating agent: {AGENT_NAME}")

    tools = _build_tools(memory_store_name)

    # Create the agent version
    agent = project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=AGENT_MODEL,
            instructions=AGENT_INSTRUCTIONS,
            tools=tools,
        ),
    )

    print(f"✓ Agent created: {agent.name} (version: {agent.version})")
    print(f"  Model: {AGENT_MODEL}")
    print(f"  Tools: {len(tools)}")
    print(f"    - Knowledge base: {KB_CONNECTION_ID}")
    print(f"    - Memory store: {memory_store_name} (delay: {MEMORY_UPDATE_DELAY}s)")
    print(f"    - Web search: enabled")
    return agent


def create_voice_agent(memory_store_name: str):
    """Create or update the voice agent (same tools, voice-optimised instructions)."""
    print(f"Creating/updating voice agent: {VOICE_AGENT_NAME}")

    tools = _build_tools(memory_store_name)

    agent = project.agents.create_version(
        agent_name=VOICE_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=AGENT_MODEL,
            instructions=VOICE_AGENT_INSTRUCTIONS,
            tools=tools,
        ),
    )

    print(f"✓ Voice agent created: {agent.name} (version: {agent.version})")
    print(f"  Model: {AGENT_MODEL}")
    print(f"  Instructions: voice-optimised (no formatting, natural prose)")
    return agent


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Setup Foundry agent and memory store")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate everything")
    parser.add_argument("--only", choices=["text", "voice"], default=None,
                        help="Create only the text or voice agent (default: both)")
    args = parser.parse_args()

    print("=" * 50)
    print("WH Foundry Agent Setup")
    print(f"  Project: {PROJECT_ENDPOINT}")
    if args.only != "voice":
        print(f"  Text agent:  {AGENT_NAME}")
    if args.only != "text":
        print(f"  Voice agent: {VOICE_AGENT_NAME}")
    print(f"  Model:       {AGENT_MODEL}")
    print("=" * 50)
    print()

    if args.reset:
        print("Resetting...")
        delete_memory_store()
        print()

    # 1. Create memory store (always needed)
    store_name = create_memory_store()
    print()

    # 2. Create text agent
    if args.only in (None, "text"):
        create_agent(store_name)
        print()

    # 3. Create voice agent
    if args.only in (None, "voice"):
        create_voice_agent(store_name)
        print()

    print("Done!")
    print()
    print("Next steps:")
    print("  1. Ensure the knowledge base is connected in the Foundry portal")
    print("  2. Run the web app: ./start.sh")
    print("  3. Or use the CLI: python chat.py")


if __name__ == "__main__":
    main()
