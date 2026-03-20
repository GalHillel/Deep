/* Deep Platform — ui.js (Reactive 3rd Pane Layout) */

const UI = {
  // ── Initialization ──────────────────────────────────────
  init() {
    console.log("UI Initializing...");
    this.initActivityBar();
    this.initResizers();
    this.subscribe();
    this.loadInitialData();
  },

  loadInitialData() {
    this.loadTree();
    this.loadWork();
    this.loadRefs();
  },

  subscribe() {
    window.store.subscribe((state, oldState) => {
      if (state.tree !== oldState.tree) this.renderFileTree();
      if (state.selectedFile !== oldState.selectedFile || state.isDirty !== oldState.isDirty) {
        this.renderTabs();
      }
      if (state.work !== oldState.work) {
        this.renderContextPane();
        this.renderStatusBar();
      }
      if (state.refs !== oldState.refs) this.renderStatusBar();
      if (state.showingDiff !== oldState.showingDiff) this.updateDiffView();
    });
  },

  // ── Layout & Resizers ───────────────────────────────────
  initActivityBar() {
    document.querySelectorAll('.activity-item').forEach(item => {
      item.addEventListener('click', () => {
        const tool = item.dataset.tool;
        if (!tool) return;

        document.querySelectorAll('.activity-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');

        const title = tool.toUpperCase();
        const titleEl = document.getElementById('sidebar-title');
        if (titleEl) titleEl.textContent = title;

        document.querySelectorAll('.tool-view').forEach(v => v.classList.add('hidden'));
        const view = document.getElementById(`${tool}-view`);
        if (view) view.classList.remove('hidden');

        // Logic based on tool
        if (tool === 'git') this.loadRefs();
        if (tool === 'prs') this.loadPRs();
        if (tool === 'issues') this.loadIssues();
        if (tool === 'work') this.loadWork();
      });
    });
  },

  initResizers() {
    const resizerL = document.getElementById('resizer-left');
    const resizerR = document.getElementById('resizer-right');
    const sidebar = document.getElementById('sidebar-pane');
    const context = document.getElementById('context-pane');

    const setupResizer = (resizer, pane, isLeft) => {
      if (!resizer || !pane) return;
      let startX, startWidth;

      const onMouseMove = (e) => {
        const delta = e.clientX - startX;
        const newWidth = isLeft ? startWidth + delta : startWidth - delta;
        if (newWidth > 150 && newWidth < 800) {
          pane.style.width = `${newWidth}px`;
          if (window.store.state.monacoInstance) window.store.state.monacoInstance.layout();
          if (window.store.state.diffEditorInstance) window.store.state.diffEditorInstance.layout();
        }
      };

      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        resizer.classList.remove('dragging');
      };

      resizer.addEventListener('mousedown', (e) => {
        startX = e.clientX;
        startWidth = pane.offsetWidth;
        resizer.classList.add('dragging');
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    };

    setupResizer(resizerL, sidebar, true);
    setupResizer(resizerR, context, false);
  },

  // ── Rendering ───────────────────────────────────────────
  renderFileTree() {
    const container = document.getElementById('file-tree');
    if (!container) return;
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

  renderTabs() {
    const container = document.getElementById('tabs-container');
    if (!container) return;
    const { selectedFile, isDirty } = window.store.state;
    if (!selectedFile) {
      container.innerHTML = '';
      return;
    }

    const name = selectedFile.split('/').pop();
    container.innerHTML = `
      <div class="tab active">
        <span>📄</span>
        <span>${name}${isDirty ? ' ●' : ''}</span>
        <span class="tab-close" onclick="UI.closeFile()">×</span>
      </div>
    `;
    
    const diffBtn = document.getElementById('diff-toggle-btn');
    if (diffBtn) diffBtn.classList.toggle('hidden', !isDirty);
  },

  renderStatusBar() {
    const { refs, work } = window.store.state;
    const branchInfo = document.getElementById('status-branch');
    const syncInfo = document.getElementById('status-sync');
    
    if (branchInfo) branchInfo.textContent = `⑂ ${refs.current_branch || 'main'}`;
    if (syncInfo && work.sync) {
      syncInfo.textContent = `↑${work.sync.ahead} ↓${work.sync.behind}`;
    }
  },

  renderContextPane() {
    const { work } = window.store.state;
    const stagedList = document.getElementById('staged-list');
    const changedList = document.getElementById('changed-list');
    const commitBtn = document.getElementById('commit-primary-btn');

    if (stagedList) {
      stagedList.innerHTML = work.staged_files.length ? '' : '<div class="text-dark" style="font-size:11px; padding:4px 8px;">No staged changes</div>';
      work.staged_files.forEach(f => {
        const item = document.createElement('div');
        item.className = 'mini-item truncate';
        item.innerHTML = `<span style="color:var(--success)">M</span> ${f}`;
        item.onclick = () => this.openFile(f);
        stagedList.appendChild(item);
      });
    }

    if (changedList) {
      changedList.innerHTML = work.changed_files.length ? '' : '<div class="text-dark" style="font-size:11px; padding:4px 8px;">Clean working tree</div>';
      work.changed_files.forEach(f => {
        const item = document.createElement('div');
        item.className = 'mini-item truncate';
        item.innerHTML = `
          <span style="color:var(--warning)">M</span> ${f}
          <span class="icon-btn" onclick="UI.stageFile(event, '${f}')" style="margin-left:auto; font-size:12px;">+</span>
        `;
        item.onclick = () => this.openFile(f);
        changedList.appendChild(item);
      });
    }

    if (commitBtn) {
      commitBtn.disabled = work.staged_files.length === 0;
      commitBtn.style.opacity = work.staged_files.length === 0 ? 0.5 : 1;
    }
  },

  // ── Actions ─────────────────────────────────────────────
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
        minimap: { enabled: false },
        lineNumbers: 'on'
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

  async stageFile(event, path) {
    if (event) event.stopPropagation();
    const { work } = window.store.state;
    window.store.set({
      work: {
        ...work,
        changed_files: work.changed_files.filter(f => f !== path),
        staged_files: [...work.staged_files, path]
      }
    });
    try {
      await API.addFile(path);
      this.loadWork();
    } catch (e) {
      this.loadWork();
    }
  },

  toggleDiff() {
    window.store.set({ showingDiff: !window.store.state.showingDiff });
  },

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
      diffEditorInstance = monaco.editor.createDiffEditor(container, {
        theme: 'vs-dark',
        automaticLayout: true,
        readOnly: true
      });
      window.store.set({ diffEditorInstance });
    }
    const lang = this.getLanguage(selectedFile);
    const originalModel = monaco.editor.createModel(fileContent, lang);
    const modifiedModel = monaco.editor.createModel(monacoInstance.getValue(), lang);
    diffEditorInstance.setModel({ original: originalModel, modified: modifiedModel });
  },

  async loadTree() {
    const tree = await API.loadTree();
    window.store.set({ tree });
  },

  async loadWork() {
    const work = await API.loadWork();
    window.store.set({ work });
  },

  async loadRefs() {
    const refs = await API.get('/api/refs');
    window.store.set({ refs });
  },

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.animation = 'toastOut .3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  },

  getLanguage(path) {
    if (!path) return 'plaintext';
    const ext = path.split('.').pop();
    const map = { js: 'javascript', py: 'python', html: 'html', css: 'css', md: 'markdown', json: 'json' };
    return map[ext] || 'plaintext';
  }
};

window.UI = UI;
