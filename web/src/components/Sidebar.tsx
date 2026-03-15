import { Link } from 'react-router-dom';
import { useChatStore } from '../stores/chatStore';
import styles from './Sidebar.module.css';

interface Props {
  onOpenMemory: () => void;
  language: string;
  onLanguageChange: (lang: string) => void;
}

const LANGUAGES = [
  { code: 'en', label: '🇬🇧 English' },
  { code: 'vi', label: '🇻🇳 Vietnamese' },
  { code: 'el', label: '🇬🇷 Greek' },
  { code: 'zh', label: '🇨🇳 Mandarin' },
  { code: 'es', label: '🇪🇸 Spanish' },
  { code: 'it', label: '🇮🇹 Italian' },
];

export default function Sidebar({ onOpenMemory, language, onLanguageChange }: Props) {
  const { chats, activeChatId, newChat, setActiveChat, deleteChat } = useChatStore();

  return (
    <div className={styles.sidebar}>
      <div className={styles.header}>
        <div className={styles.logo}>
          🏥 <span>Western</span> Health
        </div>
        <button className={styles.newChatBtn} onClick={() => newChat()}>
          + New Chat
        </button>
      </div>

      <div className={styles.chatList}>
        {chats.map((chat) => (
          <button
            key={chat.id}
            className={`${styles.chatItem} ${chat.id === activeChatId ? styles.chatItemActive : ''}`}
            onClick={() => setActiveChat(chat.id)}
          >
            <span className={styles.chatTitle}>{chat.title}</span>
            <span
              className={styles.deleteBtn}
              onClick={(e) => {
                e.stopPropagation();
                deleteChat(chat.id);
              }}
            >
              ✕
            </span>
          </button>
        ))}
      </div>

      <div className={styles.footer}>
        <button className={styles.memoryBtn} onClick={onOpenMemory}>
          🧠 Memories
        </button>
        <select
          className={styles.langSelect}
          value={language}
          onChange={(e) => onLanguageChange(e.target.value)}
          title="Voice language"
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>{l.label}</option>
          ))}
        </select>
        <Link to="/widget" className={styles.widgetLink}>
          🌐 Widget Mode
        </Link>
      </div>
    </div>
  );
}
