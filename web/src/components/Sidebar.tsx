import { Link } from 'react-router-dom';
import { useChatStore } from '../stores/chatStore';
import styles from './Sidebar.module.css';

interface Props {
  onOpenMemory: () => void;
}

export default function Sidebar({ onOpenMemory }: Props) {
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
        <Link to="/widget" className={styles.widgetLink}>
          🌐 Widget Mode
        </Link>
      </div>
    </div>
  );
}
