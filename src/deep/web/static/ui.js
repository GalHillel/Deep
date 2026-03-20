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
        if (state.activeTab === 'ide' && state.monacoInstance) {
          setTimeout(() => state.monacoInstance.layout(), 0);
        }
      }
      if (state.tree !== oldState.tree) this.renderFileTree();
      if (state.selectedFile !== oldState.selectedFile || state.isDirty !== oldState.isDirty) {
        this.renderEditorArea();
      }
      if (state.work !== oldState.work) this.renderWorkDashboard();
      if (state.refs !== oldState.refs) this.renderStatusBar();
      if (state.showingDiff !== oldState.showingDiff) this.updateDiffView();
    });
  },

  // ── Navigation ──────────────────────────────────────────
  switchTab(tabId) {
    window.store.set({ activeTab: tabId });
    if (tabId === 'prs') this.loadPRs();
    if (tabId === 'issues') this.loadIssues();
    if (tabId === 'work') this.loadWork();
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
  },

  // ── Git Graph ───────────────────────────────────────────
  async loadLog() {
    const container = document.getElementById('dag');
    if (!container) return;
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
      log.forEach(c => c.parents.forEach(p => edges.add({ from: c.sha, to: p, arrows: 'to', color: '#30363d' })));

      const options = {
        physics: { enabled: true, stabilization: { iterations: 120 } },
        layout: { hierarchical: { direction: 'LR', sortMethod: 'directed' } }
      };
      new vis.Network(container, { nodes, edges }, options);
    } catch (e) {}
  },

  // ── Dashboard / Work ────────────────────────────────────
  renderWorkDashboard() {
    const { work } = window.store.state;
    const branchName = document.getElementById('work-branch-name');
    const changedList = document.getElementById('work-changed-files');
    const syncInfo = document.getElementById('sync-info');

    if (branchName) branchName.textContent = work.current_branch || '...';
    if (syncInfo && work.sync) {
        syncInfo.innerHTML = `<span>↑${work.sync.ahead}</span> | <span>↓${work.sync.behind}</span>`;
    }

    if (changedList) {
        changedList.innerHTML = work.changed_files.length ? '' : '<p class="text-muted" style="padding:20px; text-align:center;">No changes detected. Working tree clean.</p>';
        work.changed_files.forEach(f => {
            const item = document.createElement('div');
            item.className = 'card';
            item.innerHTML = `
              <div class="card-title"><span style="color:var(--warning)">M</span> ${f}</div>
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
