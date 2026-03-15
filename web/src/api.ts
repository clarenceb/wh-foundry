const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ── Chat API ──────────────────────────────────────────────────────

export interface ChatCreateResponse {
  chat_id: string;
  title: string;
}

export async function createChat(): Promise<ChatCreateResponse> {
  const res = await fetch(`${API}/api/chats`, { method: 'POST' });
  return res.json();
}

export async function deleteServerChat(chatId: string): Promise<void> {
  await fetch(`${API}/api/chats/${chatId}`, { method: 'DELETE' });
}

export interface Citation {
  url: string;
  title: string;
}

/**
 * Send a message and stream the response via SSE.
 * Calls onDelta for each text chunk, onCitations when sources arrive,
 * onDone when complete, onError on failure.
 */
export async function streamMessage(
  chatId: string,
  message: string,
  onDelta: (text: string) => void,
  onCitations: (citations: Citation[]) => void,
  onDone: () => void,
  onError: (err: string) => void,
) {
  try {
    const res = await fetch(`${API}/api/chats/${chatId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });

    if (!res.ok) {
      onError(`Server error: ${res.status}`);
      return;
    }

    const reader = res.body?.getReader();
    if (!reader) { onError('No response stream'); return; }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith(':')) continue; // SSE comment/keep-alive
        if (trimmed.startsWith('data: ')) {
          try {
            const payload = JSON.parse(trimmed.slice(6));
            if (payload.type === 'delta' && payload.content) {
              onDelta(payload.content);
            } else if (payload.type === 'citations' && payload.citations) {
              onCitations(payload.citations);
            } else if (payload.type === 'done') {
              onDone();
              return;
            } else if (payload.type === 'error') {
              onError(payload.content || 'Unknown error');
              return;
            }
          } catch {
            // non-JSON data line, skip
          }
        }
      }
    }
    onDone();
  } catch (e) {
    onError(e instanceof Error ? e.message : 'Unknown error');
  }
}

/** Non-streaming fallback */
export async function sendMessageSync(
  chatId: string,
  message: string,
): Promise<string> {
  const res = await fetch(`${API}/api/chats/${chatId}/messages/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
  const data = await res.json();
  return data.content;
}

// ── Memory API ────────────────────────────────────────────────────

export interface Memory {
  id: string;
  content: string;
}

export async function fetchMemories(): Promise<Memory[]> {
  const res = await fetch(`${API}/api/memories`);
  if (!res.ok) return [];
  return res.json();
}

export async function deleteAllMemories(): Promise<void> {
  await fetch(`${API}/api/memories`, { method: 'DELETE' });
}

// ── Source viewer (SAS URL) ───────────────────────────────────────

/** Fetch the rendered content of a source document via the backend proxy */
export async function getSourceContent(blobUrl: string): Promise<string> {
  const res = await fetch(`${API}/api/source?url=${encodeURIComponent(blobUrl)}`);
  if (!res.ok) throw new Error(`Failed to fetch source: ${res.status}`);
  const data = await res.json();
  return data.content;
}
