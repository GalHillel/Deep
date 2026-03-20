/* Deep Platform — state.js (Reactive Store) */

class Store {
  constructor(initialState) {
    this.state = initialState;
    this.listeners = [];
  }

  get() {
    return this.state;
  }

  set(partial) {
    const oldState = { ...this.state };
    this.state = { ...this.state, ...partial };
    console.log('State Update:', partial);
    this.listeners.forEach(listener => listener(this.state, oldState));
  }

  subscribe(listener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }
}

const initialState = {
  // Navigation
  activeTab: 'graph',
  
  // Workspace / IDE
  tree: null,
  selectedFile: null,
  fileContent: '',
  isDirty: false,
  expandedFolders: new Set(['']),
  
  // Data
  commits: [],
  refs: {
    branches: {},
    current_branch: '',
    tags: {}
  },
  prs: [],
  selectedPR: null,
  issues: [],
  selectedIssue: null,
  work: {
    current_branch: '',
    staged_files: [],
    changed_files: [],
    active_pr: null,
    related_issue: null,
    sync: { ahead: 0, behind: 0, staged_count: 0, modified_count: 0 }
  },
  activity: [],
  
  // Instances
  monacoInstance: null,
  diffEditorInstance: null,
  networkInstance: null,
  
  // Flags
  graphLoaded: false,
  showingDiff: false,
  loading: false,
  error: null
};

window.store = new Store(initialState);
// Legacy compatibility
window.state = window.store.state; 

// Proxy window.state to the store to catch legacy direct mutations during transition
window.state = new Proxy(initialState, {
  get(target, prop) {
    return window.store.state[prop];
  },
  set(target, prop, value) {
    window.store.set({ [prop]: value });
    return true;
  }
});
