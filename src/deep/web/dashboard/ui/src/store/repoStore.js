import { create } from 'zustand';

export const useRepoStore = create((set) => ({
    currentRepo: null,
    setCurrentRepo: (repo) => set({ currentRepo: repo }),
    repos: [],
    setRepos: (repos) => set({ repos }),

    // Navigation state
    activeView: 'dashboard',
    setActiveView: (view) => set({ activeView: view }),

    // Selected item state (commit, file, etc)
    selectedCommit: null,
    setSelectedCommit: (sha) => set({ selectedCommit: sha }),
}));
