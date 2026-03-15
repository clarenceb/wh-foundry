import { create } from 'zustand';
import type { Citation, MemoryUsed } from '../api';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  memoriesUsed?: MemoryUsed[];
  timestamp: number;
}

export interface Chat {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
}

interface ChatState {
  chats: Chat[];
  activeChatId: string | null;

  // Actions
  newChat: () => string;
  setActiveChat: (id: string) => void;
  deleteChat: (id: string) => void;
  addMessage: (chatId: string, role: 'user' | 'assistant', content: string) => string;
  appendToMessage: (chatId: string, messageId: string, chunk: string) => void;
  setCitations: (chatId: string, messageId: string, citations: Citation[]) => void;
  setMemoriesUsed: (chatId: string, messageId: string, memories: MemoryUsed[]) => void;
  getActiveChat: () => Chat | undefined;
}

let msgCounter = 0;
const makeId = () => `msg-${Date.now()}-${++msgCounter}`;
const makeChatId = () => `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

export const useChatStore = create<ChatState>((set, get) => ({
  chats: [],
  activeChatId: null,

  newChat: () => {
    const id = makeChatId();
    const chat: Chat = { id, title: 'New chat', messages: [], createdAt: Date.now() };
    set((s) => ({ chats: [chat, ...s.chats], activeChatId: id }));
    return id;
  },

  setActiveChat: (id) => set({ activeChatId: id }),

  deleteChat: (id) =>
    set((s) => {
      const chats = s.chats.filter((c) => c.id !== id);
      const activeChatId = s.activeChatId === id ? (chats[0]?.id || null) : s.activeChatId;
      return { chats, activeChatId };
    }),

  addMessage: (chatId, role, content) => {
    const msgId = makeId();
    set((s) => ({
      chats: s.chats.map((c) => {
        if (c.id !== chatId) return c;
        const msg: Message = { id: msgId, role, content, timestamp: Date.now() };
        let title = c.title;
        if (c.messages.length === 0 && role === 'user') {
          title = content.length > 40 ? content.slice(0, 40) + '…' : content;
        }
        return { ...c, title, messages: [...c.messages, msg] };
      }),
    }));
    return msgId;
  },

  appendToMessage: (chatId, messageId, chunk) =>
    set((s) => ({
      chats: s.chats.map((c) => {
        if (c.id !== chatId) return c;
        return {
          ...c,
          messages: c.messages.map((m) =>
            m.id === messageId ? { ...m, content: m.content + chunk } : m
          ),
        };
      }),
    })),

  setCitations: (chatId, messageId, citations) =>
    set((s) => ({
      chats: s.chats.map((c) => {
        if (c.id !== chatId) return c;
        return {
          ...c,
          messages: c.messages.map((m) =>
            m.id === messageId ? { ...m, citations } : m
          ),
        };
      }),
    })),

  setMemoriesUsed: (chatId, messageId, memoriesUsed) =>
    set((s) => ({
      chats: s.chats.map((c) => {
        if (c.id !== chatId) return c;
        return {
          ...c,
          messages: c.messages.map((m) =>
            m.id === messageId ? { ...m, memoriesUsed } : m
          ),
        };
      }),
    })),

  getActiveChat: () => {
    const { chats, activeChatId } = get();
    return chats.find((c) => c.id === activeChatId);
  },
}));
