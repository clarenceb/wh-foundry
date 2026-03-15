#!/usr/bin/env python3
"""
Western Health Chat — FastAPI backend.

Provides REST + SSE endpoints for the React frontend to talk to the
Foundry agent (wh-patient-helper) with streaming responses.

Usage:
    uvicorn web.api.server:app --reload --port 8000
"""

import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from urllib.parse import urlparse

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# ── Config ─────────────────────────────────────────────────────────
load_dotenv()

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
AGENT_NAME = os.environ["AGENT_NAME"]
MEMORY_STORE_NAME = os.environ.get("MEMORY_STORE_NAME", "wh-patient-memory")
MEMORY_SCOPE = os.environ.get("MEMORY_SCOPE", "demo_user")
STORAGE_ACCOUNT_NAME = os.environ.get("STORAGE_ACCOUNT_NAME", "whkbdocs")

# ── Foundry client (singleton) ─────────────────────────────────────
project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)
openai_client = project.get_openai_client()

# ── In-memory store for conversations ─────────────────────────────
# Maps our local chat_id → { foundry_conversation_id, messages[] }
chats: dict[str, dict] = {}

# ── FastAPI app ────────────────────────────────────────────────────
app = FastAPI(title="Western Health Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ─────────────────────────────────────────────────────────
class ChatCreateResponse(BaseModel):
    chat_id: str
    title: str


class MessageRequest(BaseModel):
    message: str


class ChatSummary(BaseModel):
    chat_id: str
    title: str
    message_count: int


class MemoryItem(BaseModel):
    id: str
    content: str


# ── Helpers ────────────────────────────────────────────────────────

def _extract_citations(event) -> list[dict]:
    """Extract citation URLs from a response.completed event."""
    citations = []
    seen = set()
    try:
        response = event.response if hasattr(event, "response") else event
        output_items = getattr(response, "output", []) or []
        for item in output_items:
            content_parts = getattr(item, "content", []) or []
            for part in content_parts:
                annotations = getattr(part, "annotations", []) or []
                for ann in annotations:
                    ann_type = getattr(ann, "type", "")
                    url = ""
                    title = ""

                    if ann_type == "url_citation":
                        url = getattr(ann, "url", "")
                        title = getattr(ann, "title", "")
                    elif ann_type == "file_citation":
                        # Try to extract URL from various fields
                        url = (getattr(ann, "url", "")
                               or getattr(ann, "file_id", "")
                               or getattr(ann, "filename", ""))
                        title = getattr(ann, "title", "") or getattr(ann, "filename", "")
                    else:
                        # Try generic url/title fields on unknown annotation types
                        url = getattr(ann, "url", "")
                        title = getattr(ann, "title", "")

                    if not url or url in seen:
                        continue

                    # Skip bare index refs like "doc_0" that aren't real URLs
                    if not url.startswith("http"):
                        continue

                    # Skip knowledge base / search service endpoints (not actual documents)
                    if "/knowledgebases/" in url or url.endswith("/mcp"):
                        continue

                    seen.add(url)

                    # Derive a friendly title from blob storage URLs
                    if not title or title == url:
                        title = _friendly_blob_title(url)

                    citations.append({"url": url, "title": title})
    except Exception:
        pass
    return citations


def _extract_memories_used(event) -> list[dict]:
    """Extract memories that were used in the response from memory_search_call items."""
    memories = []
    try:
        response = event.response if hasattr(event, "response") else event
        output_items = getattr(response, "output", []) or []
        for item in output_items:
            item_type = getattr(item, "type", "")
            if item_type == "memory_search_call":
                results = getattr(item, "results", []) or []
                for r in results:
                    mem_item = getattr(r, "memory_item", None)
                    if mem_item:
                        content = getattr(mem_item, "content", "")
                        mem_id = getattr(mem_item, "memory_id", "")
                        if content:
                            memories.append({"id": mem_id, "content": content})
    except Exception:
        pass
    return memories


def _friendly_blob_title(url: str) -> str:
    """Convert a blob URL like .../wh-kb-docs/wh-services-cancer-services.md to a nice title."""
    try:
        filename = url.split("/")[-1]
        # Strip query params
        if "?" in filename:
            filename = filename.split("?")[0]
        # Remove extension
        name = filename.rsplit(".", 1)[0] if "." in filename else filename
        # Remove common prefixes like "wh-"
        if name.startswith("wh-"):
            name = name[3:]
        # Convert hyphens to spaces, title case
        return name.replace("-", " ").strip().title()
    except Exception:
        return url


# ── Chat endpoints ─────────────────────────────────────────────────

@app.post("/api/chats", response_model=ChatCreateResponse)
def create_chat():
    """Create a new chat session (Foundry conversation)."""
    conversation = openai_client.conversations.create()
    chat_id = str(uuid.uuid4())
    chats[chat_id] = {
        "foundry_id": conversation.id,
        "title": "New Chat",
        "messages": [],
    }
    return ChatCreateResponse(chat_id=chat_id, title="New Chat")


@app.get("/api/chats", response_model=list[ChatSummary])
def list_chats():
    """List all chat sessions."""
    return [
        ChatSummary(
            chat_id=cid,
            title=data["title"],
            message_count=len(data["messages"]),
        )
        for cid, data in chats.items()
    ]


@app.get("/api/chats/{chat_id}/messages")
def get_messages(chat_id: str):
    """Get all messages for a chat."""
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chats[chat_id]["messages"]


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    """Delete a chat session."""
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    del chats[chat_id]
    return {"ok": True}


@app.post("/api/chats/{chat_id}/messages")
async def send_message(chat_id: str, req: MessageRequest):
    """Send a message and stream the agent response via SSE."""
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = chats[chat_id]
    foundry_id = chat["foundry_id"]

    # Store user message
    chat["messages"].append({"role": "user", "content": req.message})

    # Auto-title from first message
    if chat["title"] == "New Chat" and len(chat["messages"]) == 1:
        chat["title"] = req.message[:50] + ("..." if len(req.message) > 50 else "")

    async def event_stream() -> AsyncGenerator[str, None]:
        full_text = ""
        try:
            stream = openai_client.responses.create(
                conversation=foundry_id,
                extra_body={
                    "agent_reference": {
                        "name": AGENT_NAME,
                        "type": "agent_reference",
                    }
                },
                input=req.message,
                stream=True,
            )
            for event in stream:
                # The responses API streams delta events
                if hasattr(event, "type"):
                    if event.type == "response.output_text.delta":
                        delta = event.delta if hasattr(event, "delta") else ""
                        if delta:
                            full_text += delta
                            yield json.dumps({"type": "delta", "content": delta})
                    elif event.type == "response.output_text.done":
                        # Some models send complete text in .done instead of deltas
                        text = getattr(event, "text", "")
                        if text and not full_text:
                            full_text = text
                            yield json.dumps({"type": "delta", "content": text})
                    elif event.type in ("response.completed", "response.done", "response.incomplete"):
                        # Extract citation annotations from the completed/incomplete response
                        citations = _extract_citations(event)
                        memories_used = _extract_memories_used(event)
                        print(f"[STREAM] {event.type}: {len(citations)} citations, {len(memories_used)} memories used")
                        if citations:
                            yield json.dumps({"type": "citations", "citations": citations})
                        if memories_used:
                            yield json.dumps({"type": "memories_used", "memories": memories_used})
                        yield json.dumps({"type": "done"})
                    else:
                        # Log other event types for debugging
                        print(f"[STREAM] event.type={event.type}")

            # Safety net: if stream ended without a terminal event, send done
            if full_text:
                chat["messages"].append({"role": "assistant", "content": full_text})
            yield json.dumps({"type": "done"})

        except Exception as e:
            yield json.dumps({"type": "error", "content": str(e)})

    return EventSourceResponse(event_stream())


# ── Fallback non-streaming endpoint ───────────────────────────────

@app.post("/api/chats/{chat_id}/messages/sync")
def send_message_sync(chat_id: str, req: MessageRequest):
    """Send a message and get the full response (non-streaming fallback)."""
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = chats[chat_id]
    foundry_id = chat["foundry_id"]

    chat["messages"].append({"role": "user", "content": req.message})

    if chat["title"] == "New Chat" and len(chat["messages"]) == 1:
        chat["title"] = req.message[:50] + ("..." if len(req.message) > 50 else "")

    response = openai_client.responses.create(
        conversation=foundry_id,
        extra_body={
            "agent_reference": {
                "name": AGENT_NAME,
                "type": "agent_reference",
            }
        },
        input=req.message,
    )

    assistant_text = response.output_text
    chat["messages"].append({"role": "assistant", "content": assistant_text})

    return {"role": "assistant", "content": assistant_text}


# ── Memory endpoints (Foundry Memory Store API) ──────────────────

@app.get("/api/memories", response_model=list[MemoryItem])
def list_memories():
    """List all agent memories for the current scope via search_memories."""
    try:
        # Search with no items returns static/user-profile memories for the scope
        search_response = project.beta.memory_stores.search_memories(
            name=MEMORY_STORE_NAME,
            scope=MEMORY_SCOPE,
        )
        return [
            MemoryItem(id=m.memory_item.memory_id, content=m.memory_item.content)
            for m in search_response.memories
        ]
    except Exception:
        return []


@app.delete("/api/memories")
def delete_all_memories():
    """Delete all memories for the current scope."""
    try:
        project.beta.memory_stores.delete_scope(
            name=MEMORY_STORE_NAME,
            scope=MEMORY_SCOPE,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





# ── Source viewer (SAS URL) ────────────────────────────────────────

def _generate_sas_url(blob_url: str, expiry_minutes: int = 15) -> str:
    """Generate a time-limited SAS URL for a blob storage document."""
    parsed = urlparse(blob_url)
    # Extract container and blob name from path: /container/blob.md
    path_parts = parsed.path.lstrip("/").split("/", 1)
    if len(path_parts) != 2:
        raise ValueError(f"Cannot parse blob path from: {blob_url}")
    container_name, blob_name = path_parts

    # Use DefaultAzureCredential to get a user delegation key
    blob_service = BlobServiceClient(
        account_url=f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )

    # Get user delegation key (valid for the SAS lifetime)
    start_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    expiry_time = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

    delegation_key = blob_service.get_user_delegation_key(
        key_start_time=start_time,
        key_expiry_time=expiry_time,
    )

    sas_token = generate_blob_sas(
        account_name=STORAGE_ACCOUNT_NAME,
        container_name=container_name,
        blob_name=blob_name,
        user_delegation_key=delegation_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry_time,
        start=start_time,
    )

    return f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"


@app.get("/api/source")
def get_source_content(url: str = Query(..., description="Blob URL to fetch content from")):
    """
    Fetch a source document's content via SAS and return it directly.
    This avoids CORS issues with the browser fetching from blob storage.
    """
    if "blob.core.windows.net" not in url:
        raise HTTPException(status_code=400, detail="Not a blob storage URL")
    try:
        sas_url = _generate_sas_url(url, expiry_minutes=5)
        import requests as http_requests
        resp = http_requests.get(sas_url, timeout=15)
        resp.raise_for_status()
        return {"content": resp.text, "url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Health check ───────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "agent": AGENT_NAME}
