import { useState, useRef, useEffect } from 'react';
import Markdown from 'react-markdown';
import { useChatStore } from '../stores/chatStore';
import { createChat, streamMessage } from '../api';
import type { Citation } from '../api';
import SourceModal from './SourceModal';
import styles from './ChatPanel.module.css';

interface Props {
  chatId?: string;
  compact?: boolean;
}

/** Strip Foundry citation markers like 【7:2†source】 */
const stripCitations = (text: string) =>
  text.replace(/【[^】]*】/g, '');

export default function ChatPanel({ chatId: chatIdProp, compact }: Props) {
  const { activeChatId, newChat, addMessage, appendToMessage, setCitations } = useChatStore();
  const chats = useChatStore((s) => s.chats);
  const resolvedChatId = chatIdProp || activeChatId;
  const chat = chats.find((c) => c.id === resolvedChatId);

  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [expandedCitations, setExpandedCitations] = useState<Set<string>>(new Set());
  const [viewingSource, setViewingSource] = useState<Citation | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat?.messages]);

  const toggleCitations = (msgId: string) => {
    setExpandedCitations((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    let cid = resolvedChatId;

    if (!cid) {
      const serverChat = await createChat();
      cid = newChat();
      useChatStore.setState((s) => ({
        chats: s.chats.map((c) =>
          c.id === cid ? { ...c, serverId: serverChat.chat_id } : c
        ),
      }));
    }

    const chatState = useChatStore.getState().chats.find((c) => c.id === cid);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let serverId = (chatState as any)?.serverId;

    if (!serverId) {
      const serverChat = await createChat();
      serverId = serverChat.chat_id;
      useChatStore.setState((s) => ({
        chats: s.chats.map((c) =>
          c.id === cid ? { ...c, serverId } : c
        ),
      }));
    }

    addMessage(cid!, 'user', text);
    setInput('');
    setStreaming(true);

    const assistantMsgId = addMessage(cid!, 'assistant', '');

    await streamMessage(
      serverId,
      text,
      (chunk) => appendToMessage(cid!, assistantMsgId, chunk),
      (citations: Citation[]) => setCitations(cid!, assistantMsgId, citations),
      () => {},  // onMemoriesUsed — not displayed inline
      () => setStreaming(false),
      (err: string) => {
        appendToMessage(cid!, assistantMsgId, `\n\n⚠️ Error: ${err}`);
        setStreaming(false);
      },
    );
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const messages = chat?.messages || [];
  const isEmpty = messages.length === 0;

  return (
    <div className={styles.chatPanel}>
      <div className={styles.messages}>
        {isEmpty && !compact && (
          <div className={styles.emptyState}>
            <h2>🏥 Western Health</h2>
            <p>Ask me about our services, locations, visiting hours, or anything else.</p>
          </div>
        )}
        {isEmpty && compact && (
          <div className={styles.emptyState}>
            <p>How can I help you today?</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={msg.id}>
            <div
              className={`${styles.messageBubble} ${
                msg.role === 'user' ? styles.userBubble : styles.assistantBubble
              } ${
                msg.role === 'assistant' && streaming && i === messages.length - 1
                  ? styles.streaming
                  : ''
              }`}
            >
              {msg.role === 'user' ? (
                msg.content
              ) : (
                <Markdown>{stripCitations(msg.content)}</Markdown>
              )}
            </div>

            {/* Citations toggle — only for assistant messages with citations */}
            {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
              <div className={styles.citationsWrapper}>
                <button
                  className={styles.citationsToggle}
                  onClick={() => toggleCitations(msg.id)}
                >
                  {expandedCitations.has(msg.id) ? '▾ Hide sources' : '▸ Show sources'}
                  <span className={styles.citationCount}>({msg.citations.length})</span>
                </button>
                {expandedCitations.has(msg.id) && (
                  <ul className={styles.citationsList}>
                    {msg.citations.map((c, ci) => (
                      <li key={ci}>
                        <a
                          href="#"
                          onClick={(e) => {
                            e.preventDefault();
                            setViewingSource(c);
                          }}
                        >
                          📄 {c.title}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className={styles.inputBar}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your question…"
          disabled={streaming}
        />
        <button
          className={styles.sendBtn}
          onClick={handleSend}
          disabled={streaming || !input.trim()}
        >
          Send
        </button>
      </div>

      {viewingSource && (
        <SourceModal
          url={viewingSource.url}
          title={viewingSource.title}
          onClose={() => setViewingSource(null)}
        />
      )}
    </div>
  );
}
