import { useState, useEffect } from 'react';
import { useChatStore } from '../stores/chatStore';
import ChatPanel from '../components/ChatPanel';
import styles from './EmbedPage.module.css';

export default function EmbedPage() {
  const { newChat } = useChatStore();
  const [chatId, setChatId] = useState<string | null>(null);

  useEffect(() => {
    const id = newChat();
    setChatId(id);
  }, [newChat]);

  if (!chatId) return null;

  return (
    <div className={styles.embedRoot}>
      <div className={styles.embedHeader}>🏥 Western Health Chat</div>
      <div className={styles.embedBody}>
        <ChatPanel chatId={chatId} compact />
      </div>
    </div>
  );
}
