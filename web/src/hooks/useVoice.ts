import { useRef, useState, useCallback, useEffect } from 'react';
import { useChatStore } from '../stores/chatStore';

export type VoiceStatus = 'idle' | 'connecting' | 'active' | 'error';

const SAMPLE_RATE = 24000;

function getVoiceWsUrl(): string {
  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  return apiBase.replace(/^http/, 'ws');
}

interface UseVoiceOptions {
  chatId: string | null;
  language: string;
}

interface UseVoiceReturn {
  status: VoiceStatus;
  start: (overrideChatId?: string) => Promise<void>;
  stop: () => void;
  partialTranscript: string;
  error: string | null;
}

export function useVoice({ chatId, language }: UseVoiceOptions): UseVoiceReturn {
  const [status, setStatus] = useState<VoiceStatus>('idle');
  const [partialTranscript, setPartialTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const playbackNodeRef = useRef<AudioWorkletNode | null>(null);
  const assistantMsgIdRef = useRef<string | null>(null);
  const assistantTextRef = useRef('');
  const activeChatIdRef = useRef<string | null>(chatId);

  // Keep the ref in sync
  activeChatIdRef.current = chatId;

  const { addMessage, replaceMessageContent } = useChatStore();

  const cleanup = useCallback(() => {
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* ignore */ }
      wsRef.current = null;
    }
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close(); } catch { /* ignore */ }
      audioCtxRef.current = null;
    }
    playbackNodeRef.current = null;
    assistantMsgIdRef.current = null;
    assistantTextRef.current = '';
  }, []);

  const stop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'stop' }));
    }
    cleanup();
    setStatus('idle');
    setPartialTranscript('');
    setError(null);
  }, [cleanup]);

  const start = useCallback(async (overrideChatId?: string) => {
    const effectiveId = overrideChatId || chatId;
    if (!effectiveId) {
      console.warn('[VOICE] No chatId — cannot start voice session');
      setError('No active chat');
      setStatus('error');
      return;
    }
    // Update the ref so handleEvent uses the right chatId
    activeChatIdRef.current = effectiveId;
    console.log('[VOICE] Starting voice session, chatId=', effectiveId, 'lang=', language);
    setStatus('connecting');
    setError(null);
    setPartialTranscript('');

    try {
      // 1. Get mic permission
      console.log('[VOICE] Requesting mic permission...');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      micStreamRef.current = stream;
      console.log('[VOICE] Mic granted, sampleRate=', stream.getAudioTracks()[0]?.getSettings().sampleRate);

      // 2. Create AudioContext at 24kHz
      const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioCtxRef.current = audioCtx;
      console.log('[VOICE] AudioContext created, sampleRate=', audioCtx.sampleRate);

      // 3. Load worklets
      await audioCtx.audioWorklet.addModule('/mic-processor.js');
      await audioCtx.audioWorklet.addModule('/playback-processor.js');
      console.log('[VOICE] AudioWorklets loaded');

      // 4. Mic capture pipeline
      const micSource = audioCtx.createMediaStreamSource(stream);
      const micNode = new AudioWorkletNode(audioCtx, 'mic-processor');
      micSource.connect(micNode);
      // Don't connect mic to destination (would cause echo)

      // 5. Playback pipeline
      const playbackNode = new AudioWorkletNode(audioCtx, 'playback-processor');
      playbackNode.connect(audioCtx.destination);
      playbackNodeRef.current = playbackNode;

      // 6. Open WebSocket
      const wsUrl = `${getVoiceWsUrl()}/api/voice?lang=${language}`;
      console.log('[VOICE] Opening WebSocket:', wsUrl);
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[VOICE] WebSocket connected');
        setStatus('active');
      };

      // 7. Mic → WebSocket: forward captured PCM16 to server
      micNode.port.onmessage = (e: MessageEvent) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(e.data as ArrayBuffer);
        }
      };

      // 8. WebSocket → playback + transcripts
      ws.onmessage = (e: MessageEvent) => {
        if (e.data instanceof ArrayBuffer) {
          // Binary audio → playback worklet
          console.log('[VOICE] Received audio chunk:', e.data.byteLength, 'bytes');
          playbackNode.port.postMessage(e.data, [e.data]);
        } else {
          // JSON text frame → transcript
          try {
            const msg = JSON.parse(e.data as string);
            console.log('[VOICE] Received event:', msg.type, msg.text?.substring(0, 50) || '');
            handleEvent(msg);
          } catch {
            // ignore non-JSON
          }
        }
      };

      ws.onerror = (ev) => {
        console.error('[VOICE] WebSocket error:', ev);
        setError('Voice connection error');
        setStatus('error');
      };

      ws.onclose = (ev) => {
        console.log('[VOICE] WebSocket closed:', ev.code, ev.reason);
        if (status !== 'idle') {
          cleanup();
          setStatus('idle');
        }
      };
    } catch (err) {
      console.error('[VOICE] Start failed:', err);
      setError(err instanceof Error ? err.message : 'Failed to start voice');
      setStatus('error');
      cleanup();
    }
  }, [chatId, language, cleanup, status]);

  const handleEvent = useCallback(
    (msg: { type: string; role?: string; text?: string; message?: string }) => {
      const cid = activeChatIdRef.current;
      if (!cid) return;

      switch (msg.type) {
        case 'transcript.final':
          setPartialTranscript('');
          if (msg.text) {
            addMessage(cid, 'user', msg.text);
          }
          break;

        case 'response.delta':
          if (msg.text) {
            assistantTextRef.current += msg.text;
            if (!assistantMsgIdRef.current) {
              assistantMsgIdRef.current = addMessage(cid, 'assistant', assistantTextRef.current);
            } else {
              replaceMessageContent(cid, assistantMsgIdRef.current, assistantTextRef.current);
            }
          }
          break;

        case 'response.final':
          if (msg.text) {
            if (assistantMsgIdRef.current) {
              replaceMessageContent(cid, assistantMsgIdRef.current, msg.text);
            } else {
              addMessage(cid, 'assistant', msg.text);
            }
          }
          assistantMsgIdRef.current = null;
          assistantTextRef.current = '';
          break;

        case 'response.done':
          // Response complete — reset for next turn
          assistantMsgIdRef.current = null;
          assistantTextRef.current = '';
          break;

        case 'barge_in':
          // User interrupted — flush audio playback
          if (playbackNodeRef.current) {
            playbackNodeRef.current.port.postMessage('flush');
          }
          // Clear partial assistant message
          assistantMsgIdRef.current = null;
          assistantTextRef.current = '';
          break;

        case 'error':
          setError(msg.message || 'Voice error');
          setStatus('error');
          break;
      }
    },
    [chatId, addMessage, replaceMessageContent],
  );

  // Cleanup on unmount
  useEffect(() => () => cleanup(), [cleanup]);

  return { status, start, stop, partialTranscript, error };
}
