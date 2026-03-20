/* ⚓ Deep V3 — state.js (Single Source of Truth) */

class Store {
    constructor() {
        this.state = {
            // App Shell
            activeTab: 'work',
            loading: false,
            
            // Editor State
            tree: null,
            selectedFile: null,
            openTabs: [],
            fileContent: '',
            isDirty: false,
            expandedFolders: new Set(['/']),
            monacoInstance: null,
            diffEditorInstance: null,
            showingDiff: false,
            
            // Git Data
            work: { current_branch: '...', changed_files: [] },
            refs: { branches: [], current_branch: '...', head: null },
            log: [],
            
            // Collaboration
            prs: [],
            issues: [],
            
            // UI Flags
            sidebarWidth: 260,
            rightPanelOpen: false
        };
        this.listeners = [];
    }

    get() {
        return this.state;
    }

    set(update) {
        const oldState = { ...this.state };
        this.state = { ...this.state, ...update };
        console.log("⚓ State Update:", update);
        this.listeners.forEach(fn => fn(this.state, oldState));
    }

    subscribe(fn) {
        this.listeners.push(fn);
        return () => { this.listeners = this.listeners.filter(l => l !== fn); };
    }
}

window.store = new Store();

// Legacy compatibility shim
window.state = new Proxy(window.store.state, {
    get(target, prop) { return window.store.state[prop]; },
    set(target, prop, value) {
        window.store.set({ [prop]: value });
        return true;
    }
});
