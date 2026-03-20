/* Deep Platform — ui.js */

const UI = {
  // ── Navigation ───────────────────────────────────────────
  switchTab(tabId) {
    if (state.activeTab === tabId && tabId !== 'ide') return;
    
    // Update State
    state.activeTab = tabId;
    
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
    
    // Trigger specific tab loads
    this.refreshCurrentTab();
  },

  refreshCurrentTab() {
    const tabId = state.activeTab;
    if (tabId === 'graph') this.renderGraph();
    if (tabId === 'ide') this.renderIDE();
    if (tabId === 'prs') this.renderPRs();
    if (tabId === 'issues') this.renderIssues();
    if (tabId === 'work') this.renderWork();
    this.renderBranches();
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
    if (!state.tree) {
      this.loadTree();
    }
  },

  async loadTree() {
    try {
      state.tree = await API.loadTree();
      this.renderFileTree();
    } catch (e) { /* Error handled in API.request */ }
  },

  renderFileTree() {
    const container = document.getElementById('file-tree');
    container.innerHTML = '';
    if (!state.tree || !state.tree.children) return;
    
    const buildNodes = (nodes, parentEl, indent = 0) => {
      nodes.sort((a, b) => {
        if (a.type !== b.type) return a.type === 'directory' || a.type === 'folder' ? -1 : 1;
        return a.name.localeCompare(b.name);
      }).forEach(node => {
        const item = document.createElement('div');
        item.className = 'tree-item';
        item.style.paddingLeft = `${indent * 12 + 10}px`;
        if (state.selectedFile === node.path) item.classList.add('selected');
        
        const isFolder = node.type === 'directory' || node.type === 'folder';
        const icon = isFolder ? '📁' : '📄';
        item.innerHTML = `<span>${icon}</span> <span class="truncate">${node.name}</span>`;
        
        item.onclick = (e) => {
          e.stopPropagation();
          if (isFolder) {
            // In this simple version, we don't collapse, but we could
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
    
    buildNodes(state.tree.children, container);
  },

  async openFile(path) {
    state.selectedFile = path;
    this.renderFileTree(); // Highlight selected
    
    try {
      const file = await API.loadFile(path);
      state.fileContent = file.content;
      state.isDirty = false;
      
      if (!state.monacoInstance) {
        this.initMonaco(file.content, this.getLanguage(path));
      } else {
        state.monacoInstance.setValue(file.content);
        monaco.editor.setModelLanguage(state.monacoInstance.getModel(), this.getLanguage(path));
      }
      
      this.updateCommitPanel();
    } catch (e) {}
  },

  initMonaco(content, lang) {
    const container = document.getElementById('monaco-container');
    state.monacoInstance = monaco.editor.create(container, {
      value: content,
      language: lang,
      theme: 'vs-dark',
      automaticLayout: true,
      fontSize: 14,
      fontFamily: 'JetBrains Mono, Fira Code, monospace',
      minimap: { enabled: false },
      scrollbar: { vertical: 'hidden', horizontal: 'hidden' }
    });
    
    state.monacoInstance.onDidChangeModelContent(() => {
      state.isDirty = state.monacoInstance.getValue() !== state.fileContent;
      this.updateCommitPanel();
    });
  },

  getLanguage(path) {
    const ext = path.split('.').pop();
    const map = { js: 'javascript', py: 'python', html: 'html', css: 'css', md: 'markdown', json: 'json' };
    return map[ext] || 'plaintext';
  },

  updateCommitPanel() {
    const btn = document.getElementById('commit-btn');
    if (state.isDirty && state.selectedFile) {
      btn.classList.add('ready');
    } else {
      btn.classList.remove('ready');
    }
  },

  // ── PRs ──────────────────────────────────────────────────
  async renderPRs() {
    const container = document.getElementById('prs-list');
    container.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
    
    try {
      state.prs = await API.loadPRs();
      container.innerHTML = '';
      if (state.prs.length === 0) {
        container.innerHTML = '<div class="empty-state">No open pull requests</div>';
        return;
      }
      
      state.prs.forEach(pr => {
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
            <span>${pr.created_at}</span>
          </div>
        `;
        card.onclick = () => this.showPRDetail(pr.id);
        container.appendChild(card);
      });
    } catch (e) {}
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
  async renderWork() {
    const container = document.getElementById('work-tab');
    // For now we'll just update parts of it
    try {
      state.work = await API.loadWork();
      document.getElementById('work-branch-name').textContent = state.work.current_branch;
      document.getElementById('stat-prs').textContent = state.work.open_prs;
      document.getElementById('stat-issues').textContent = state.work.open_issues;
      
      const changedList = document.getElementById('work-changed-files');
      changedList.innerHTML = state.work.changed_files.length ? '' : '<p class="text-muted">No changes</p>';
      state.work.changed_files.forEach(f => {
        const item = document.createElement('div');
        item.className = 'activity-item';
        item.innerHTML = `<span class="text-warning">M</span> ${f} <button class="action-btn" style="margin-left:auto; padding:2px 8px" onclick="UI.addFile('${f}')">Stage</button>`;
        changedList.appendChild(item);
      });
    } catch (e) {}
  },

  async addFile(path) {
    await API.addFile(path);
    this.showToast(`Staged ${path}`, 'success');
    this.renderWork();
  },

  // ── Branch Management ───────────────────────────────────
  async renderBranches() {
    try {
      const data = await API.get('/api/refs');
      state.refs = data;
      document.getElementById('current-branch-name').textContent = data.current_branch;
      
      const list = document.getElementById('branches-list');
      list.innerHTML = '';
      
      Object.keys(data.branches).forEach(name => {
        const item = document.createElement('div');
        item.className = 'tree-item';
        if (name === data.current_branch) item.classList.add('selected');
        item.innerHTML = `<span>⑂</span> <span class="truncate">${name}</span>`;
        item.onclick = async () => {
          if (name === data.current_branch) return;
          try {
            await API.checkoutBranch(name);
            this.showToast(`Switched to ${name}`, 'success');
            await this.renderBranches();
            this.loadTree(); // Refresh IDE tree for new branch
          } catch (e) {}
        };
        list.appendChild(item);
      });
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
