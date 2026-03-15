import { useVoice } from '../hooks/useVoice';
import type { VoiceStatus } from '../hooks/useVoice';
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

export default function VoiceControls({ chatId, language }: Props) {
  const { status, start, stop, partialTranscript, error } = useVoice({
    chatId,
    language,
  });

  const handleClick = async () => {
    if (status === 'active') {
      stop();
    } else {
      await start();
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

      {partialTranscript && (
        <span className={styles.partialTranscript}>{partialTranscript}</span>
      )}

      {error && status === 'error' && (
        <span className={styles.errorTooltip}>{error}</span>
      )}
    </div>
  );
}
