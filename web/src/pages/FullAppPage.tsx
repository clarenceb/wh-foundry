import { useState } from 'react';
import Sidebar from '../components/Sidebar';
import ChatPanel from '../components/ChatPanel';
import MemoryPanel from '../components/MemoryPanel';
import styles from './FullAppPage.module.css';

export default function FullAppPage() {
  const [memoryOpen, setMemoryOpen] = useState(false);

  return (
    <div className={styles.layout}>
      <Sidebar onOpenMemory={() => setMemoryOpen(true)} />
      <div className={styles.main}>
        <div className={styles.topBar}>
          Patient Chat — powered by Microsoft Foundry
        </div>
        <div className={styles.chatArea}>
          <ChatPanel />
        </div>
      </div>
      {memoryOpen && <MemoryPanel onClose={() => setMemoryOpen(false)} />}
    </div>
  );
}
