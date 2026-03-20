/* Deep Platform — ui.js */

const UI = {
  // ── Initialization ──────────────────────────────────────
  init() {
    console.log("UI Initializing...");
    window.store.subscribe((state, oldState) => {
      this.handleStateChange(state, oldState);
    });
  },

  handleStateChange(state, oldState) {
    if (state.activeTab !== oldState.activeTab) this.renderTabChange(state.activeTab);
    if (state.tree !== oldState.tree) this.renderFileTree();
    if (state.prs !== oldState.prs) this.renderPRsList();
    if (state.issues !== oldState.issues) this.renderIssuesList();
    if (state.work !== oldState.work) this.renderWorkInfo();
    if (state.refs !== oldState.refs) this.renderRefsInfo();
    if (state.isDirty !== oldState.isDirty) this.updateCommitPanel();
  },

  switchTab(tabId) {
    if (window.store.state.activeTab === tabId && tabId !== 'ide') return;
    window.store.set({ activeTab: tabId });
    this.refreshCurrentTab();
  },

  renderTabChange(tabId) {
    // Update Sidebar
    document.querySelectorAll('.nav-item').forEach(item => {
      item.classList.toggle('active', item.dataset.tab === tabId);
    });
    
    // Update Topbar
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    
    // Update Content
    document.querySelectorAll('.tab-content').forEach(content => {
      content.classList.toggle('hidden', content.id !== `${tabId}-tab`);
    });
  },

  refreshCurrentTab() {
    const tabId = window.store.state.activeTab;
    if (tabId === 'graph') this.renderGraph();
    if (tabId === 'ide') this.renderIDE();
    // PRs and Issues are rendered via subscriptions now, but we can trigger refresh
    if (tabId === 'prs') this.loadPRs();
    if (tabId === 'issues') this.loadIssues();
    if (tabId === 'work') this.loadWork();
  },

  // ── Toasts ───────────────────────────────────────────────
  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
      toast.style.animation = 'toastOut .3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },

  // ── IDE / File Tree ──────────────────────────────────────
  renderIDE() {
    if (!window.store.state.tree) {
      this.loadTree();
    }
  },

  async loadTree() {
    try {
      const tree = await API.loadTree();
      window.store.set({ tree });
    } catch (e) {}
  },

  renderFileTree() {
    const container = document.getElementById('file-tree');
    container.innerHTML = '';
    const { tree, selectedFile } = window.store.state;
    if (!tree || !tree.children) return;
    
    const buildNodes = (nodes, parentEl, indent = 0) => {
      nodes.sort((a, b) => {
        if (a.type !== b.type) return (a.type === 'directory' || a.type === 'folder') ? -1 : 1;
        return a.name.localeCompare(b.name);
      }).forEach(node => {
        const item = document.createElement('div');
        item.className = 'tree-item';
        item.style.paddingLeft = `${indent * 12 + 10}px`;
        if (selectedFile === node.path) item.classList.add('selected');
        
        const isFolder = node.type === 'directory' || node.type === 'folder';
        const icon = isFolder ? '📁' : '📄';
        item.innerHTML = `<span>${icon}</span> <span class="truncate">${node.name}</span>`;
        
        item.onclick = (e) => {
          e.stopPropagation();
          if (isFolder) {
            // Folders could be toggled here
          } else {
            this.openFile(node.path);
          }
        };
        
        parentEl.appendChild(item);
        
        if (node.children && node.children.length > 0) {
          buildNodes(node.children, parentEl, indent + 1);
        }
      });
    };
    
    buildNodes(tree.children, container);
  },

  async openFile(path) {
    window.store.set({ selectedFile: path });
    
    try {
      const file = await API.loadFile(path);
      const { monacoInstance } = window.store.state;
      window.store.set({ fileContent: file.content, isDirty: false });
      
      if (!monacoInstance) {
        this.initMonaco(file.content, this.getLanguage(path));
      } else {
        monacoInstance.setValue(file.content);
        monaco.editor.setModelLanguage(monacoInstance.getModel(), this.getLanguage(path));
      }
    } catch (e) {}
  },

  initMonaco(content, lang) {
    const container = document.getElementById('monaco-container');
    const monacoInstance = monaco.editor.create(container, {
      value: content,
      language: lang,
      theme: 'vs-dark',
      automaticLayout: true,
      fontSize: 14,
      fontFamily: 'JetBrains Mono, Fira Code, monospace',
      minimap: { enabled: false },
      scrollbar: { vertical: 'hidden', horizontal: 'hidden' }
    });
    
    window.store.set({ monacoInstance });
    
    monacoInstance.onDidChangeModelContent(() => {
      const currentVal = monacoInstance.getValue();
      const isDirty = currentVal !== window.store.state.fileContent;
      window.store.set({ isDirty });
    });
  },

  getLanguage(path) {
    const ext = path.split('.').pop();
    const map = { js: 'javascript', py: 'python', html: 'html', css: 'css', md: 'markdown', json: 'json' };
    return map[ext] || 'plaintext';
  },

  updateCommitPanel() {
    const btn = document.getElementById('commit-btn');
    const { isDirty, selectedFile } = window.store.state;
    if (isDirty && selectedFile) {
      btn.classList.add('ready');
    } else {
      btn.classList.remove('ready');
    }
  },

  // ── PRs ──────────────────────────────────────────────────
  async loadPRs() {
    try {
      const prs = await API.loadPRs();
      window.store.set({ prs });
    } catch (e) {}
  },

  renderPRsList() {
    const container = document.getElementById('prs-list');
    const { prs } = window.store.state;
    container.innerHTML = '';
    
    if (prs.length === 0) {
      container.innerHTML = '<div class="empty-state">No pull requests found</div>';
      return;
    }
    
    prs.forEach(pr => {
      const card = document.createElement('div');
      card.className = 'card';
      card.innerHTML = `
        <div class="card-title">
          <span class="status-badge status-${pr.status}">${pr.status}</span>
          ${pr.title}
        </div>
        <div class="card-meta">
          <span>#${pr.id} by ${pr.author}</span>
          <span>${pr.head} → ${pr.base}</span>
        </div>
      `;
      card.onclick = () => this.showPRDetail(pr.id);
      container.appendChild(card);
    });
  },

  async showPRDetail(id) {
    const panel = document.getElementById('detail-panel');
    const header = document.getElementById('detail-header');
    const body = document.getElementById('detail-body');
    
    panel.classList.add('open');
    header.innerHTML = '<h2>Loading...</h2>';
    body.innerHTML = '<div class="skeleton"></div>';
    
    try {
      const pr = await API.loadPR(id);
      header.innerHTML = `
        <span id="detail-close" onclick="UI.hideDetail()">✕</span>
        <h2>${pr.title}</h2>
        <div class="detail-subtitle">#${pr.id} | ${pr.head} → ${pr.base}</div>
      `;
      
      body.innerHTML = `
        <div class="detail-section">
          <h4>Description</h4>
          <p>${pr.description || 'No description provided.'}</p>
        </div>
        <div class="action-bar">
          <button class="action-btn approve" onclick="UI.doPRAction(${pr.id}, 'approve')">Approve</button>
          <button class="action-btn merge" onclick="UI.doPRAction(${pr.id}, 'merge')">Merge</button>
        </div>
      `;
    } catch (e) {}
  },

  hideDetail() {
    document.getElementById('detail-panel').classList.remove('open');
  },

  // ── Work ─────────────────────────────────────────────────
  async loadWork() {
    try {
      const work = await API.loadWork();
      window.store.set({ work });
    } catch (e) {}
  },

  renderWorkInfo() {
    const { work } = window.store.state;
    document.getElementById('work-branch-name').textContent = work.current_branch;
    document.getElementById('stat-prs').textContent = work.open_prs;
    document.getElementById('stat-issues').textContent = work.open_issues;
    
    // Update Sync Metrics (from Phase 2 backend)
    const sync = work.sync || { ahead: 0, behind: 0, staged_count: 0, modified_count: 0 };
    const syncEl = document.getElementById('sync-info');
    if (syncEl) {
        syncEl.innerHTML = `
            <span title="Ahead">↑${sync.ahead}</span>
            <span title="Behind">↓${sync.behind}</span>
        `;
    }

    const changedList = document.getElementById('work-changed-files');
    changedList.innerHTML = work.changed_files.length ? '' : '<p class="text-muted">No changes</p>';
    work.changed_files.forEach(f => {
      const item = document.createElement('div');
      item.className = 'activity-item';
      item.innerHTML = `
        <span class="text-warning">M</span> 
        <span class="truncate" style="flex:1; margin-left:8px">${f}</span>
        <button class="action-btn" onclick="UI.addFile('${f}')">Stage</button>
      `;
      changedList.appendChild(item);
    });
  },

  async addFile(path) {
    // OPTIMISTIC UI: Remove from changed, add to staged in local state immediately
    const { work } = window.store.state;
    const newWork = {
      ...work,
      changed_files: work.changed_files.filter(f => f !== path),
      staged_files: [...work.staged_files, path]
    };
    window.store.set({ work: newWork });
    this.showToast(`Staging ${path}...`, 'info');

    try {
      await API.addFile(path);
      this.showToast(`Staged ${path}`, 'success');
      this.loadWork(); // Final sync with server
    } catch (e) {
      // Rollback on failure
      window.store.set({ work });
      this.showToast(`Failed to stage ${path}`, 'error');
    }
  },

  // ── Branch Management ───────────────────────────────────
  async renderRefsInfo() {
    const { refs } = window.store.state;
    document.getElementById('current-branch-name').textContent = refs.current_branch;
    
    const list = document.getElementById('branches-list');
    list.innerHTML = '';
    
    Object.keys(refs.branches || {}).forEach(name => {
      const item = document.createElement('div');
      item.className = 'tree-item';
      if (name === refs.current_branch) item.classList.add('selected');
      item.innerHTML = `<span>⑂</span> <span class="truncate">${name}</span>`;
      item.onclick = async () => {
        if (name === refs.current_branch) return;
        try {
          // OPTIMISTIC UI: Assume switch succeeds
          const oldRefs = { ...refs };
          window.store.set({ refs: { ...refs, current_branch: name } });
          
          await API.checkoutBranch(name);
          this.showToast(`Switched to ${name}`, 'success');
          this.loadRefs();
          this.loadTree();
        } catch (e) {
          window.store.set({ refs: oldState.refs }); // Rollback
        }
      };
      list.appendChild(item);
    });
  },

  async loadRefs() {
    try {
      const refs = await API.get('/api/refs');
      window.store.set({ refs });
    } catch (e) {}
  },

  promptNewBranch() {
    const name = prompt("Enter new branch name:");
    if (name) {
      API.createBranch(name).then(() => {
        this.showToast(`Branch ${name} created`, 'success');
        this.renderBranches();
      });
    }
  },

  // ── Git Graph ────────────────────────────────────────────
  async renderGraph() {
    if (state.graphLoaded) return;
    
    const container = document.getElementById('dag');
    try {
      const log = await API.loadLog();
      const nodes = new vis.DataSet(log.map(c => ({
        id: c.sha,
        label: c.sha.substring(0, 7),
        title: `${c.author}: ${c.message}`,
        color: { background: '#161b22', border: '#58a6ff' },
        font: { color: '#c9d1d9' }
      })));
      
      const edges = new vis.DataSet();
      log.forEach(c => {
        c.parents.forEach(p => {
          edges.add({ from: c.sha, to: p, arrows: 'to', color: '#30363d' });
        });
      });
      
      const options = {
        physics: { enabled: true, stabilization: { iterations: 120 } },
        layout: { hierarchical: { direction: 'LR', sortMethod: 'directed' } }
      };
      
      state.networkInstance = new vis.Network(container, { nodes, edges }, options);
      state.networkInstance.once("stabilizationIterationsDone", () => {
        state.networkInstance.setOptions({ physics: { enabled: false } });
      });
      
      state.graphLoaded = true;
    } catch (e) {}
  }
};

window.UI = UI;
