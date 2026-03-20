/* ⚓ Deep V3 — ui.js (Unified Shell & Intelligence) */

const UI = {
    // ── Initialization ──────────────────────────────────────
    async init() {
        console.log("⚓ UI Initializing...");
        this.renderTabChange(window.store.state.activeTab);
        this.subscribe();
        this.setupListeners();
    },

    async loadInitialData() {
        await Promise.all([this.loadTree(), this.loadWork(), this.loadRefs()]);
        this.switchTab('work');
    },

    setupListeners() {
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
                if (state.activeTab === 'ide' && state.monacoInstance) setTimeout(() => state.monacoInstance.layout(), 50);
            }
            if (state.tree !== oldState.tree || state.expandedFolders !== oldState.expandedFolders || state.selectedFile !== oldState.selectedFile) {
                this.renderFileTree();
            }
            if (state.selectedFile !== oldState.selectedFile || state.isDirty !== oldState.isDirty || state.openTabs !== oldState.openTabs) {
                this.renderEditorArea(); this.renderTabs();
            }
            if (state.work !== oldState.work) { 
                this.renderWorkDashboard(); this.renderBranchSwitcher(); 
                if (state.activeTab === 'scm') this.renderScmSidebar();
            }
            if (state.refs !== oldState.refs) { this.renderStatusBar(); this.renderBranchSwitcher(); }
            if (state.showingDiff !== oldState.showingDiff) this.updateDiffView();
        });
    },

    // ── Navigation & Sidebar ──────────────────────────────
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

    // ── AI Commit Intelligence (Phase 8 bonus) ───────────
    async generateCommitMsg(inputId) {
        const input = document.getElementById(inputId); if (!input) return;
        this.showToast("AI thinking...", "info");
        try {
            const res = await API.post('/api/generate/commit-msg');
            if (res.success && res.data.message) {
                input.value = res.data.message;
                this.showToast(`Suggested with ${Math.round(res.data.confidence*100)}% confidence`, "success");
            }
        } catch (e) { this.showToast("AI failed to suggest message", "error"); }
    },

    // ── Pull Request System (Phase 9) ─────────────────────
    async loadPRs(status = 'open') {
        try {
            const res = await API.get(`/api/prs?status=${status}`);
            const list = document.getElementById('pr-list-view');
            const detail = document.getElementById('pr-detail-view');
            if (!list || !detail) return;
            list.classList.remove('hidden'); detail.classList.add('hidden');
            if (!res.success || !res.data.length) { list.innerHTML = `<div class="text-muted" style="padding:40px; text-align:center;">No ${status} PRs.</div>`; return; }
            list.innerHTML = res.data.map(pr => `
                <div class="pr-card ${pr.status}" onclick="UI.openPR(${pr.id})">
                    <div style="display:flex; justify-content:space-between;"><span class="pr-title"><span class="pr-id">#${pr.id}</span>${pr.title}</span><span class="pr-status-badge ${pr.status}">${pr.status}</span></div>
                    <div class="pr-meta"><span>by <b>${pr.author}</b></span><span>branch: <code>${pr.head}</code></span></div>
                </div>`).join('');
        } catch (e) {}
    },

    async openPR(id) {
        try {
            const res = await API.get(`/api/pr/${id}`);
            const list = document.getElementById('pr-list-view');
            const detail = document.getElementById('pr-detail-view');
            if (!list || !detail || !res.success) return;
            list.classList.add('hidden'); detail.classList.remove('hidden');
            const pr = res.data;
            detail.innerHTML = `
                <button class="action-btn secondary" style="margin-bottom:24px;" onclick="UI.loadPRs()">← Back</button>
                <div class="pr-header"><h1>${pr.title}</h1><div class="pr-meta"><span>#${pr.id} by <b>${pr.author}</b></span></div></div>
                <div class="card" style="padding:24px; margin-bottom:32px;">${pr.description || 'No description.'}</div>
                <div class="review-list"><h3 style="margin-bottom:20px;">Reviews</h3>
                    ${Object.entries(pr.reviews || {}).map(([user, r]) => `<div class="review-item"><div class="review-avatar">${user[0]}</div><div class="review-content"><b>${user}</b> <span class="review-status ${r.status}">${r.status}</span><div>${r.comment || ''}</div></div></div>`).join('')}
                    <div style="margin-top:20px; display:flex; gap:12px;">
                        <button class="action-btn" onclick="UI.approvePR(${pr.id})">Approve</button>
                        <button class="action-btn" style="background:var(--purple); color:#fff;" onclick="UI.mergePR(${pr.id})">Merge</button>
                    </div>
                </div>`;
        } catch (e) {}
    },
    async approvePR(id) { await API.post(`/api/pr/${id}/approve`); this.showToast("Approved", "success"); this.openPR(id); },
    async mergePR(id) { await API.post(`/api/pr/${id}/merge`); this.showToast("Merged", "success"); this.loadPRs(); },

    // ── Issues System (Phase 10) ──────────────────────────
    async loadIssues(status = 'open') {
        try {
            const res = await API.get(`/api/issues?status=${status}`);
            const list = document.getElementById('issue-list-view'); if (!list) return;
            list.innerHTML = res.data.map(iss => `<div class="pr-card"><div class="pr-title">#${iss.id} ${iss.title}</div><div class="pr-meta">by <b>${iss.author}</b></div></div>`).join('');
        } catch (e) {}
    },

    // ── Source Control (SCM) ──────────────────────────────
    renderScmSidebar() {
        const container = document.getElementById('scm-content'); if (!container) return;
        const { work } = window.store.state;
        const staged = work.staged_files || [], changed = work.changed_files || [];
        container.innerHTML = `
            <div class="scm-commit-zone">
                <input type="text" id="scm-commit-msg" placeholder="Message...">
                <div style="display:flex; gap:8px; margin-top:8px;">
                    <button class="action-btn" style="flex:1" onclick="UI.commitChanges('scm-commit-msg')">Commit</button>
                    <button class="action-btn secondary" title="AI Suggest" onclick="UI.generateCommitMsg('scm-commit-msg')">✨</button>
                </div>
            </div>
            <div class="nav-section-title">STAGED (${staged.length})</div>
            <div class="scm-list">${staged.map(f => `<div class="scm-item"><span class="truncate" onclick="UI.openFile('${f}')">${f}</span><span class="scm-action" onclick="UI.unstageFile('${f}')">−</span></div>`).join('')}</div>
            <div class="nav-section-title">CHANGES (${changed.length})</div>
            <div class="scm-list">${changed.map(f => `<div class="scm-item"><span class="truncate" onclick="UI.openFile('${f}')">${f}</span><span class="scm-action" onclick="UI.stageFile('${f}')">+</span></div>`).join('')}</div>
        `;
    },

    async stageFile(path) { await API.post('/api/file/add', { path }); this.loadWork(); },
    async unstageFile(path) { await API.post('/api/reset', { mode: 'mixed', target: 'HEAD' }); this.loadWork(); },

    // ── Git Graph & Intelligence ─────────────────────────
    async loadLog() {
        const container = document.getElementById('dag'); if (!container) return;
        try {
            const log = await API.getLog(); window.store.set({ log });
            const { head, branches } = window.store.state.refs;
            const ns = new vis.DataSet(log.map(cm => ({ id: cm.sha, label: cm.sha.substring(0,7), shape: 'box', color: { background: cm.sha === head ? '#06b6d4' : '#111827', border: '#1f2937' }, font: { color: '#e5e7eb' } })));
            const es = new vis.DataSet(); log.forEach(cm => cm.parents.forEach(p => es.add({ from: cm.sha, to: p, arrows: 'to' })));
            const net = new vis.Network(container, { nodes: ns, edges: es }, { layout: { hierarchical: { direction: 'UD' } }, interaction: { dragNodes: false } });
            net.on("click", (p) => p.nodes.length ? this.onCommitClick(p.nodes[0]) : this.closeRightSidebar());
        } catch (e) {}
    },

    async onCommitClick(sha) {
        const c = window.store.state.log.find(x => x.sha === sha); if (!c) return;
        this.openRightSidebar();
        const container = document.getElementById('right-sidebar-content');
        container.innerHTML = `<div style="padding:20px;"><div class="commit-meta"><span class="commit-label">SHA</span><code class="code-box">${c.sha}</code><span class="commit-label">AUTHOR</span><div class="meta-val">${c.author}</div><span class="commit-label">MESSAGE</span><div class="message-box">${c.message}</div></div>
            <div style="margin:20px 0;"><button class="action-btn" onclick="UI.checkoutBranch('${c.sha}')">Checkout</button></div>
            <div class="nav-section-title">CHANGED FILES</div><div id="commit-diff-list" style="padding:20px;">Loading...</div></div>`;
        const res = await API.get(`/api/diff/${sha}`);
        if (res.success) document.getElementById('commit-diff-list').innerHTML = res.data.map(f => `<div class="diff-file-item" onclick="UI.openFile('${f.path}')"><span>${f.path.split('/').pop()}</span><span class="status-tag ${f.status}">${f.status[0].toUpperCase()}</span></div>`).join('');
    },

    // ── Explorer & Monaco ─────────────────────────────────
    renderFileTree() {
        const containers = [document.getElementById('file-tree'), document.getElementById('file-tree-ide')];
        const { tree, selectedFile, expandedFolders } = window.store.state;
        containers.forEach(el => {
            if (!el) return; el.innerHTML = '';
            if (!tree || !tree.children) return;
            const build = (nodes, p, ind = 0) => {
                nodes.sort((a,b) => (a.type==='directory') === (b.type==='directory') ? a.name.localeCompare(b.name) : (a.type==='directory' ? -1 : 1)).forEach(n => {
                    const isD = n.type === 'directory' || n.type === 'folder', exp = expandedFolders.has(n.path), item = document.createElement('div');
                    item.className = `tree-item ${selectedFile === n.path ? 'selected' : ''}`; item.style.paddingLeft = `${ind*12+16}px`;
                    item.innerHTML = `<span>${isD ? (exp ? '▼' : '▶') : ''}</span><span>${isD ? '📁' : '📄'}</span><span class="truncate">${n.name}</span>`;
                    item.onclick = (e) => { e.stopPropagation(); isD ? this.toggleFolder(n.path) : this.openFile(n.path); };
                    item.oncontextmenu = (e) => { e.preventDefault(); this.showContextMenu(e, n); };
                    p.appendChild(item); if (isD && exp && n.children) build(n.children, p, ind + 1);
                });
            };
            build(tree.children, el);
        });
    },
    toggleFolder(p) { const s = new Set(window.store.state.expandedFolders); s.has(p) ? s.delete(p) : s.add(p); window.store.set({ expandedFolders: s }); },
    async openFile(path) {
        if (!window.store.state.openTabs.includes(path)) window.store.set({ openTabs: [...window.store.state.openTabs, path] });
        window.store.set({ selectedFile: path, loading: true });
        try {
            const d = await API.getFile(path); window.store.set({ fileContent: d.content, isDirty: false, loading: false });
            this.initOrUpdateMonaco(d.content, path); this.switchTab('ide');
        } catch (e) { window.store.set({ loading: false }); }
    },
    initOrUpdateMonaco(c, p) {
        const { monacoInstance } = window.store.state; const lang = this.getLanguage(p);
        if (!monacoInstance) {
            const ed = monaco.editor.create(document.getElementById('monaco-container'), { value: c, language: lang, theme: 'vs-dark', automaticLayout: true, fontSize: 13, minimap: { enabled: false } });
            window.store.set({ monacoInstance: ed });
            ed.onDidChangeModelContent(() => window.store.set({ isDirty: ed.getValue() !== window.store.state.fileContent }));
        } else {
            monacoInstance.setValue(c); monaco.editor.setModelLanguage(monacoInstance.getModel(), lang);
        }
    },
    renderTabs() {
        const container = document.getElementById('editor-tabs'); if (!container) return;
        const { openTabs, selectedFile, isDirty } = window.store.state;
        container.innerHTML = openTabs.map(p => `<div class="editor-tab ${p===selectedFile?'active':''} ${p===selectedFile&&isDirty?'dirty':''}" onclick="UI.openFile('${p}')"><span>${p.split('/').pop()}</span><span class="dirty-dot"></span><span class="tab-close" onclick="event.stopPropagation(); UI.closeTab('${p}')">×</span></div>`).join('');
    },
    closeTab(path) {
        const { openTabs, selectedFile } = window.store.state; const nt = openTabs.filter(t => t !== path);
        let ns = selectedFile === path ? (nt.length ? nt[0] : null) : selectedFile;
        window.store.set({ openTabs: nt, selectedFile: ns }); if (ns && selectedFile===path) this.openFile(ns);
    },

    // ── Infrastructure ────────────────────────────────────
    renderWorkDashboard() {
        const { work, tree } = window.store.state;
        const bn = document.getElementById('work-branch-name'), sc = document.querySelector('.work-stats');
        if (bn) bn.textContent = work.current_branch || 'main';
        if (sc) sc.innerHTML = `<div class="work-stat-card"><div class="stat-value">${(work.changed_files||[]).length}</div><div class="stat-label">Changes</div></div>`;
    },
    async checkoutBranch(n) { await API.post('/api/branch/checkout', { name: n }); this.showToast("Switched", "success"); this.loadInitialData(); },
    renderBranchSwitcher() {
        const s = document.getElementById('branch-select'); if (!s) return;
        const { refs, work } = window.store.state; const b = Array.isArray(refs.branches) ? refs.branches : Object.keys(refs.branches || {});
        s.innerHTML = b.map(x => `<option value="${x}" ${x===(work.current_branch||refs.current_branch)?'selected':''}>${x}</option>`).join('');
    },
    renderStatusBar() {
        const { refs, work } = window.store.state; const b = document.getElementById('current-branch-status');
        if (b) b.textContent = work.current_branch || refs.current_branch || 'main';
    },
    showContextMenu(e, node) {
        const menu = document.getElementById('ctx-menu'); menu.classList.remove('hidden'); menu.style.top = `${e.clientY}px`; menu.style.left = `${e.clientX}px`;
        menu.innerHTML = `<div class="menu-item" onclick="UI.renameFile('${node.path}')">Rename</div><div class="menu-item danger" onclick="UI.deleteFile('${node.path}')">Delete</div>`;
    },
    hideContextMenu() { const m = document.getElementById('ctx-menu'); if (m) m.classList.add('hidden'); },
    async deleteFile(p) { if(confirm(`Delete ${p}?`)) { await API.post('/api/file/delete', { path: p }); this.loadTree(); } },
    async renameFile(p) { const n = prompt("New path:", p); if(n) { await API.post('/api/file/rename', { old_path: p, new_path: n }); this.loadTree(); } },
    async saveCurrentFile() {
        const { selectedFile, monacoInstance } = window.store.state; if (!selectedFile || !monacoInstance) return;
        await API.post('/api/file/save', { path: selectedFile, content: monacoInstance.getValue() });
        window.store.set({ fileContent: monacoInstance.getValue(), isDirty: false }); this.showToast("Saved", "success"); this.loadWork();
    },
    async commitChanges(miId = 'commit-msg') {
        const mi = document.getElementById(miId); const m = (mi?mi.value.trim():"") || "Update from Deep V3";
        await API.post('/api/commit', { message: m }); if(mi) mi.value=''; this.showToast("Committed", "success"); this.loadInitialData();
    },
    async createNewFile() { const n = prompt("File name:"); if(n) { await API.post('/api/file/create', { path: n }); this.loadTree(); this.openFile(n); } },
    async loadTree() { const d = await API.get('/api/tree'); window.store.set({ tree: d.data }); },
    async loadWork() { const d = await API.get('/api/work'); window.store.set({ work: d.data }); },
    async loadRefs() { const d = await API.get('/api/refs'); window.store.set({ refs: d.data }); },
    showToast(m, t = 'info') { const c = document.getElementById('toast-container'); if (!c) return; const div = document.createElement('div'); div.className = `toast ${t}`; div.textContent = m; c.appendChild(div); setTimeout(() => div.remove(), 4000); },
    getLanguage(p) { if (!p) return 'plaintext'; const e = p.split('.').pop(); return { js:'javascript', py:'python', html:'html', css:'css' }[e] || 'plaintext'; },
    toggleDiff() { window.store.set({ showingDiff: !window.store.state.showingDiff }); },
    renderEditorArea() {}
};

window.UI = UI;
