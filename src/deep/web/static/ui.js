/* Deep Platform — ui.js (Restored Dashboard Logic Fixed) */

const UI = {
  // ── Initialization ──────────────────────────────────────
  init() {
    console.log("UI Initializing...");
    this.subscribe();
    this.loadInitialData();
    // Initial render based on default state
    this.renderTabChange(window.store.state.activeTab);
  },

  loadInitialData() {
    this.loadTree();
    this.loadWork();
    this.loadRefs();
  },

  subscribe() {
    window.store.subscribe((state, oldState) => {
      if (state.activeTab !== oldState.activeTab) {
        this.renderTabChange(state.activeTab);
        // Refresh visibility-dependent components
        if (state.activeTab === 'graph') this.loadLog();
        if (state.activeTab === 'ide') {
            if (state.monacoInstance) {
                setTimeout(() => state.monacoInstance.layout(), 50);
            }
            if (state.diffEditorInstance) {
                setTimeout(() => state.diffEditorInstance.layout(), 50);
            }
        }
      }
      if (state.tree !== oldState.tree) this.renderFileTree();
      if (state.selectedFile !== oldState.selectedFile || state.isDirty !== oldState.isDirty) {
        this.renderEditorArea();
      }
      if (state.work !== oldState.work) {
          this.renderWorkDashboard();
          this.renderBranchSwitcher();
      }
      if (state.refs !== oldState.refs) {
          this.renderStatusBar();
          this.renderBranchSwitcher();
      }
      if (state.showingDiff !== oldState.showingDiff) this.updateDiffView();
    });
  },

  // ── Navigation ──────────────────────────────────────────
  switchTab(tabId) {
    window.store.set({ activeTab: tabId });
    if (tabId === 'prs') this.loadPRs();
    if (tabId === 'issues') this.loadIssues();
    if (tabId === 'work' || tabId === 'dashboard') this.loadWork();
  },

  renderTabChange(tabId) {
    if (!tabId) return;
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

  // ── IDE / Editor ───────────────────────────────────────
  renderFileTree() {
    const container = document.getElementById('file-tree');
    if (!container) return;
    container.innerHTML = '';
    const { tree, selectedFile } = window.store.state;
    if (!tree || !tree.children) {
      container.innerHTML = '<div style="padding:10px; font-size:11px; color:var(--text-muted)">Loading tree...</div>';
      return;
    }

    const buildNodes = (nodes, parentEl, indent = 0) => {
      nodes.sort((a, b) => {
        if (a.type !== b.type) return (a.type === 'directory' || a.type === 'folder') ? -1 : 1;
        return a.name.localeCompare(b.name);
      }).forEach(node => {
        const item = document.createElement('div');
        item.className = 'tree-item';
        item.style.paddingLeft = `${indent * 12 + 16}px`;
        if (selectedFile === node.path) item.classList.add('selected');

        const isFolder = node.type === 'directory' || node.type === 'folder';
        const icon = isFolder ? '📁' : '📄';
        item.innerHTML = `<span>${icon}</span> <span class="truncate">${node.name}</span>`;
        
        item.onclick = (e) => {
          e.stopPropagation();
          if (!isFolder) this.openFile(node.path);
        };
        
        parentEl.appendChild(item);
        if (node.children) buildNodes(node.children, parentEl, indent + 1);
      });
    };
    buildNodes(tree.children, container);
  },

  async openFile(path) {
    if (window.store.state.selectedFile === path && !window.store.state.loading) return;
    window.store.set({ selectedFile: path, loading: true });
    try {
      const file = await API.loadFile(path);
      window.store.set({ fileContent: file.content, isDirty: false, loading: false });
      this.initOrUpdateMonaco(file.content, path);
    } catch (e) {
      window.store.set({ loading: false });
    }
  },

  initOrUpdateMonaco(content, path) {
    const { monacoInstance } = window.store.state;
    const lang = this.getLanguage(path);
    if (!monacoInstance) {
      const container = document.getElementById('monaco-container');
      const editor = monaco.editor.create(container, {
        value: content,
        language: lang,
        theme: 'vs-dark',
        automaticLayout: true,
        fontSize: 14,
        minimap: { enabled: false }
      });
      window.store.set({ monacoInstance: editor });
      editor.onDidChangeModelContent(() => {
        const isDirty = editor.getValue() !== window.store.state.fileContent;
        window.store.set({ isDirty });
      });
    } else {
      monacoInstance.setValue(content);
      monaco.editor.setModelLanguage(monacoInstance.getModel(), lang);
    }
  },

  renderEditorArea() {
    const diffBtn = document.getElementById('diff-toggle-btn');
    const { isDirty } = window.store.state;
    if (diffBtn) diffBtn.classList.toggle('hidden', !isDirty);
    
    // Auto-layout on state change to prevent blank screens
    const { monacoInstance } = window.store.state;
    if (monacoInstance) {
        setTimeout(() => monacoInstance.layout(), 10);
    }
  },

  async createNewFile() {
    const name = prompt("Enter file name (relative path):");
    if (!name) return;
    try {
        const res = await API.createFile(name, "User");
        if (res.success) {
            this.showToast(res.message, 'success');
            await this.loadTree();
            this.openFile(name);
        } else {
            this.showToast(res.error, 'error');
        }
    } catch (e) {
        this.showToast("Failed to create file", 'error');
    }
  },

  async checkoutBranch(name) {
    if (!name) return;
    if (name === window.store.state.work.current_branch) return;
    
    this.showToast(`Checking out ${name}...`, 'info');
    try {
        const res = await API.checkoutBranch(name, "User");
        if (res.success) {
            this.showToast(res.message, 'success');
            await this.loadInitialData();
            this.loadLog();
        } else {
            this.showToast(res.error, 'error');
            // Revert selector
            this.renderBranchSwitcher();
        }
    } catch (e) {
        this.showToast("Checkout failed", 'error');
    }
  },

  renderBranchSwitcher() {
    const select = document.getElementById('branch-select');
    if (!select) return;
    const { refs, work } = window.store.state;
    if (!refs || !refs.branches) return;
    
    const current = work.current_branch || refs.current_branch;
    select.innerHTML = refs.branches.map(b => `<option value="${b}" ${b === current ? 'selected' : ''}>${b}</option>`).join('');
  },

  // ── Git Graph ───────────────────────────────────────────
  async loadLog() {
    const container = document.getElementById('dag');
    if (!container) return;
    try {
      const log = await API.loadLog();
      window.store.set({ log }); // Store log for detail lookup
      
      const nodes = new vis.DataSet(log.map(c => ({
        id: c.sha,
        label: c.sha.substring(0, 7),
        title: c.message,
        color: { 
            background: c.sha === window.store.state.refs.head_sha ? '#58a6ff' : '#161b22', 
            border: '#30363d' 
        },
        font: { color: '#c9d1d9' },
        shape: 'box',
        margin: 10
      })));
      const edges = new vis.DataSet();
      log.forEach(c => c.parents.forEach(p => edges.add({ from: c.sha, to: p, arrows: 'to', color: '#30363d' })));

      const options = {
        physics: { enabled: true, stabilization: { iterations: 120 } },
        layout: { hierarchical: { direction: 'RL', sortMethod: 'directed', levelSeparation: 150 } },
        interaction: { hover: true, tooltipDelay: 100 }
      };
      const network = new vis.Network(container, { nodes, edges }, options);
      
      network.on("click", (params) => {
        if (params.nodes.length > 0) {
            this.onCommitClick(params.nodes[0]);
        } else {
            this.hideGraphDetail();
        }
      });
    } catch (e) {
        console.error("Graph error", e);
    }
  },

  onCommitClick(sha) {
    const { log } = window.store.state;
    const commit = log.find(c => c.sha === sha);
    if (!commit) return;
    
    const detail = document.getElementById('graph-detail');
    const content = document.getElementById('graph-detail-content');
    if (!detail || !content) return;
    
    detail.classList.remove('hidden');
    content.innerHTML = `
        <span class="commit-label">SHA</span>
        <code>${commit.sha}</code>
        <span class="commit-label">AUTHOR</span>
        <div style="font-weight:600">${commit.author}</div>
        <div class="text-muted" style="font-size:11px">${commit.email}</div>
        <span class="commit-label">DATE</span>
        <div>${new Date(commit.timestamp * 1000).toLocaleString()}</div>
        <span class="commit-label">MESSAGE</span>
        <div style="font-size:14px; font-weight:600; margin-top:4px">${commit.message}</div>
        <div style="margin-top:20px">
            <button class="action-btn" onclick="UI.checkoutBranch('${commit.sha}')">Checkout Commit</button>
        </div>
    `;
  },

  hideGraphDetail() {
    const detail = document.getElementById('graph-detail');
    if (detail) detail.classList.add('hidden');
  },

  // ── Dashboard / Work ────────────────────────────────────
  renderWorkDashboard() {
    const { work, tree } = window.store.state;
    const branchName = document.getElementById('work-branch-name');
    const changedList = document.getElementById('work-changed-files');
    const syncInfo = document.getElementById('sync-info');

    if (branchName) branchName.textContent = work.current_branch || '...';
    if (syncInfo && work.sync) {
        syncInfo.innerHTML = `<span>↑${work.sync.ahead}</span> | <span>↓${work.sync.behind}</span>`;
    }

    // Render Stats
    const totalFiles = this.countFiles(tree);
    const statsContainer = document.querySelector('.work-stats');
    if (statsContainer) {
        statsContainer.innerHTML = `
            <div class="work-stat-card">
                <div class="stat-value">${totalFiles}</div>
                <div class="stat-label">Project Files</div>
            </div>
            <div class="work-stat-card">
                <div class="stat-value">${work.changed_files.length}</div>
                <div class="stat-label">Pending Changes</div>
            </div>
            <div class="work-stat-card">
                <div class="stat-value">${window.store.state.refs.branches ? window.store.state.refs.branches.length : 0}</div>
                <div class="stat-label">Local Branches</div>
            </div>
        `;
    }

    if (changedList) {
        changedList.innerHTML = work.changed_files.length ? '' : '<p class="text-muted" style="padding:20px; text-align:center;">No changes detected. Working tree clean.</p>';
        work.changed_files.forEach(f => {
            const item = document.createElement('div');
            item.className = 'card';
            item.innerHTML = `
              <div class="card-title"><span style="color:var(--orange)">M</span> ${f}</div>
              <div class="card-meta">Modified locally</div>
            `;
            item.onclick = () => {
              this.switchTab('ide');
              this.openFile(f);
            }
            changedList.appendChild(item);
        });
    }
  },

  countFiles(node) {
      if (!node) return 0;
      let count = node.type === 'file' ? 1 : 0;
      if (node.children) {
          node.children.forEach(c => count += this.countFiles(c));
      }
      return count;
  },

  renderStatusBar() {
    const { refs } = window.store.state;
    const branchInfo = document.getElementById('current-branch');
    if (branchInfo) branchInfo.textContent = refs.current_branch || 'main';
  },

  // ── Detail & Utils ──────────────────────────────────────
  hideDetail() { document.getElementById('detail-panel').classList.remove('open'); },
  toggleDiff() { window.store.set({ showingDiff: !window.store.state.showingDiff }); },

  async updateDiffView() {
    const { showingDiff } = window.store.state;
    const editorEl = document.getElementById('monaco-container');
    const diffEl = document.getElementById('diff-container');
    if (showingDiff) {
      editorEl.classList.add('hidden');
      diffEl.classList.remove('hidden');
      this.renderDiffEditor();
    } else {
      editorEl.classList.remove('hidden');
      diffEl.classList.add('hidden');
    }
  },

  async renderDiffEditor() {
    const { selectedFile, fileContent, monacoInstance } = window.store.state;
    let { diffEditorInstance } = window.store.state;
    const container = document.getElementById('diff-container');
    if (!diffEditorInstance) {
      diffEditorInstance = monaco.editor.createDiffEditor(container, { theme: 'vs-dark', automaticLayout: true, readOnly: true });
      window.store.set({ diffEditorInstance });
    }
    const lang = this.getLanguage(selectedFile);
    const originalModel = monaco.editor.createModel(fileContent, lang);
    const modifiedModel = monaco.editor.createModel(monacoInstance.getValue(), lang);
    diffEditorInstance.setModel({ original: originalModel, modified: modifiedModel });
  },

  async loadTree() { try { const tree = await API.loadTree(); window.store.set({ tree }); } catch(e){} },
  async loadWork() { try { const work = await API.loadWork(); window.store.set({ work }); } catch(e){} },
  async loadRefs() { try { const refs = await API.loadRefs(); window.store.set({ refs }); } catch(e){} },
  async loadPRs() { try { const prs = await API.loadPRs(); window.store.set({ prs }); } catch(e){} },
  async loadIssues() { try { const issues = await API.loadIssues(); window.store.set({ issues }); } catch(e){} },

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  },

  getLanguage(path) {
    if (!path) return 'plaintext';
    const ext = path.split('.').pop();
    const map = { js: 'javascript', py: 'python', html: 'html', css: 'css', md: 'markdown', json: 'json' };
    return map[ext] || 'plaintext';
  }
};

window.UI = UI;
