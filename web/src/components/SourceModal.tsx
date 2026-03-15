import { useState, useEffect } from 'react';
import Markdown from 'react-markdown';
import { getSourceContent } from '../api';
import styles from './SourceModal.module.css';

interface Props {
  url: string;
  title: string;
  onClose: () => void;
}

export default function SourceModal({ url, title, onClose }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSourceContent(url)
      .then((text) => { if (!cancelled) setContent(text); })
      .catch((e) => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [url]);

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
          <h4>📄 {title}</h4>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>
        <div className={styles.body}>
          {!content && !error && <div className={styles.loading}>Loading document…</div>}
          {error && <div className={styles.error}>⚠️ {error}</div>}
          {content && (
            <div className={styles.markdownContent}>
              <Markdown>{content}</Markdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
