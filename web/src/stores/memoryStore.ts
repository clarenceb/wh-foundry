import { create } from 'zustand';
import { fetchMemories, deleteAllMemories } from '../api';
import type { Memory } from '../api';

interface MemoryState {
  memories: Memory[];
  loading: boolean;
  load: () => Promise<void>;
  clearAll: () => Promise<void>;
}

export const useMemoryStore = create<MemoryState>((set) => ({
  memories: [],
  loading: false,

  load: async () => {
    set({ loading: true });
    try {
      const memories = await fetchMemories();
      set({ memories, loading: false });
    } catch {
      set({ loading: false });
    }
  },

  clearAll: async () => {
    await deleteAllMemories();
    set({ memories: [] });
  },
}));
