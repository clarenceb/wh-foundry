import { useEffect } from 'react';
import { useMemoryStore } from '../stores/memoryStore';
import styles from './MemoryPanel.module.css';

interface Props {
  onClose: () => void;
}

export default function MemoryPanel({ onClose }: Props) {
  const { memories, loading, load, clearAll } = useMemoryStore();

  useEffect(() => { load(); }, [load]);

  const handleClear = async () => {
    if (window.confirm('Clear all memories for this scope? This cannot be undone.')) {
      await clearAll();
    }
  };

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.panel} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h3>🧠 Agent Memories</h3>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        <div className={styles.body}>
          {loading && <div className={styles.empty}>Loading…</div>}
          {!loading && memories.length === 0 && (
            <div className={styles.empty}>No memories stored yet.<br/>Chat with the agent and it will remember things about you.</div>
          )}
          {memories.map((m) => (
            <div key={m.id} className={styles.memoryItem}>
              <div className={styles.memoryContent}>{m.content}</div>
            </div>
          ))}
        </div>

        {memories.length > 0 && (
          <div className={styles.footer}>
            <button className={styles.clearAllBtn} onClick={handleClear}>
              Clear All Memories (scope)
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
