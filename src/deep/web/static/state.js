/* Deep Platform — state.js */

const state = {
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
    related_issue: null
  },
  activity: [],
  
  // Instances
  monacoInstance: null,
  networkInstance: null,
  
  // Flags
  graphLoaded: false,
  loading: false
};

// State Helpers
function updateState(key, value) {
  state[key] = value;
  // Trigger UI updates if needed (handled in ui.js)
  if (window.renderUI) window.renderUI(key);
}

window.state = state;
