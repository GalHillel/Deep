/**
 * ⚓ Deep Studio — app.js (Final Overhaul)
 * The Definitive State Machine for Deep Web IDE.
 */

const App = {
    state: {
        tab: 'code',
        currentFile: null,
        editor: null,
        graphInstance: null,
        workspace: { branch: 'main', dirty: false },
        activeContextPath: null // Tracks selection in Explorer
    },

    async init() {
        console.log("⚓ Deep Studio Final Overhaul Booting...");
        this.initEditor();
        await this.syncWorkspace();
        
        // Set Project Name in Sidebar Header
        const repoRoot = this.state.workspace.repo_path || "Project";
        const projectName = repoRoot.split(/[\\/]/).pop();
        const headerName = document.getElementById('explorer-project-name');
        if(headerName) headerName.textContent = projectName;

        this.switchTab('code');
        setInterval(() => this.syncWorkspace(), 5000); 
    },

    toast(msg, error = false) {
        const container = document.getElementById('toast-container');
        const el = document.getElementById('toast-msg');
        if (!el) return;
        el.textContent = msg;
        el.className = `px-4 py-2 rounded shadow-lg border text-sm font-bold ${error ? 'bg-red-900 text-red-100 border-red-700' : 'bg-cyan-900 text-cyan-100 border-cyan-700'}`;
        container.classList.remove('opacity-0');
        setTimeout(() => container.classList.add('opacity-0'), 3000);
    },

    async api(endpoint, method = 'GET', body = null) {
        try {
            const opts = { method, headers: {} };
            if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
            const res = await fetch(endpoint, opts);
            const data = await res.json();
            if (!data.success) throw new Error(data.error || "Operation failed");
            return data.data;
        } catch (e) {
            this.toast(e.message, true);
            console.error(`API Error [${endpoint}]:`, e);
            return null;
        }
    },

    async syncWorkspace() {
        const data = await this.api('/api/status');
        if (!data) return;
        this.state.workspace = data;
        document.getElementById('header-branch').textContent = data.branch;
        
        const isDirty = (data.modified?.length || 0) + (data.untracked?.length || 0) > 0;
        const statusEl = document.getElementById('header-status');
        if (isDirty) {
            statusEl.innerHTML = '<i class="fa-solid fa-circle-exclamation text-yellow-500"></i> Uncommitted Changes';
            statusEl.classList.replace('text-gray-400', 'text-yellow-400');
        } else {
            statusEl.innerHTML = '<i class="fa-solid fa-check-double text-green-500 text-xs"></i> Clean Workspace';
            statusEl.classList.replace('text-yellow-400', 'text-gray-400');
        }
    },

    switchTab(tabId) {
        this.state.tab = tabId;
        document.querySelectorAll('.activity-icon').forEach(el => el.classList.remove('active'));
        const navEl = document.getElementById(`nav-${tabId}`);
        if (navEl) navEl.classList.add('active');

        document.querySelectorAll('.panel').forEach(el => el.classList.remove('active'));
        const panelEl = document.getElementById(`panel-${tabId}`);
        if (panelEl) panelEl.classList.add('active');

        const st = document.getElementById('sidebar-title');
        const sc = document.getElementById('sidebar-content');
        if (tabId === 'code') { st.textContent = 'Explorer'; this.loadTree(); }
        else if (tabId === 'graph') { st.textContent = 'Branches & Tags'; this.loadRefsSidebar(); this.loadGraph(); }
        else if (tabId === 'diff') { st.textContent = 'Changes'; this.loadDiffSidebar(); this.loadDiffContent(); }
        else if (tabId === 'prs') { st.textContent = 'Collaboration'; this.loadPRs(); }
        else if (tabId === 'issues') { st.textContent = 'Collaboration'; this.loadIssues(); }
    },

    /* --- EDITOR MODULE (VSCODE PARITY) --- */
    initEditor() {
        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.36.1/min/vs' }});
        require(['vs/editor/editor.main'], () => {
            this.state.editor = monaco.editor.create(document.getElementById('monaco-container'), {
                value: "// Open a file from the Explorer to begin.",
                theme: 'vs-dark', language: 'plaintext', automaticLayout: true, minimap: { enabled: false }
            });
            // Ctrl+S Binding
            this.state.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => this.saveCurrentFile());
        });
    },

    async loadTree() {
        const data = await this.api('/api/tree');
        if (!data || !data.tree) return;
        
        // Define Active Styles for Tailwind
        const activeItemClasses = "bg-cyan-900/50 text-white font-semibold border border-cyan-700";
        const hoverItemClasses = "hover:bg-slate-800";

        const renderNode = (nodeMap, name, depth = 0) => {
            const node = nodeMap[name];
            const isDir = node._type === 'dir';
            const currentPath = node.path || (isDir ? name : ''); 
            const isActive = this.state.activeContextPath === currentPath;
            const indent = depth > 0 ? `style="margin-left: ${depth * 10}px;"` : '';

            if (isDir) {
                let childHtml = '';
                const sortedKeys = Object.keys(node.children).sort((a, b) => {
                    const typeA = node.children[a]._type;
                    const typeB = node.children[b]._type;
                    if (typeA === typeB) return a.localeCompare(b);
                    return typeA === 'dir' ? -1 : 1;
                });
                for (const key of sortedKeys) childHtml += renderNode(node.children, key, depth + 1);
                
                return `
                <div class="mt-1" ${indent}>
                    <div id="tree-node-${btoa(currentPath)}"
                         class="cursor-pointer font-semibold text-slate-300 hover:text-white flex items-center py-1 select-none px-2 rounded transition-all ${hoverItemClasses} ${isActive ? activeItemClasses : ''}" 
                         onclick="App.setExplorerContext('${currentPath}', 'folder'); this.nextElementSibling.classList.toggle('hidden')">
                        <i class="fa-solid fa-folder text-cyan-600 mr-2 w-4"></i> ${name}
                    </div>
                    <div class="hidden border-l border-slate-800 ml-2 pl-2">
                        ${childHtml}
                    </div>
                </div>`;
            } else {
                return `
                <div class="mt-1" ${indent}>
                    <div id="tree-node-${btoa(currentPath)}"
                         class="cursor-pointer text-slate-400 hover:text-cyan-400 flex items-center py-1 px-2 rounded transition-all ${hoverItemClasses} ${isActive ? activeItemClasses : ''}" 
                         onclick="App.setExplorerContext('${currentPath}', 'file')">
                        <i class="fa-regular fa-file-code text-slate-500 mr-2 w-4"></i> ${name}
                    </div>
                </div>`;
            }
        };

        const rootKeys = Object.keys(data.tree).sort((a,b) => {
            const typeA = data.tree[a]._type;
            const typeB = data.tree[b]._type;
            if (typeA === typeB) return a.localeCompare(b);
            return typeA === 'dir' ? -1 : 1;
        });

        let html = '<div class="space-y-1 text-[13px] pt-2">';
        for (const key of rootKeys) html += renderNode(data.tree, key);
        html += '</div>';

        document.getElementById('sidebar-content').innerHTML = html;
        
        if(this.state.activeContextPath) {
            const el = document.getElementById(`tree-node-${btoa(this.state.activeContextPath)}`);
            if(el) el.scrollIntoView({ block: 'nearest' });
        }
    },

    setExplorerContext(path, type) {
        // Apply active styles visually
        if(this.state.activeContextPath) {
            const oldEl = document.getElementById(`tree-node-${btoa(this.state.activeContextPath)}`);
            if(oldEl) oldEl.classList.remove("bg-cyan-900/50", "text-white", "font-semibold", "border", "border-cyan-700");
        }
        this.state.activeContextPath = path;
        const newEl = document.getElementById(`tree-node-${btoa(path)}`);
        if(newEl) newEl.classList.add("bg-cyan-900/50", "text-white", "font-semibold", "border", "border-cyan-700");

        if (type === 'file') this.openFile(path);
    },

    async openFile(path) {
        if (!this.state.editor) {
            this.toast("Editor is still initializing, please wait...", true);
            return;
        }
        
        this.state.currentFile = path;
        const header = document.getElementById('editor-header');
        if(header) header.innerHTML = `<i class="fa-solid fa-spinner fa-spin mr-2 text-cyan-400"></i> Loading ${path}...`;
        
        const data = await this.api(`/api/file?path=${encodeURIComponent(path)}`);
        
        if (!data || data.error) {
            // Error is already toasted by this.api() or data.error exists
            if(header) header.innerHTML = `<i class="fa-solid fa-triangle-exclamation mr-2 text-red-400"></i> Failed to load ${path}`;
            if(data?.error) this.toast(data.error, true);
            return;
        }

        if(header) header.innerHTML = `<i class="fa-regular fa-file-code mr-2 text-cyan-400"></i> ${path}`;

        this.state.editor.setValue(data.isBinary ? `// System Note: ${data.content}` : data.content);
        this.state.editor.updateOptions({ readOnly: !!data.isBinary });
        
        // Set Syntax Highlighting
        const ext = path.split('.').pop().toLowerCase();
        const langs = { py: 'python', js: 'javascript', ts: 'typescript', html: 'html', css: 'css', json: 'json', md: 'markdown', txt: 'plaintext' };
        monaco.editor.setModelLanguage(this.state.editor.getModel(), langs[ext] || 'plaintext');
    },

    async saveCurrentFile() {
        if (!this.state.currentFile) return this.toast("No file open.", true);
        const res = await this.api('/api/file/save', 'POST', { filepath: this.state.currentFile, content: this.state.editor.getValue() });
        if (res) { this.toast("File saved (Uncommitted)"); this.syncWorkspace(); }
    },

    /* --- CONTEXT-AWARE CREATION LOGIC --- */

    createItem(type) {
        let parentDir = ''; 
        if (this.state.activeContextPath) {
            const pathParts = this.state.activeContextPath.split('/');
            const isFileSelection = pathParts[pathParts.length - 1].includes('.');
            if (isFileSelection) {
                pathParts.pop(); 
                parentDir = pathParts.join('/');
            } else {
                parentDir = this.state.activeContextPath;
            }
        }
        parentDir = parentDir.replace(/\\/g, '/');
        if(parentDir && !parentDir.endsWith('/')) parentDir += '/';
        this.showCreationModal(type, parentDir);
    },

    showCreationModal(type, parentDir) {
        const title = type === 'file' ? 'New File' : 'New Folder';
        const icon = type === 'file' ? 'fa-file-medical text-cyan-500' : 'fa-folder-plus text-cyan-500';
        const modalHtml = `
            <div id="creation-modal" class="fixed inset-0 bg-black/80 flex items-center justify-center z-[200] animate-in fade-in duration-200">
                <div class="bg-gray-900 border border-gray-700 rounded-xl w-96 overflow-hidden shadow-2xl flex flex-col">
                    <div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center select-none">
                        <h3 class="font-bold text-white flex items-center gap-2 text-xs uppercase tracking-widest"><i class="fa-solid ${icon}"></i> ${title}</h3>
                        <button onclick="document.getElementById('creation-modal').remove()" class="text-gray-400 hover:text-white transition-colors"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="p-4 bg-gray-950">
                        <div class="text-[10px] text-slate-500 mb-2 font-mono truncate">Creating in: /${parentDir || '(root)'}</div>
                        <input type="text" id="item-name-input" placeholder="Name (e.g. main.py)" class="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white text-sm focus:outline-none focus:border-cyan-500">
                    </div>
                    <div class="p-3 bg-gray-900 border-t border-gray-800 flex justify-end">
                        <button onclick="App.submitNewItem('${type}', '${parentDir}')" class="bg-cyan-600 hover:bg-cyan-500 text-white rounded px-4 py-1.5 font-bold text-xs uppercase tracking-widest transition-colors shadow-lg">Create</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const input = document.getElementById('item-name-input');
        input.focus();
        input.addEventListener('keypress', (e) => { if (e.key === 'Enter') App.submitNewItem(type, parentDir); });
    },

    async submitNewItem(type, parentDir) {
        const inputName = document.getElementById('item-name-input').value.trim();
        document.getElementById('creation-modal')?.remove();
        if (!inputName) return this.toast("Name required", true);
        if (inputName.includes('/') || inputName.includes('\\')) return this.toast("Name cannot contain slashes.", true);

        const fullRelPath = parentDir + inputName;
        this.toast(`Creating ${type}: /${fullRelPath}...`);
        const res = await this.api('/api/item/create', 'POST', { path: fullRelPath, type: type });
        if (res && res.status === 'success') {
            this.toast(`${type.charAt(0).toUpperCase() + type.slice(1)} created successfully.`);
            this.state.activeContextPath = res.path; 
            this.loadTree(); 
        }
    },

    async commitCurrentFile() {
        if (!this.state.currentFile) return this.toast("No file open.", true);
        const msg = document.getElementById('commit-msg-input').value.trim();
        if (!msg) return this.toast("Message required.", true);
        const res = await this.api('/api/commit', 'POST', { filepath: this.state.currentFile, content: this.state.editor.getValue(), message: msg });
        if (res) { this.toast("Committed successfully!"); document.getElementById('commit-msg-input').value = ''; this.syncWorkspace(); }
    },

    /* --- BRANCHING --- */
    async triggerCheckout() {
        const data = await this.api('/api/graph');
        if (!data) return;
        const branches = Object.keys(data.refs).filter(r => r.startsWith('branch:')).map(r => r.replace('branch:', ''));
        const listHtml = branches.map(b => `<div class="p-3 hover:bg-cyan-900/40 cursor-pointer text-cyan-400 font-bold border-b border-gray-800 transition-colors flex items-center" onclick="App.executeCheckout('${b}')"><i class="fa-solid fa-code-branch mr-3 opacity-50"></i> ${b}</div>`).join('');
        const modalHtml = `<div id="branch-modal" class="fixed inset-0 bg-black/80 flex items-center justify-center z-[100] animate-in fade-in duration-200"><div class="bg-gray-900 border border-gray-700 rounded-xl w-96 overflow-hidden shadow-2xl flex flex-col"><div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center"><h3 class="font-bold text-white uppercase text-xs tracking-widest">Switch Branch</h3><button onclick="document.getElementById('branch-modal').remove()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button></div><div class="max-h-64 overflow-y-auto bg-black/40">${listHtml}</div><div class="p-4 bg-gray-950 border-t border-gray-800"><input type="text" id="new-branch-input" placeholder="New branch name..." class="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white text-sm mb-3 outline-none focus:border-cyan-500"><button onclick="App.createAndCheckoutBranch()" class="w-full bg-cyan-700 hover:bg-cyan-600 text-white rounded p-2 font-bold transition-all shadow-lg">Create & Checkout</button></div></div></div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async executeCheckout(branch) {
        document.getElementById('branch-modal')?.remove();
        const res = await this.api('/api/branch/checkout', 'POST', { branch });
        if (res) { this.toast(`Checked out ${branch}`); await this.syncWorkspace(); if(this.state.tab === 'code') this.loadTree(); }
    },
    
    async createAndCheckoutBranch() {
        const name = document.getElementById('new-branch-input').value.trim();
        if (!name) return this.toast("Branch name required", true);
        document.getElementById('branch-modal')?.remove();
        if (await this.api('/api/branch/create', 'POST', { name })) this.executeCheckout(name);
    },

    /* --- GRAPH & DIFF --- */
    async loadRefsSidebar() {
        const data = await this.api('/api/graph');
        if (!data) return;
        let html = '<div class="space-y-2">';
        for (const [ref, sha] of Object.entries(data.refs || {})) {
            if (ref === "HEAD") continue;
            const isB = ref.startsWith('branch:');
            const n = ref.replace('branch:', '').replace('tag:', '');
            html += `<div class="bg-gray-800/50 p-2 rounded flex justify-between items-center border border-gray-700 hover:border-gray-600 transition-colors"><span class="font-bold ${isB?'text-cyan-400':'text-amber-400'} cursor-pointer text-xs" onclick="App.executeCheckout('${n}')"><i class="fa-solid ${isB?'fa-code-branch':'fa-tag'} mr-1"></i> ${n}</span><i class="fa-solid fa-code-merge text-gray-500 hover:text-green-400 cursor-pointer text-xs transition-colors" onclick="App.triggerMerge('${n}')"></i></div>`;
        }
        document.getElementById('sidebar-content').innerHTML = html + '</div>';
    },

    async loadGraph() {
        const data = await this.api('/api/graph'); if (!data) return;
        let nodes = new vis.DataSet(); let edges = new vis.DataSet(); let rMap = {};
        for (const [r, sha] of Object.entries(data.refs || {})) { if(!rMap[sha]) rMap[sha]=[]; rMap[sha].push(r.replace('branch:','').replace('tag:','')); }
        data.commits.forEach((c, i) => {
            let label = c.sha.substring(0,7); let color = { background: '#1f2937', border: '#374151' };
            if (rMap[c.sha]) { label = rMap[c.sha].join(', ') + '\n' + label; color = { background: '#0891b2', border: '#06b6d4' }; }
            nodes.add({ id: c.sha, label, shape: 'box', color, font: { color: 'white', face: 'monospace', size: 10 } });
            if (c.parents) c.parents.forEach(p => edges.add({ from: c.sha, to: p, arrows: 'to' }));
        });
        if (this.state.graphInstance) this.state.graphInstance.destroy();
        this.state.graphInstance = new vis.Network(document.getElementById('network-canvas'), { nodes, edges }, {
            layout: { hierarchical: { direction: "UD", sortMethod: "directed", nodeSpacing: 250, levelSeparation: 120 } },
            physics: { enabled: true, hierarchicalRepulsion: { nodeDistance: 200 }, stabilization: { iterations: 150 } },
            edges: { smooth: { type: 'cubicBezier', forceDirection: 'vertical' } }
        });
        this.state.graphInstance.once("stabilizationIterationsDone", () => this.state.graphInstance.setOptions({ physics: { enabled: false } }));
    },

    async loadDiffSidebar() {
        const d = await this.api('/api/status'); if (!d) return;
        let html = '<div class="text-[10px] space-y-4">';
        if (d.modified?.length) html += `<div><div class="text-yellow-400 font-bold mb-1 uppercase">Modified</div>` + d.modified.map(f => `<div class="ml-2 mb-1 truncate text-gray-400"><i class="fa-solid fa-circle-dot mr-1 opacity-50"></i>${f}</div>`).join('') + `</div>`;
        if (d.untracked?.length) html += `<div><div class="text-green-400 font-bold mb-1 uppercase">Untracked</div>` + d.untracked.map(f => `<div class="ml-2 mb-1 truncate text-gray-400"><i class="fa-solid fa-plus mr-1 opacity-50"></i>${f}</div>`).join('') + `</div>`;
        document.getElementById('sidebar-content').innerHTML = html || '<div class="text-gray-500 p-4">Clean</div>';
    },

    async loadDiffContent() {
        const d = await this.api('/api/diff'); const c = document.getElementById('diff-content');
        if (!d || !d.diff) { c.innerHTML = "<div class='text-center p-8 text-gray-600'>Clean.</div>"; return; }
        let html = ''; d.diff.split('\n').forEach(l => {
            if (l.startsWith('+')) html += `<div class="text-green-400 bg-green-900/10">${l}</div>`;
            else if (l.startsWith('-')) html += `<div class="text-red-400 bg-red-900/10">${l}</div>`;
            else html += `<div class="opacity-80">${l}</div>`;
        });
        c.innerHTML = html;
    },

    /* --- COLLABORATION HUB --- */
    async loadIssues() {
        const data = await this.api('/api/issues/local');
        let html = `<div class="flex justify-between items-center mb-6"><h3 class="text-lg font-bold text-white"><i class="fa-regular fa-circle-dot text-green-500 mr-2"></i> Local Issues</h3><button onclick="App.showCreateIssueModal()" class="bg-green-700 hover:bg-green-600 text-white px-3 py-1 rounded font-bold text-xs"><i class="fa-solid fa-plus mr-1"></i> New Issue</button></div><div class="space-y-3">`;
        if (!data || !data.issues || data.issues.length === 0) { html += "<div class='text-gray-500 text-center p-4 italic'>No issues found.</div>"; }
        else {
            data.issues.forEach(iss => {
                const isO = (iss.status || iss.state) === "open" || (iss.status || iss.state) === "OPEN";
                html += `<div class="bg-gray-900/60 p-4 rounded-xl border border-gray-800 flex justify-between items-start transition-all hover:border-gray-700"><div class="flex-1"><div class="font-bold text-white mb-1"><span class="${isO?'text-green-400':'text-purple-400'}">[${(iss.status || iss.state).toUpperCase()}]</span> #${iss.id} ${iss.title}</div><div class="text-gray-500 text-sm italic">${iss.description || iss.body || 'No description.'}</div></div><button onclick="App.manageIssue(${iss.id}, '${isO?'close':'reopen'}')" class="text-[10px] bg-gray-800 hover:bg-gray-700 px-2 py-1 rounded-lg text-gray-300 font-bold uppercase tracking-wider transition-colors ml-3">${isO?'Close':'Reopen'}</button></div>`;
            });
        }
        document.getElementById('panel-issues').innerHTML = `<div class="p-6 overflow-y-auto h-full">${html}</div></div>`;
    },

    async showCreateIssueModal() {
        const modalHtml = `<div id="create-issue-modal" class="fixed inset-0 bg-black/80 flex items-center justify-center z-[100] animate-in fade-in duration-200"><div class="bg-gray-900 border border-gray-700 rounded-2xl w-[500px] shadow-2xl flex flex-col overflow-hidden"><div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center"><h3 class="font-bold text-white text-sm uppercase tracking-widest">Create Issue</h3><button onclick="document.getElementById('create-issue-modal').remove()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button></div><div class="p-6 flex flex-col gap-4 bg-[#0b0f19]"><input type="text" id="ci-title" placeholder="Issue Title" class="bg-black border border-gray-800 rounded-xl p-3 text-white w-full outline-none focus:border-green-600"><textarea id="ci-body" placeholder="Description..." class="bg-black border border-gray-800 rounded-xl p-3 text-white w-full h-32 outline-none focus:border-green-600"></textarea><button onclick="App.submitNewIssue()" class="bg-green-600 hover:bg-green-500 text-white font-black py-3 rounded-xl uppercase text-xs tracking-widest transition-all">Submit Issue</button></div></div></div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async submitNewIssue() {
        const title = document.getElementById('ci-title').value.trim();
        const body = document.getElementById('ci-body').value.trim();
        if (!title) return this.toast("Title required", true);
        if (await this.api('/api/issue/create', 'POST', { title, body })) { this.toast("Issue created!"); document.getElementById('create-issue-modal').remove(); this.loadIssues(); }
    },

    async manageIssue(issue_id, action) {
        if (await this.api('/api/issue/manage', 'POST', { issue_id, action })) { this.toast(`Issue ${action === 'close' ? 'closed' : 'reopened'}`); this.loadIssues(); }
    },

    async loadPRs() {
        const data = await this.api('/api/prs/local');
        let html = `<div class="flex justify-between items-center mb-6"><h3 class="text-lg font-bold text-white"><i class="fa-solid fa-code-pull-request text-purple-500 mr-2"></i> Local PRs</h3><button onclick="App.showCreatePRModal()" class="bg-purple-700 hover:bg-purple-600 text-white px-3 py-1 rounded font-bold text-xs"><i class="fa-solid fa-plus mr-1"></i> New PR</button></div><div class="grid gap-4">`;
        if (!data || !data.prs || data.prs.length === 0) { html += "<div class='text-gray-500 text-center p-4 italic'>No PRs found.</div>"; }
        else {
            data.prs.forEach(pr => {
                const c = pr.status === "merged" ? "text-green-400" : "text-amber-400";
                html += `<div class="bg-gray-900/60 p-4 rounded-xl border border-gray-800 hover:border-purple-900/50 transition-all cursor-pointer" onclick="App.showPRDetails(${pr.id})"><div class="flex justify-between mb-2"><span class="font-bold text-white">#${pr.id} ${pr.title}</span><span class="${c} text-[10px] uppercase font-black">${pr.status}</span></div><div class="text-gray-500 text-xs mb-3 italic">${pr.body || 'No description.'}</div><div class="text-[10px] font-mono text-cyan-500 bg-black/40 px-2 py-1 rounded border border-gray-800 inline-block">${pr.head} → ${pr.base}</div></div>`;
            });
        }
        document.getElementById('panel-prs').innerHTML = `<div class="p-6 overflow-y-auto h-full">${html}</div></div>`;
    },

    showCreatePRModal() {
        const modalHtml = `<div id="create-pr-modal" class="fixed inset-0 bg-black/80 flex items-center justify-center z-[100] animate-in fade-in duration-200"><div class="bg-gray-900 border border-gray-700 rounded-2xl w-[500px] shadow-2xl flex flex-col overflow-hidden"><div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center"><h3 class="font-bold text-white text-sm uppercase tracking-widest">Create PR</h3><button onclick="document.getElementById('create-pr-modal').remove()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button></div><div class="p-6 flex flex-col gap-4 bg-[#0b0f19]"><input type="text" id="cpr-title" placeholder="PR Title" class="bg-black border border-gray-800 rounded-xl p-3 text-white w-full outline-none focus:border-purple-600"><textarea id="cpr-desc" placeholder="Description..." class="bg-black border border-gray-800 rounded-xl p-3 text-white w-full h-24 outline-none focus:border-purple-600"></textarea><div class="flex gap-2"><input type="text" id="cpr-head" value="${this.state.workspace.branch}" class="bg-black border border-gray-800 rounded-xl p-3 text-cyan-400 w-1/2 outline-none"><input type="text" id="cpr-base" value="main" class="bg-black border border-gray-800 rounded-xl p-3 text-gray-400 w-1/2 outline-none"></div><input type="text" id="cpr-issue" placeholder="Link Issue ID (optional)" class="bg-black border border-gray-800 rounded-xl p-3 text-white w-full outline-none placeholder:text-gray-700"><button onclick="App.submitNewPR()" class="bg-purple-600 hover:bg-purple-500 text-white font-black py-3 rounded-xl uppercase text-xs tracking-widest shadow-xl transition-all">Submit PR</button></div></div></div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async submitNewPR() {
        const payload = { title: id('cpr-title').value.trim(), desc: id('cpr-desc').value.trim(), head: id('cpr-head').value.trim(), base: id('cpr-base').value.trim(), issue_id: id('cpr-issue').value.trim() || null };
        function id(i) { return document.getElementById(i); }
        if (!payload.title || !payload.head) return this.toast("Title and Head required", true);
        if (await this.api('/api/pr/create', 'POST', payload)) { this.toast("PR created!"); document.getElementById('create-pr-modal').remove(); this.loadPRs(); }
    },

    async showPRDetails(id) {
        const data = await this.api('/api/prs/local'); 
        const pr = data.prs.find(p => p.id == id);
        if (!pr) return this.toast("PR not found", true);
        
        const reviewsHtml = (pr.reviews || []).map(r => `
            <div class="bg-black/40 p-3 rounded-lg border border-gray-800 text-xs">
                <div class="flex justify-between mb-1">
                    <span class="font-bold text-gray-300">${r.author}</span>
                    <span class="uppercase font-black ${r.state === 'APPROVED' ? 'text-green-500' : 'text-red-500'}">${r.state}</span>
                </div>
                <div class="text-gray-500 italic">${r.comment || 'No comment.'}</div>
            </div>
        `).join('') || '<div class="text-gray-600 text-xs italic">No reviews yet.</div>';

        const modalHtml = `
            <div id="pr-detail-modal" class="fixed inset-0 bg-black/90 flex items-center justify-center z-[110] animate-in zoom-in duration-200">
                <div class="bg-gray-900 border border-gray-700 rounded-2xl w-[600px] max-h-[80vh] overflow-hidden shadow-2xl flex flex-col">
                    <div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center">
                        <div class="flex items-center gap-2">
                            <span class="bg-purple-600 text-white text-[10px] font-black px-2 py-0.5 rounded uppercase">${pr.status}</span>
                            <h3 class="font-bold text-white">#${pr.id} ${pr.title}</h3>
                        </div>
                        <button onclick="document.getElementById('pr-detail-modal').remove()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="p-6 overflow-y-auto space-y-6 bg-[#0b0f19]">
                        <div class="space-y-2">
                            <div class="text-xs font-black text-gray-500 uppercase tracking-widest">Description</div>
                            <div class="text-gray-300 text-sm bg-black/20 p-4 rounded-xl border border-gray-800">${pr.body || 'No description provided.'}</div>
                        </div>
                        
                        <div class="flex gap-4">
                            <div class="flex-1 space-y-2">
                                <div class="text-xs font-black text-gray-500 uppercase tracking-widest">Pipeline</div>
                                <div class="font-mono text-[11px] text-cyan-400 bg-black p-3 rounded-xl border border-gray-800">
                                    ${pr.head} <i class="fa-solid fa-arrow-right mx-2 text-gray-600"></i> ${pr.base}
                                </div>
                            </div>
                            <div class="flex-1 space-y-2">
                                <div class="text-xs font-black text-gray-500 uppercase tracking-widest">Linked Issue</div>
                                <div class="text-sm ${pr.linked_issue ? 'text-green-400' : 'text-gray-600 italic'} bg-black p-3 rounded-xl border border-gray-800">
                                    ${pr.linked_issue ? `Issue #${pr.linked_issue}` : 'None'}
                                </div>
                            </div>
                        </div>

                        <div class="space-y-3">
                            <div class="text-xs font-black text-gray-500 uppercase tracking-widest">Reviews</div>
                            <div class="space-y-2">${reviewsHtml}</div>
                        </div>

                        <div class="pt-4 border-t border-gray-800 flex gap-3">
                            <button onclick="App.submitReview(${pr.id}, 'APPROVED')" class="flex-1 bg-green-700 hover:bg-green-600 text-white font-black py-2 rounded-lg text-[10px] uppercase">Approve</button>
                            <button onclick="App.submitReview(${pr.id}, 'CHANGES_REQUESTED')" class="flex-1 bg-red-900/50 hover:bg-red-800 text-red-100 font-black py-2 rounded-lg text-[10px] uppercase">Request Changes</button>
                            <button onclick="App.mergePR(${pr.id})" class="flex-1 bg-purple-600 hover:bg-purple-500 text-white font-black py-2 rounded-lg text-[10px] uppercase shadow-lg">Merge PR</button>
                        </div>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async submitReview(pr_id, state) {
        const comment = prompt("Enter review comment:", state === 'APPROVED' ? "LGTM!" : "Please fix...");
        if (comment === null) return;
        if (await this.api('/api/pr/review', 'POST', { pr_id, state, comment })) {
            this.toast("Review submitted!");
            document.getElementById('pr-detail-modal')?.remove();
            this.loadPRs();
        }
    },

    async mergePR(pr_id) {
        if (!confirm("Are you sure you want to merge this PR locally?")) return;
        if (await this.api('/api/pr/merge', 'POST', { pr_id })) {
            this.toast("PR Merged Successfully!");
            document.getElementById('pr-detail-modal')?.remove();
            this.loadPRs();
            this.syncWorkspace();
        }
    },

    async triggerMerge(b) { if(confirm(`Merge ${b}?`)){ if(await this.api('/api/merge','POST',{branch:b})) { this.toast(`Merged ${b}`); this.syncWorkspace(); this.loadGraph(); }}}
};

window.onload = () => App.init();
