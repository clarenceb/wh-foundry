import { useState, useEffect } from 'react';
import { useChatStore } from '../stores/chatStore';
import ChatPanel from './ChatPanel';
import styles from './ChatWidget.module.css';

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [widgetChatId, setWidgetChatId] = useState<string | null>(null);
  const { newChat } = useChatStore();

  useEffect(() => {
    if (open && !widgetChatId) {
      const id = newChat();
      setWidgetChatId(id);
    }
  }, [open, widgetChatId, newChat]);

  return (
    <div className={styles.widgetContainer}>
      {open && widgetChatId && (
        <div className={styles.chatWindow}>
          <div className={styles.chatHeader}>
            <h4>🏥 Western Health Chat</h4>
            <button onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className={styles.chatBody}>
            <ChatPanel chatId={widgetChatId} compact />
          </div>
        </div>
      )}
      <button className={styles.fab} onClick={() => setOpen(!open)}>
        {open ? '✕' : '💬'}
      </button>
    </div>
  );
}
