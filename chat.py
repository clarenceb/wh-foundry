#!/usr/bin/env python3
"""
Western Health Patient Helper — simple chat demo.

Connects to a Foundry agent and lets you ask questions
about Western Health services, locations, and patient info.

Usage:
    python chat.py
"""

import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from opentelemetry import trace

# ── Load config from .env ──────────────────────────────────────────
load_dotenv()

# ── Tracing ───────────────────────────────────────────────────────
from tracing import configure_tracing, tracer
configure_tracing()

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
AGENT_NAME = os.environ["AGENT_NAME"]

# ── Connect to Foundry ─────────────────────────────────────────────
project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)
openai = project.get_openai_client()

# ── Start a conversation ───────────────────────────────────────────
with tracer.start_as_current_span("create_conversation") as span:
    conversation = openai.conversations.create()
    span.set_attribute("foundry.conversation_id", conversation.id)

GREEN = "\033[32m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"

BANNER = f"""{GREEN}{BOLD}
    ____        __  _            __     ________          __
   / __ \\____ _/ /_(_)__  ____  / /_   / ____/ /_  ____ _/ /_
  / /_/ / __ `/ __/ / _ \\/ __ \\/ __/  / /   / __ \\/ __ `/ __/
 / ____/ /_/ / /_/ /  __/ / / / /_   / /___/ / / / /_/ / /_
/_/    \\__,_/\\__/_/\\___/_/ /_/\\__/   \\____/_/ /_/\\__,_/\\__/
{RESET}{GREEN}
              Western Health Patient Services
{RESET}{DIM}
      Ask me anything about our services, locations,
       or visiting. Type "q", "quit" or "bye" to exit.
{RESET}"""

print(BANNER)

last_response_id = None

while True:
    user_input = input("You: ").strip()

    if not user_input:
        continue

    if user_input.lower() in ("q", "quit", "bye", "exit"):
        print("\nThank you for using Western Health Patient Helper. Goodbye! 👋\n")
        break

    # Send the question to the Foundry agent
    with tracer.start_as_current_span("agent_chat_turn") as span:
        span.set_attribute("user.message_length", len(user_input))
        span.set_attribute("agent.name", AGENT_NAME)

        response = openai.responses.create(
            conversation=conversation.id,
            extra_body={
                "agent_reference": {
                    "name": AGENT_NAME,
                    "type": "agent_reference",
                }
            },
            input=user_input,
        )

        span.set_attribute("assistant.response_length", len(response.output_text))

    print(f"\nAssistant: {response.output_text}\n")
