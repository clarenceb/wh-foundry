"""
Voice WebSocket proxy — bridges browser audio to Azure Voice Live.

Uses the azure-ai-voicelive SDK (v1.1.0) with the correct async API:
  - connect() → VoiceLiveConnection (async context manager)
  - connection.send(ClientEvent) to send audio/config
  - connection.recv() → ServerEvent to receive events
  - connection.recv_bytes() → bytes for raw audio

Protocol (browser ↔ this server):
  Browser → Server:
    - Binary frames: raw PCM16 audio from mic (24kHz mono)
    - Text frames: JSON control messages ({"type": "stop"})
  Server → Browser:
    - Binary frames: PCM16 audio for playback
    - Text frames: JSON transcript/status events
"""

import asyncio
import json
import os
import base64

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

# Voice Live endpoint
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
    """WebSocket endpoint for voice sessions."""
    await ws.accept()

    lang_config = LANGUAGES.get(lang, LANGUAGES["en"])
    print(f"[VOICE] Session started — lang={lang}, voice={lang_config['voice']}")

    await ws.send_text(json.dumps({
        "type": "session.started",
        "language": lang,
        "voice": lang_config["voice"],
    }))

    credential = AsyncDefaultAzureCredential()

    try:
        from azure.ai.voicelive.aio import connect
        from azure.ai.voicelive.models import (
            ClientEventInputAudioBufferAppend,
            ClientEventSessionUpdate,
            RequestSession,
            AzureStandardVoice,
            AzureSemanticVadMultilingual,
            AudioNoiseReduction,
            AudioEchoCancellation,
            AudioInputTranscriptionOptions,
            Modality,
            InputAudioFormat,
            OutputAudioFormat,
            ServerEventType,
        )

        # Connect with agent mode via query params
        async with connect(
            endpoint=VOICELIVE_ENDPOINT,
            credential=credential,
            api_version="2026-01-01-preview",
            # Agent mode: no model needed, agent provides it
            query={
                "agent_name": VOICE_AGENT_NAME,
                "project_name": PROJECT_NAME,
            },
        ) as connection:

            print(f"[VOICE] Connected to Voice Live (agent={VOICE_AGENT_NAME})")

            # Configure the session
            session_config = RequestSession(
                modalities=[Modality.TEXT, Modality.AUDIO],
                input_audio_format=InputAudioFormat.PCM16,
                output_audio_format=OutputAudioFormat.PCM16,
                voice=AzureStandardVoice(name=lang_config["voice"]),
                turn_detection=AzureSemanticVadMultilingual(),
                input_audio_transcription=AudioInputTranscriptionOptions(model="azure-speech"),
                input_audio_noise_reduction=AudioNoiseReduction(type="azure_deep_noise_suppression"),
                input_audio_echo_cancellation=AudioEchoCancellation(type="server_echo_cancellation"),
            )

            await connection.send(ClientEventSessionUpdate(session=session_config))
            print("[VOICE] Session configured")

            stop_event = asyncio.Event()

            async def browser_to_azure():
                """Forward mic audio from browser WebSocket to Voice Live."""
                try:
                    while not stop_event.is_set():
                        data = await ws.receive()
                        if "bytes" in data and data["bytes"]:
                            # Raw PCM16 audio → base64 encode for SDK
                            audio_b64 = base64.b64encode(data["bytes"]).decode("utf-8")
                            await connection.send(
                                ClientEventInputAudioBufferAppend(audio=audio_b64)
                            )
                        elif "text" in data and data["text"]:
                            msg = json.loads(data["text"])
                            if msg.get("type") == "stop":
                                print("[VOICE] Stop requested by client")
                                stop_event.set()
                                break
                except (WebSocketDisconnect, RuntimeError):
                    stop_event.set()
                except Exception as e:
                    print(f"[VOICE] browser_to_azure error: {e}")
                    stop_event.set()

            async def azure_to_browser():
                """Forward Voice Live events to browser WebSocket."""
                try:
                    while not stop_event.is_set():
                        try:
                            event = await asyncio.wait_for(connection.recv(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                        except Exception:
                            break

                        event_type = event.get("type", "")

                        # Audio response data
                        if event_type == "response.audio.delta":
                            delta = event.get("delta", "")
                            if delta:
                                audio_bytes = base64.b64decode(delta)
                                await ws.send_bytes(audio_bytes)

                        # User speech transcript (final)
                        elif event_type == "conversation.item.input_audio_transcription.completed":
                            transcript = event.get("transcript", "")
                            if transcript:
                                print(f"[VOICE] User said: {transcript[:80]}")
                                await ws.send_text(json.dumps({
                                    "type": "transcript.final",
                                    "role": "user",
                                    "text": transcript.strip(),
                                }))

                        # User speech transcript (partial/delta)
                        elif event_type == "conversation.item.input_audio_transcription.delta":
                            transcript = event.get("delta", "")
                            if transcript:
                                await ws.send_text(json.dumps({
                                    "type": "transcript.partial",
                                    "role": "user",
                                    "text": transcript,
                                }))

                        # Agent audio transcript done
                        elif event_type == "response.audio_transcript.done":
                            transcript = event.get("transcript", "")
                            if transcript:
                                print(f"[VOICE] Agent said: {transcript[:80]}")
                                await ws.send_text(json.dumps({
                                    "type": "response.final",
                                    "role": "assistant",
                                    "text": transcript.strip(),
                                }))

                        # Agent audio transcript streaming
                        elif event_type == "response.audio_transcript.delta":
                            delta = event.get("delta", "")
                            if delta:
                                await ws.send_text(json.dumps({
                                    "type": "response.delta",
                                    "role": "assistant",
                                    "text": delta,
                                }))

                        # User started speaking (barge-in)
                        elif event_type == "input_audio_buffer.speech_started":
                            print("[VOICE] Barge-in detected")
                            await ws.send_text(json.dumps({
                                "type": "barge_in",
                            }))

                        # Response complete
                        elif event_type == "response.done":
                            await ws.send_text(json.dumps({
                                "type": "response.done",
                            }))

                        # Session created/updated
                        elif event_type in ("session.created", "session.updated"):
                            print(f"[VOICE] {event_type}")

                        # Error
                        elif event_type == "error":
                            error_data = event.get("error", {})
                            print(f"[VOICE] Error: {error_data}")
                            await ws.send_text(json.dumps({
                                "type": "error",
                                "message": str(error_data),
                            }))

                except (WebSocketDisconnect, RuntimeError):
                    stop_event.set()
                except Exception as e:
                    print(f"[VOICE] azure_to_browser error: {e}")
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
