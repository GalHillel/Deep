/* ⚓ Deep V3 — ui.js (Unified Shell & Stability Recovery) */

const UI = {
    // ── Initialization ──────────────────────────────────────
    async init() {
        console.log("⚓ UI Initializing Components...");
        this.renderTabChange(window.store.state.activeTab);
        this.subscribe();
        // setupListeners is handled by App.boot()
    },

    async loadInitialData() {
        console.log("⚓ Loading Initial Data (Tree, Work, Refs)...");
        try {
            await Promise.all([this.loadTree(), this.loadWork(), this.loadRefs()]);
            console.log("⚓ Data Synchronized Successfully");
            this.switchTab('work');
        } catch (e) {
            console.error("⚓ Initial Data Load Failed:", e);
            throw e;
        }
    },

    setupListeners() {
        console.log("⚓ Setting up UI Global Listeners...");
        document.querySelectorAll('.activity-item').forEach(i => i.addEventListener('click', () => {
            const t = i.dataset.tab; if (t) this.switchTab(t);
        }));
        document.querySelectorAll('.tab-btn').forEach(b => b.addEventListener('click', () => {
            const t = b.dataset.tab; if (t) this.switchTab(t);
        }));

        document.addEventListener('click', (e) => {
            this.hideContextMenu();
            if (e.target.closest('.activity-item')) this.closeRightSidebar();
        });
        document.addEventListener('contextmenu', (e) => {
            if (!e.target.closest('.tree-item')) this.hideContextMenu();
        });

        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); this.saveCurrentFile(); }
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); this.commitChanges(); }
        });
    },

    subscribe() {
        window.store.subscribe((state, oldState) => {
            if (state.activeTab !== oldState.activeTab) {
                this.renderTabChange(state.activeTab);
                if (state.activeTab === 'graph') this.loadLog();
                if (state.activeTab === 'ide' && state.monacoInstance) setTimeout(() => state.monacoInstance.layout(), 10);
            }
            if (state.tree !== oldState.tree || state.expandedFolders !== oldState.expandedFolders || state.selectedFile !== oldState.selectedFile) {
                this.renderFileTree();
            }
            if (state.selectedFile !== oldState.selectedFile || state.isDirty !== oldState.isDirty || state.openTabs !== oldState.openTabs) {
                this.renderEditorArea(); this.renderTabs();
            }
            if (state.work !== oldState.work) { 
                this.renderWorkDashboard(); this.renderBranchSwitcher(); 
            }
            if (state.refs !== oldState.refs) { this.renderStatusBar(); this.renderBranchSwitcher(); }
        });
    },

    // ── Navigation ─────────────────────────────────────────
    switchTab(tabId) {
        window.store.set({ activeTab: tabId });
        if (tabId === 'prs') this.loadPRs();
        if (tabId === 'issues') this.loadIssues();
        if (['work', 'scm', 'graph'].includes(tabId)) this.loadWork();
    },

    renderTabChange(tabId) {
        if (!tabId) return;
        document.querySelectorAll('.activity-item').forEach(i => i.classList.toggle('active', i.dataset.tab === tabId));
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('hidden', c.id !== `${tabId}-tab`));
        this.renderSidebarContext(tabId);
    },

    renderSidebarContext(tabId) {
        const sidebar = document.getElementById('sidebar-content'); if (!sidebar) return;
        if (['ide','work','graph'].includes(tabId)) {
            sidebar.innerHTML = `<div class="nav-section"><h3>Explorer</h3><div id="file-tree"></div></div>`;
            this.renderFileTree();
        } else if (tabId === 'scm') {
            sidebar.innerHTML = `<div id="scm-sidebar" class="nav-section"><h3>Source Control</h3><div id="scm-content"></div></div>`;
            this.renderScmSidebar();
        } else if (tabId === 'prs') {
            sidebar.innerHTML = `<div class="nav-section"><h3>PR Filter</h3><div class="nav-item active" onclick="UI.loadPRs('open')">Open</div><div class="nav-item" onclick="UI.loadPRs('merged')">Merged</div></div>`;
        } else if (tabId === 'issues') {
            sidebar.innerHTML = `<div class="nav-section"><h3>Issue Filter</h3><div class="nav-item active" onclick="UI.loadIssues('open')">Active</div><div class="nav-item" onclick="UI.loadIssues('closed')">Closed</div></div>`;
        }
    },

    toggleRightSidebar() { document.getElementById('right-sidebar').classList.toggle('hidden'); },
    openRightSidebar() { document.getElementById('right-sidebar').classList.remove('hidden'); },
    closeRightSidebar() { document.getElementById('right-sidebar').classList.add('hidden'); },

    // ── Core Data Loading ─────────────────────────────────
    async loadTree() {
        console.log("⚓ Loading File Tree...");
        try {
            const data = await API.getTree();
            console.log("⚓ Tree Data Received:", data);
            window.store.set({ tree: data });
        } catch (e) {
            console.error("⚓ Tree Load Failed:", e);
        }
    },

    async loadWork() {
        console.log("⚓ Loading Work Metadata...");
        try {
            const data = await API.getWork();
            window.store.set({ work: data });
        } catch (e) { console.error("⚓ Work Load Failed:", e); }
    },

    async loadRefs() {
        console.log("⚓ Loading Git Refs...");
        try {
            const data = await API.getRefs();
            window.store.set({ refs: data });
        } catch (e) { console.error("⚓ Refs Load Failed:", e); }
    },

    // ── Explorer & Monaco ─────────────────────────────────
    renderFileTree() {
        const containers = [document.getElementById('file-tree'), document.getElementById('file-tree-ide')];
        const { tree, selectedFile, expandedFolders } = window.store.state;
        
        containers.forEach(el => {
            if (!el) return;
            el.innerHTML = '';
            if (!tree || !tree.children) {
                el.innerHTML = '<div class="text-muted" style="padding:10px;">Empty tree or loading...</div>';
                return;
            }

            const build = (nodes, p, ind = 0) => {
                nodes.sort((a,b) => (a.type==='directory') === (b.type==='directory') ? a.name.localeCompare(b.name) : (a.type==='directory' ? -1 : 1)).forEach(n => {
                    const isD = n.type === 'directory' || n.type === 'folder';
                    const exp = expandedFolders.has(n.path);
                    const item = document.createElement('div');
                    item.className = `tree-item ${selectedFile === n.path ? 'selected' : ''}`;
                    item.style.paddingLeft = `${ind*12+16}px`;
                    item.innerHTML = `<span>${isD ? (exp ? '▼' : '▶') : ''}</span><span>${isD ? '📁' : '📄'}</span><span class="truncate">${n.name}</span>`;
                    item.onclick = (e) => { e.stopPropagation(); isD ? this.toggleFolder(n.path) : this.openFile(n.path); };
                    item.oncontextmenu = (e) => { e.preventDefault(); this.showContextMenu(e, n); };
                    p.appendChild(item);
                    if (isD && exp && n.children) build(n.children, p, ind + 1);
                });
            };
            build(tree.children, el);
        });
    },

    toggleFolder(p) { const s = new Set(window.store.state.expandedFolders); s.has(p) ? s.delete(p) : s.add(p); window.store.set({ expandedFolders: s }); },

    async openFile(path) {
        console.log("⚓ Opening File:", path);
        if (!window.store.state.openTabs.includes(path)) window.store.set({ openTabs: [...window.store.state.openTabs, path] });
        window.store.set({ selectedFile: path, loading: true });
        try {
            const d = await API.getFile(path);
            window.store.set({ fileContent: d.content, isDirty: false, loading: false });
            
            if (window.editor) { // window.editor is set by App.boot()
                window.editor.setValue(d.content || "");
                monaco.editor.setModelLanguage(window.editor.getModel(), this.getLanguage(path));
            }
            this.switchTab('ide');
        } catch (e) {
            window.store.set({ loading: false });
            console.error("⚓ File Open Failed:", e);
        }
    },

    getLanguage(p) { if (!p) return 'plaintext'; const e = p.split('.').pop(); return { js:'javascript', py:'python', html:'html', css:'css' }[e] || 'plaintext'; },

    // ── Simple Dashboard ──────────────────────────────────
    renderWorkDashboard() {
        const { work } = window.store.state;
        const bn = document.getElementById('work-branch-name'), sc = document.querySelector('.work-stats');
        if (bn) bn.textContent = work.current_branch || 'main';
        if (sc) sc.innerHTML = `<div class="work-stat-card"><div class="stat-value">${(work.staged_files||[]).length}</div><div class="stat-label">Staged</div></div>`;
    },

    // ── Minimal Graph (vis.js) ──────────────────────────
    async loadLog() {
        console.log("⚓ Loading Git Graph...");
        const container = document.getElementById('dag'); if (!container) return;
        try {
            const log = await API.getLog();
            window.store.set({ log });
            const head = window.store.state.refs.head;
            
            const ns = new vis.DataSet(log.map(cm => ({
                id: cm.sha,
                label: cm.sha.substring(0,6),
                shape: 'box',
                color: { background: cm.sha === head ? '#06b6d4' : '#111827', border: '#1f2937' },
                font: { color: '#e5e7eb' }
            })));
            const es = new vis.DataSet();
            log.forEach(cm => { if (cm.parents) cm.parents.forEach(p => es.add({ from: cm.sha, to: p, arrows: 'to' })); });

            new vis.Network(container, { nodes: ns, edges: es }, {
                layout: { hierarchical: { direction: 'UD', sortMethod: 'directed' } },
                interaction: { dragNodes: false }
            });
            console.log("⚓ Graph Rendered");
        } catch (e) { console.error("⚓ Graph Data Failed:", e); }
    },

    // ── Stubs / Placeholders ─────────────────────────────
    renderStatusBar() {
        const { refs, work } = window.store.state;
        const b = document.getElementById('current-branch-status');
        if (b) b.textContent = work.current_branch || refs.current_branch || '...';
    },
    renderTabs() {
        const container = document.getElementById('editor-tabs'); if (!container) return;
        const { openTabs, selectedFile, isDirty } = window.store.state;
        container.innerHTML = openTabs.map(p => `<div class="editor-tab ${p===selectedFile?'active':''} ${p===selectedFile&&isDirty?'dirty':''}" onclick="UI.openFile('${p}')"><span>${p.split('/').pop()}</span><span class="tab-close" onclick="event.stopPropagation(); UI.closeTab('${p}')">×</span></div>`).join('');
    },
    closeTab(p) { /* simplified */ },
    renderEditorArea() {},
    renderSidebarContext(t) { /* simplified */ },
    showToast(m, t) { console.log(`TOAST [${t}]: ${m}`); },
    hideContextMenu() {},
    renderBranchSwitcher() {}
};

window.UI = UI;
