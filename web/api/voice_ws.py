"""
Voice WebSocket proxy — bridges browser audio to Azure Voice Live.

The browser connects via WebSocket, sends PCM16 audio chunks (24kHz mono),
and receives audio responses + transcripts from the Foundry voice agent.

Protocol:
  Browser → Server:
    - Binary frames: raw PCM16 audio from mic
    - Text frames: JSON control messages ({"type": "stop"})

  Server → Browser:
    - Binary frames: PCM16 audio for playback
    - Text frames: JSON transcript/status events
"""

import asyncio
import json
import os
import base64
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from azure.identity.aio import DefaultAzureCredential as AsyncDefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# ── Config ─────────────────────────────────────────────────────────

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
VOICE_AGENT_NAME = os.environ.get("VOICE_AGENT_NAME", "wh-patient-helper-voice")

# Extract resource name and project name from endpoint
# Format: https://<resource>.services.ai.azure.com/api/projects/<project>
_parts = PROJECT_ENDPOINT.replace("https://", "").split("/")
RESOURCE_NAME = _parts[0].split(".")[0]
PROJECT_NAME = _parts[-1] if len(_parts) > 1 else "mydemos"

# Voice Live endpoint (uses cognitiveservices subdomain)
VOICELIVE_ENDPOINT = os.environ.get(
    "VOICELIVE_ENDPOINT",
    f"https://{RESOURCE_NAME}.cognitiveservices.azure.com",
)

# ── Language configuration ─────────────────────────────────────────

LANGUAGES = {
    "en": {"voice": "en-US-Ava:DragonHDLatestNeural", "locale": "en-US", "label": "English"},
    "vi": {"voice": "vi-VN-HoaiMyNeural", "locale": "vi-VN", "label": "Vietnamese"},
    "el": {"voice": "el-GR-AthinaNeural", "locale": "el-GR", "label": "Greek"},
    "zh": {"voice": "zh-CN-XiaoxiaoNeural", "locale": "zh-CN", "label": "Mandarin"},
    "es": {"voice": "es-ES-ElviraNeural", "locale": "es-ES", "label": "Spanish"},
    "it": {"voice": "it-IT-ElsaNeural", "locale": "it-IT", "label": "Italian"},
}


@router.get("/api/voice/languages")
def list_languages():
    """List supported voice languages."""
    return [
        {"code": code, "label": cfg["label"], "voice": cfg["voice"]}
        for code, cfg in LANGUAGES.items()
    ]


@router.websocket("/api/voice")
async def voice_session(ws: WebSocket, lang: str = Query("en")):
    """
    WebSocket endpoint for voice sessions.

    Query params:
        lang: Language code (en, vi, el, zh, es, it)
    """
    await ws.accept()

    lang_config = LANGUAGES.get(lang, LANGUAGES["en"])
    print(f"[VOICE] Session started — lang={lang}, voice={lang_config['voice']}")

    # Send session info to client
    await ws.send_text(json.dumps({
        "type": "session.started",
        "language": lang,
        "voice": lang_config["voice"],
    }))

    credential = AsyncDefaultAzureCredential()

    try:
        # Import Voice Live SDK
        from azure.ai.voicelive.aio import VoiceLiveClient

        # Create Voice Live client with agent mode
        client = VoiceLiveClient(
            endpoint=VOICELIVE_ENDPOINT,
            credential=credential,
            api_version="2026-01-01-preview",
        )

        # Connect with agent configuration
        async with client.connect(
            agent_name=VOICE_AGENT_NAME,
            project_name=PROJECT_NAME,
            voice=lang_config["voice"],
            input_audio_transcription={"model": "azure-speech"},
            turn_detection={
                "type": "azure_semantic_vad",
                "end_of_utterance_detection": {
                    "model": "semantic_detection_v1_multilingual"
                },
            },
            input_audio_noise_reduction={"type": "azure_deep_noise_suppression"},
            input_audio_echo_cancellation={"type": "server_echo_cancellation"},
        ) as connection:

            stop_event = asyncio.Event()

            async def browser_to_azure():
                """Forward mic audio from browser to Voice Live."""
                try:
                    while not stop_event.is_set():
                        data = await ws.receive()
                        if "bytes" in data:
                            # Raw PCM16 audio → base64 encode for SDK
                            audio_b64 = base64.b64encode(data["bytes"]).decode("utf-8")
                            await connection.input_audio_buffer.append(audio=audio_b64)
                        elif "text" in data:
                            msg = json.loads(data["text"])
                            if msg.get("type") == "stop":
                                stop_event.set()
                                break
                except (WebSocketDisconnect, RuntimeError):
                    stop_event.set()

            async def azure_to_browser():
                """Forward Voice Live events to browser."""
                try:
                    async for event in connection:
                        if stop_event.is_set():
                            break

                        event_type = getattr(event, "type", "")

                        # Audio response data
                        if event_type == "response.audio.delta":
                            delta = getattr(event, "delta", "")
                            if delta:
                                audio_bytes = base64.b64decode(delta)
                                await ws.send_bytes(audio_bytes)

                        # User speech transcript (final)
                        elif event_type == "conversation.item.input_audio_transcription.completed":
                            transcript = getattr(event, "transcript", "")
                            if transcript:
                                await ws.send_text(json.dumps({
                                    "type": "transcript.final",
                                    "role": "user",
                                    "text": transcript.strip(),
                                }))

                        # Agent text response done
                        elif event_type == "response.audio_transcript.done":
                            transcript = getattr(event, "transcript", "")
                            if transcript:
                                await ws.send_text(json.dumps({
                                    "type": "response.final",
                                    "role": "assistant",
                                    "text": transcript.strip(),
                                }))

                        # Agent text response streaming
                        elif event_type == "response.audio_transcript.delta":
                            delta = getattr(event, "delta", "")
                            if delta:
                                await ws.send_text(json.dumps({
                                    "type": "response.delta",
                                    "role": "assistant",
                                    "text": delta,
                                }))

                        # User started speaking (barge-in)
                        elif event_type == "input_audio_buffer.speech_started":
                            await ws.send_text(json.dumps({
                                "type": "barge_in",
                            }))

                        # Response complete
                        elif event_type == "response.done":
                            await ws.send_text(json.dumps({
                                "type": "response.done",
                            }))

                        # Error
                        elif event_type == "error":
                            error_msg = getattr(event, "error", {})
                            print(f"[VOICE] Error: {error_msg}")
                            await ws.send_text(json.dumps({
                                "type": "error",
                                "message": str(error_msg),
                            }))

                except (WebSocketDisconnect, RuntimeError):
                    stop_event.set()

            # Run both directions concurrently
            await asyncio.gather(
                browser_to_azure(),
                azure_to_browser(),
                return_exceptions=True,
            )

    except Exception as e:
        print(f"[VOICE] Session error: {e}")
        try:
            await ws.send_text(json.dumps({
                "type": "error",
                "message": str(e),
            }))
        except Exception:
            pass
    finally:
        await credential.close()
        print("[VOICE] Session ended")
        try:
            await ws.close()
        except Exception:
            pass
