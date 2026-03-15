import { useState } from 'react';
import Sidebar from '../components/Sidebar';
import ChatPanel from '../components/ChatPanel';
import MemoryPanel from '../components/MemoryPanel';
import styles from './FullAppPage.module.css';

export default function FullAppPage() {
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [language, setLanguage] = useState('en');

  return (
    <div className={styles.layout}>
      <Sidebar
        onOpenMemory={() => setMemoryOpen(true)}
        language={language}
        onLanguageChange={setLanguage}
      />
      <div className={styles.main}>
        <div className={styles.topBar}>
          Patient Chat — powered by Microsoft Foundry
        </div>
        <div className={styles.chatArea}>
          <ChatPanel language={language} />
        </div>
      </div>
      {memoryOpen && <MemoryPanel onClose={() => setMemoryOpen(false)} />}
    </div>
  );
}
