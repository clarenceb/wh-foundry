import { useState } from 'react';
import { useVoice } from '../hooks/useVoice';
import type { VoiceStatus } from '../hooks/useVoice';
import { useChatStore } from '../stores/chatStore';
import { createChat } from '../api';
import styles from './VoiceControls.module.css';

interface Props {
  chatId: string | null;
  language: string;
}

const STATUS_ICONS: Record<VoiceStatus, string> = {
  idle: '🎙️',
  connecting: '🎙️',
  active: '⏹️',
  error: '⚠️',
};

const STATUS_TITLES: Record<VoiceStatus, string> = {
  idle: 'Start voice mode',
  connecting: 'Connecting…',
  active: 'Stop voice mode',
  error: 'Voice error — click to retry',
};

const STATUS_MESSAGES: Record<VoiceStatus, string> = {
  idle: '',
  connecting: '🎙️ Connecting voice…',
  active: '🎙️ Voice mode active — speak now',
  error: '',
};

export default function VoiceControls({ chatId, language }: Props) {
  const [overrideChatId, setOverrideChatId] = useState<string | null>(null);
  const effectiveChatId = chatId || overrideChatId;

  const { status, start, stop, partialTranscript, error } = useVoice({
    chatId: effectiveChatId,
    language,
  });

  const handleClick = async () => {
    if (status === 'active') {
      console.log('[VOICE UI] Stopping voice mode');
      stop();
    } else {
      let cid = effectiveChatId;

      // Auto-create a chat if none exists
      if (!cid) {
        console.log('[VOICE UI] No chat — creating one...');
        const { newChat } = useChatStore.getState();
        cid = newChat();
        const serverChat = await createChat();
        useChatStore.setState((s) => ({
          chats: s.chats.map((c) =>
            c.id === cid ? { ...c, serverId: serverChat.chat_id } : c
          ),
        }));
        setOverrideChatId(cid);
      }

      console.log('[VOICE UI] Starting voice mode, chatId=', cid, 'lang=', language);
      // Pass the chatId directly to start() to avoid stale closure
      await start(cid);
    }
  };

  const buttonClass = {
    idle: styles.micIdle,
    connecting: styles.micConnecting,
    active: styles.micActive,
    error: styles.micError,
  }[status];

  return (
    <div className={styles.voiceControls}>
      <button
        className={`${styles.micButton} ${buttonClass}`}
        onClick={handleClick}
        disabled={status === 'connecting'}
        title={STATUS_TITLES[status]}
      >
        {STATUS_ICONS[status]}
      </button>

      {status === 'active' && <div className={`${styles.statusDot} ${styles.statusActive}`} />}

      {STATUS_MESSAGES[status] && (
        <span className={styles.statusMessage}>{STATUS_MESSAGES[status]}</span>
      )}

      {partialTranscript && (
        <span className={styles.partialTranscript}>{partialTranscript}</span>
      )}

      {error && status === 'error' && (
        <span className={styles.errorTooltip}>{error}</span>
      )}
    </div>
  );
}
