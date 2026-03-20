/**
 * ⚓ Deep Studio — app.js (Pinnacle Edition)
 * Enterprise-grade state machine for Deep Web IDE.
 */

const App = {
    state: {
        tab: 'code',
        currentFile: null,
        editor: null,
        graphInstance: null,
        workspace: { branch: 'main', dirty: false }
    },

    async init() {
        console.log("⚓ Deep Studio Pinnacle Booting...");
        this.initEditor();
        await this.syncWorkspace();
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
        else if (tabId === 'prs') { st.textContent = 'Local PRs'; sc.innerHTML=''; this.loadPRs(); }
        else if (tabId === 'issues') { st.textContent = 'Local Issues'; sc.innerHTML=''; this.loadIssues(); }
    },

    /* --- EDITOR & TREE MODULE (PINNACLE NESTED) --- */
    initEditor() {
        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.36.1/min/vs' }});
        require(['vs/editor/editor.main'], () => {
            this.state.editor = monaco.editor.create(document.getElementById('monaco-container'), {
                value: "// Open a file from the Explorer to begin.",
                theme: 'vs-dark',
                language: 'javascript',
                automaticLayout: true,
                minimap: { enabled: false }
            });
        });
    },

    async loadTree() {
        const data = await this.api('/api/tree');
        if (!data || !data.tree) return;
        
        const renderNode = (nodeMap, name) => {
            const node = nodeMap[name];
            if (node._type === 'dir') {
                let childHtml = '';
                const sortedKeys = Object.keys(node.children).sort((a, b) => {
                    const typeA = node.children[a]._type;
                    const typeB = node.children[b]._type;
                    if (typeA === typeB) return a.localeCompare(b);
                    return typeA === 'dir' ? -1 : 1;
                });
                for (const key of sortedKeys) childHtml += renderNode(node.children, key);
                
                return `<div class="ml-2 mt-1">
                    <div class="cursor-pointer font-semibold text-slate-300 hover:text-white flex items-center py-1 select-none text-[13px]" onclick="this.nextElementSibling.classList.toggle('hidden')">
                        <i class="fa-solid fa-folder text-cyan-600 mr-2 w-4"></i> ${name}
                    </div>
                    <div class="ml-2 pl-2 border-l border-slate-800 hidden">
                        ${childHtml}
                    </div>
                </div>`;
            } else {
                return `<div class="ml-2 cursor-pointer text-slate-400 hover:text-cyan-400 hover:bg-slate-800 rounded px-1 flex items-center py-1 transition-colors select-none text-[13px]" onclick="App.openFile('${node.path}')">
                    <i class="fa-regular fa-file-code text-slate-500 mr-2 w-4"></i> ${name}
                </div>`;
            }
        };

        const rootKeys = Object.keys(data.tree).sort((a,b) => {
            const typeA = data.tree[a]._type;
            const typeB = data.tree[b]._type;
            if (typeA === typeB) return a.localeCompare(b);
            return typeA === 'dir' ? -1 : 1;
        });

        let html = '<div class="space-y-1">';
        for (const key of rootKeys) html += renderNode(data.tree, key);
        html += '</div>';

        document.getElementById('sidebar-content').innerHTML = html;
    },

    async openFile(path) {
        if (!this.state.editor) return this.toast("Editor initializing...", true);
        this.state.currentFile = path;
        document.getElementById('editor-header').innerHTML = `<i class="fa-regular fa-file-code mr-2"></i> ${path}`;
        
        const data = await this.api(`/api/file?path=${encodeURIComponent(path)}`);
        if (!data) return;

        this.state.editor.setValue(data.isBinary ? `// Binary or unreadable file\n// ${data.content}` : data.content);
        this.state.editor.updateOptions({ readOnly: data.isBinary });
        
        const ext = path.split('.').pop();
        const langs = { py: 'python', js: 'javascript', html: 'html', css: 'css', json: 'json', md: 'markdown' };
        monaco.editor.setModelLanguage(this.state.editor.getModel(), langs[ext] || 'plaintext');
    },

    async commitCurrent() {
        const msg = document.getElementById('commit-input').value.trim();
        if (!msg) return this.toast("Message required.", true);
        const res = await this.api('/api/commit', 'POST', { message: msg });
        if (res && res.status === 'success') {
            this.toast("Commit successful!");
            document.getElementById('commit-input').value = '';
            this.syncWorkspace();
        }
    },

    /* --- BRANCH MANAGEMENT (PINNACLE MODALS) --- */
    async triggerCheckout() {
        const data = await this.api('/api/graph');
        if (!data || !data.refs) return;
        
        const branches = Object.keys(data.refs)
            .filter(r => r.startsWith('branch:'))
            .map(r => r.replace('branch:', ''));
            
        const branchListHtml = branches.map(b => 
            `<div class="p-3 hover:bg-cyan-900/40 cursor-pointer text-cyan-400 font-bold border-b border-gray-800 transition-colors flex items-center" onclick="App.executeCheckout('${b}')">
                <i class="fa-solid fa-code-branch mr-3 opacity-50"></i> ${b}
             </div>`
        ).join('');

        const modalHtml = `
            <div id="branch-modal" class="fixed inset-0 bg-black/80 flex items-center justify-center z-[100] animate-in fade-in duration-200">
                <div class="bg-gray-900 border border-gray-700 rounded-xl w-96 overflow-hidden shadow-2xl flex flex-col">
                    <div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center">
                        <h3 class="font-bold text-white uppercase text-xs tracking-widest"><i class="fa-solid fa-code-branch text-cyan-500 mr-2"></i> Switch Branch</h3>
                        <button onclick="document.getElementById('branch-modal').remove()" class="text-gray-400 hover:text-white transition-colors"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="max-h-64 overflow-y-auto bg-[#030712]">
                        ${branchListHtml || '<div class="p-4 text-gray-500 text-center">No branches found</div>'}
                    </div>
                    <div class="p-4 bg-gray-950 border-t border-gray-800">
                        <input type="text" id="new-branch-input" placeholder="New branch name..." class="w-full bg-gray-900 border border-gray-700 rounded p-2 text-white text-sm mb-3 focus:border-cyan-500 outline-none">
                        <button onclick="App.createAndCheckoutBranch()" class="w-full bg-cyan-700 hover:bg-cyan-600 text-white rounded p-2 font-bold transition-all shadow-lg">Create & Checkout</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async executeCheckout(branch) {
        document.getElementById('branch-modal')?.remove();
        const res = await this.api('/api/branch/checkout', 'POST', { branch: branch });
        if (res && res.status === 'success') { 
            this.toast(`Checked out ${branch}`); 
            await this.syncWorkspace(); 
            if(this.state.tab === 'code') this.loadTree(); 
        }
    },
    
    async createAndCheckoutBranch() {
        const branchName = document.getElementById('new-branch-input').value.trim();
        if (!branchName) return this.toast("Branch name required", true);
        document.getElementById('branch-modal')?.remove();
        const res = await this.api('/api/branch/create', 'POST', { name: branchName });
        if (res && res.status === 'success') {
            this.executeCheckout(branchName);
        }
    },

    /* --- GRAPH MODULE (PINNACLE TOPOLOGY) --- */
    async loadRefsSidebar() {
        const data = await this.api('/api/graph');
        if (!data) return;
        let html = '<div class="space-y-2">';
        let hasRefs = false;
        for (const [ref, sha] of Object.entries(data.refs || {})) {
            if (ref === "HEAD") continue;
            hasRefs = true;
            const isBranch = ref.startsWith('branch:');
            const name = ref.replace('branch:', '').replace('tag:', '');
            const typeIcon = isBranch ? 'fa-code-branch' : 'fa-tag';
            const typeColor = isBranch ? 'text-cyan-400' : 'text-amber-400';
            html += `<div class="bg-gray-800/50 p-2 rounded flex justify-between items-center border border-gray-700 hover:border-gray-600 transition-colors">
                <span class="font-bold ${typeColor} cursor-pointer text-xs" onclick="App.executeCheckout('${name}')"><i class="fa-solid ${typeIcon} mr-1"></i> ${name}</span>
                <i class="fa-solid fa-code-merge text-gray-500 hover:text-green-400 cursor-pointer text-xs transition-colors" title="Merge into current" onclick="App.triggerMerge('${name}')"></i>
            </div>`;
        }
        document.getElementById('sidebar-content').innerHTML = hasRefs ? (html + '</div>') : '<div class="text-gray-500 text-center p-4">No refs found</div>';
    },

    async loadGraph() {
        const data = await this.api('/api/graph');
        if (!data || !data.commits) return;

        let nodes = new vis.DataSet(); let edges = new vis.DataSet(); let refsMap = {};
        for (const [ref, sha] of Object.entries(data.refs || {})) {
            if (!refsMap[sha]) refsMap[sha] = [];
            refsMap[sha].push(ref.replace('branch:', '').replace('tag:', ''));
        }

        data.commits.forEach((c, i) => {
            let label = c.sha.substring(0,7);
            let color = { background: '#1f2937', border: '#374151' };
            if (refsMap[c.sha]) {
                label = refsMap[c.sha].join(', ') + '\n' + label;
                color = { background: '#0891b2', border: '#06b6d4' };
            } else if (i === 0) {
                color = { background: '#4f46e5', border: '#6366f1' };
            }
            nodes.add({ id: c.sha, label: label, shape: 'box', color, font: { color: 'white', face: 'monospace', size: 10 }, margin: 10 });
            if (c.parents) c.parents.forEach(p => edges.add({ from: c.sha, to: p, color: '#4b5563', arrows: 'to' }));
        });

        const container = document.getElementById('network-canvas');
        if (this.state.graphInstance) this.state.graphInstance.destroy();
        
        const options = {
            layout: { hierarchical: { direction: "UD", sortMethod: "directed", nodeSpacing: 250, levelSeparation: 120, treeSpacing: 250 } },
            physics: { enabled: true, hierarchicalRepulsion: { nodeDistance: 200, springLength: 120, damping: 0.05 }, stabilization: { iterations: 150, fit: true } },
            interaction: { hover: true, dragNodes: true, zoomView: true },
            edges: { smooth: { type: 'cubicBezier', forceDirection: 'vertical', roundness: 0.4 } }
        };
        
        this.state.graphInstance = new vis.Network(container, { nodes, edges }, options);
        this.state.graphInstance.once("stabilizationIterationsDone", () => {
            this.state.graphInstance.setOptions({ physics: { enabled: false } });
        });

        this.state.graphInstance.on("click", (p) => {
            if (p.nodes.length > 0) {
                const c = data.commits.find(x => x.sha === p.nodes[0]);
                if (c) {
                    document.getElementById('cc-sha').textContent = c.sha.substring(0,8);
                    document.getElementById('cc-author').textContent = c.author;
                    document.getElementById('cc-msg').textContent = c.message;
                    document.getElementById('commit-card').classList.remove('hidden');
                }
            }
        });
    },

    /* --- DIFF MODULE --- */
    async loadDiffSidebar() {
        const data = await this.api('/api/status');
        if (!data) return;
        let html = '<div class="text-[10px] space-y-4">';
        if (data.modified?.length) html += `<div><div class="text-yellow-400 font-bold mb-1 tracking-tighter uppercase">Modified</div>` + data.modified.map(f => `<div class="ml-2 mb-1 truncate text-gray-400"><i class="fa-solid fa-circle-dot mr-1 opacity-50"></i>${f}</div>`).join('') + `</div>`;
        if (data.untracked?.length) html += `<div><div class="text-green-400 font-bold mb-1 tracking-tighter uppercase">Untracked</div>` + data.untracked.map(f => `<div class="ml-2 mb-1 truncate text-gray-400"><i class="fa-solid fa-plus mr-1 opacity-50"></i>${f}</div>`).join('') + `</div>`;
        if (data.deleted?.length) html += `<div><div class="text-red-400 font-bold mb-1 tracking-tighter uppercase">Deleted</div>` + data.deleted.map(f => `<div class="ml-2 mb-1 truncate text-gray-400"><i class="fa-solid fa-minus mr-1 opacity-50"></i>${f}</div>`).join('') + `</div>`;
        document.getElementById('sidebar-content').innerHTML = html || '<div class="text-gray-500 text-center p-4">Working tree clean</div>';
    },

    async loadDiffContent() {
        const data = await this.api('/api/diff');
        const container = document.getElementById('diff-content');
        if (!data || !data.diff) { container.innerHTML = "<div class='flex flex-col items-center justify-center h-64 text-gray-600'><i class='fa-solid fa-mug-hot text-4xl mb-4 opacity-20'></i>Working tree clean.</div>"; return; }
        
        let html = '';
        data.diff.split('\n').forEach(line => {
            if (line.startsWith('+') && !line.startsWith('+++')) html += `<div class="text-green-400 bg-green-900/10 px-1 border-l-2 border-green-700">${line}</div>`;
            else if (line.startsWith('-') && !line.startsWith('---')) html += `<div class="text-red-400 bg-red-900/10 px-1 border-l-2 border-red-700">${line}</div>`;
            else if (line.startsWith('@@')) html += `<div class="text-cyan-500 mt-2 font-bold opacity-60">${line}</div>`;
            else if (line.startsWith('diff') || line.startsWith('---') || line.startsWith('+++')) html += `<div class="text-amber-500 font-bold bg-[#030712] py-0.5 mt-2">${line}</div>`;
            else html += `<div class="opacity-80">${line}</div>`;
        });
        container.innerHTML = html;
    },

    /* --- PR & ISSUES (PINNACLE CRUD) --- */
    async loadPRs() {
        const data = await this.api('/api/prs/local');
        const container = document.getElementById('prs-content');
        if (!data || !data.prs || data.prs.length === 0) { container.innerHTML = "<div class='flex flex-col items-center justify-center h-64 text-gray-600'><i class='fa-solid fa-code-pull-request text-4xl mb-4 opacity-20'></i>No local PRs found.</div>"; return; }
        
        let html = '';
        data.prs.forEach(pr => {
            const color = pr.status === "merged" ? "text-green-400" : pr.status === "closed" ? "text-red-400" : "text-amber-400";
            html += `<div class="bg-gray-900/40 p-4 rounded-xl border border-gray-800 hover:border-cyan-500/50 transition-all cursor-pointer shadow-sm group" onclick="App.showPRDetails(${pr.id})">
                <div class="flex justify-between items-start mb-2">
                    <span class="font-bold text-gray-100 italic group-hover:text-cyan-400 transition-colors">#${pr.id} <span class="not-italic text-sm text-gray-100">${pr.title}</span></span>
                    <span class="font-mono text-[10px] uppercase font-black ${color} bg-black/40 px-2 py-1 rounded border border-gray-700">${pr.status}</span>
                </div>
                <div class="text-gray-500 text-[13px] mb-3 leading-relaxed">${pr.body || 'No description provided.'}</div>
                <div class="flex gap-3 text-xs font-mono text-cyan-400 bg-black/30 w-fit px-2 py-1 rounded border border-gray-800">
                    <span>${pr.head}</span> <i class="fa-solid fa-arrow-right text-gray-700 mx-1"></i> <span>${pr.base}</span>
                </div>
            </div>`;
        });
        container.innerHTML = html;
    },

    async showPRDetails(prId) {
        const data = await this.api(`/api/prs/local`);
        if(!data || !data.prs) return;
        const pr = data.prs.find(p => p.id == prId);
        if(!pr) return;

        // Count approvals (author -> status)
        let approvals = 0;
        let reviewsHtml = '';
        if (pr.reviews) {
            for (const [author, r] of Object.entries(pr.reviews)) {
                if (r.status === 'APPROVED') approvals++;
                reviewsHtml += `<div class="bg-gray-900 p-3 rounded border border-gray-700 mb-2">
                    <span class="font-black text-[10px] uppercase px-1.5 py-0.5 rounded border ${r.status === 'APPROVED' ? 'text-green-400 border-green-900 bg-green-900/10' : 'text-yellow-400 border-yellow-900 bg-yellow-900/10'} mr-2">${r.status}</span> 
                    <span class="text-gray-300 font-bold text-sm">${author}</span>
                    <p class="text-gray-400 text-sm mt-1 ml-[70px] italic underline decoration-gray-800 underline-offset-4">${r.comment || 'no comment'}</p>
                </div>`;
            }
        } else {
            reviewsHtml = '<div class="text-gray-500 italic text-sm text-center p-4">No reviews yet.</div>';
        }

        const isApproved = approvals >= (pr.approvals_required || 1);

        const modalHtml = `
            <div id="pr-detail-modal" class="fixed inset-0 bg-black/90 flex items-center justify-center z-[100] animate-in fade-in duration-300">
                <div class="bg-[#0b0f19] border border-gray-800 rounded-2xl w-[800px] max-h-[90vh] overflow-hidden shadow-[0_0_50px_rgba(0,0,0,0.5)] flex flex-col">
                    <div class="p-6 border-b border-gray-800 bg-[#030712] flex justify-between items-start">
                        <div>
                            <div class="text-cyan-500 text-[10px] font-black uppercase tracking-[0.2em] mb-1">Pull Request Detail</div>
                            <h2 class="text-2xl font-black text-white mb-2 tracking-tight">#${pr.id} ${pr.title}</h2>
                            <div class="flex gap-2 items-center">
                                <span class="text-[11px] font-mono text-cyan-400 bg-cyan-900/20 px-2 py-0.5 rounded border border-cyan-800">${pr.head}</span>
                                <i class="fa-solid fa-arrow-right text-gray-700 text-xs"></i>
                                <span class="text-[11px] font-mono text-gray-400 bg-gray-900 px-2 py-0.5 rounded border border-gray-800">${pr.base}</span>
                            </div>
                        </div>
                        <button onclick="document.getElementById('pr-detail-modal').remove()" class="text-gray-500 hover:text-white transition-all hover:rotate-90"><i class="fa-solid fa-xmark text-xl"></i></button>
                    </div>
                    
                    <div class="p-8 flex-1 overflow-y-auto space-y-8 scrollbar-hide">
                        <section>
                            <h3 class="text-gray-500 font-black uppercase text-[10px] tracking-widest mb-3 flex items-center"><i class="fa-solid fa-align-left mr-2"></i> Description</h3>
                            <div class="text-gray-300 bg-[#030712] p-5 rounded-xl border border-gray-800/50 leading-relaxed text-sm whitespace-pre-wrap">${pr.body || 'No description provided.'}</div>
                        </section>
                        
                        <section>
                            <h3 class="text-gray-500 font-black uppercase text-[10px] tracking-widest mb-3 flex items-center"><i class="fa-solid fa-comments mr-2"></i> Timeline & Reviews</h3>
                            <div class="space-y-2">${reviewsHtml}</div>
                        </section>
                        
                        <section class="bg-[#030712] p-6 rounded-2xl border border-cyan-900/20 shadow-inner">
                            <h3 class="text-cyan-400 font-black uppercase text-[10px] tracking-widest mb-4">Submit Your Review</h3>
                            <textarea id="review-comment" class="w-full bg-[#0b0f19] border border-gray-800 rounded-xl p-4 text-white mb-4 h-24 focus:border-cyan-500 outline-none placeholder:text-gray-700 text-sm" placeholder="Any thoughts on this code?"></textarea>
                            <div class="flex gap-3">
                                <button onclick="App.submitPRReview(${pr.id}, 'APPROVED')" class="flex-1 bg-green-600 hover:bg-green-500 text-white px-4 py-3 rounded-xl font-black text-xs uppercase tracking-widest transition-all shadow-lg active:scale-95"><i class="fa-solid fa-check mr-2"></i> Approve</button>
                                <button onclick="App.submitPRReview(${pr.id}, 'CHANGES_REQUESTED')" class="flex-1 bg-amber-700 hover:bg-amber-600 text-white px-4 py-3 rounded-xl font-black text-xs uppercase tracking-widest transition-all shadow-lg active:scale-95"><i class="fa-solid fa-xmark mr-2"></i> Request Changes</button>
                            </div>
                        </section>
                    </div>
                    
                    <div class="p-6 bg-[#030712] border-t border-gray-800 flex justify-between items-center">
                        <div class="text-[10px] font-mono text-gray-500 uppercase">
                            Status: <span class="${isApproved ? 'text-green-500' : 'text-amber-500'} font-black">${isApproved ? 'Ready to Merge' : 'Approval Required'}</span>
                        </div>
                        <button onclick="App.mergePR(${pr.id})" class="${isApproved && pr.status === 'open' ? 'bg-purple-600 hover:bg-purple-500 hover:shadow-[0_0_20px_rgba(147,51,234,0.3)]' : 'bg-gray-800 cursor-not-allowed opacity-50'} text-white px-8 py-3 rounded-xl font-black text-xs uppercase tracking-widest transition-all shadow-xl flex items-center group" ${!isApproved || pr.status !== 'open' ? 'disabled' : ''}>
                            <i class="fa-solid fa-code-merge mr-2 group-hover:rotate-12 transition-transform"></i> Merge PR
                        </button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async submitPRReview(prId, state) {
        const comment = document.getElementById('review-comment').value;
        const res = await this.api('/api/pr/review', 'POST', { pr_id: prId, state: state, comment: comment });
        if (res && res.status === 'success') {
            this.toast(`PR ${state}`);
            document.getElementById('pr-detail-modal').remove();
            this.loadPRs();
        }
    },
    
    async mergePR(prId) {
        const res = await this.api('/api/pr/merge', 'POST', { pr_id: prId });
        if (res && res.status === 'success') {
            this.toast(`PR #${prId} Merged!`);
            document.getElementById('pr-detail-modal').remove();
            this.loadPRs();
            this.syncWorkspace();
        }
    },

    async loadIssues() {
        const data = await this.api('/api/issues/local');
        const container = document.getElementById('issues-content');
        if (!data || !data.issues || data.issues.length === 0) { container.innerHTML = "<div class='flex flex-col items-center justify-center h-64 text-gray-600'><i class='fa-regular fa-circle-dot text-4xl mb-4 opacity-20'></i>No local issues found.</div>"; return; }
        let html = '';
        data.issues.forEach(iss => {
            const color = iss.status === "open" ? "text-green-400" : "text-purple-400";
            html += `<div class="bg-gray-800/60 p-4 rounded-xl border border-gray-800 hover:border-green-500/30 transition-all">
                <div class="font-bold text-gray-200 mb-2 flex justify-between">
                    <span><span class="${color} mr-2">[${iss.status.toUpperCase()}]</span> #${iss.id} ${iss.title}</span>
                    <span class="text-[10px] text-gray-600 font-mono">${iss.created_at.split('T')[0]}</span>
                </div>
                <div class="text-gray-500 text-sm italic">${iss.description || 'No additional details.'}</div>
            </div>`;
        });
        container.innerHTML = html;
    },

    async create_issue_action() {
        const title = document.getElementById('new-issue-title').value.trim();
        const body = document.getElementById('new-issue-body').value.trim();
        if (!title) return this.toast("Title required", true);
        const res = await this.api('/api/issue/create', 'POST', { title, body, type: 'task' });
        if (res && res.status === 'success') {
            this.toast(`Issue #${res.id} Created!`);
            document.getElementById('issue-create-modal').remove();
            this.loadIssues();
        }
    },

    showCreatePRModal() {
        const modalHtml = `
            <div id="pr-create-modal" class="fixed inset-0 bg-black/80 flex items-center justify-center z-[100] animate-in fade-in duration-200">
                <div class="bg-gray-900 border border-gray-700 rounded-xl w-[500px] overflow-hidden shadow-2xl flex flex-col">
                    <div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center">
                        <h3 class="font-bold text-white uppercase text-xs tracking-widest">Create Pull Request</h3>
                        <button onclick="document.getElementById('pr-create-modal').remove()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="p-6 space-y-4">
                        <input type="text" id="new-pr-title" placeholder="PR Title..." class="w-full bg-gray-950 border border-gray-800 rounded p-2 text-white">
                        <textarea id="new-pr-body" placeholder="Description..." class="w-full bg-gray-950 border border-gray-800 rounded p-2 text-white h-24"></textarea>
                        <div class="flex gap-2">
                            <input type="text" id="new-pr-head" value="${this.state.workspace.branch}" class="flex-1 bg-gray-950 border border-gray-800 rounded p-2 text-cyan-400 font-mono text-xs" readonly>
                            <i class="fa-solid fa-arrow-right self-center text-gray-600"></i>
                            <input type="text" id="new-pr-base" value="main" class="flex-1 bg-gray-950 border border-gray-800 rounded p-2 text-gray-400 font-mono text-xs">
                        </div>
                        <button onclick="App.create_pr_action()" class="w-full bg-purple-600 hover:bg-purple-500 text-white rounded p-3 font-black text-xs uppercase tracking-widest shadow-lg">Submit Pull Request</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async create_pr_action() {
        const title = document.getElementById('new-pr-title').value.trim();
        const body = document.getElementById('new-pr-body').value.trim();
        const head = document.getElementById('new-pr-head').value.trim();
        const base = document.getElementById('new-pr-base').value.trim();
        if (!title) return this.toast("Title required", true);
        const res = await this.api('/api/pr/create', 'POST', { title, body, head, base });
        if (res && res.status === 'success') {
            this.toast(`PR #${res.id} Created!`);
            document.getElementById('pr-create-modal').remove();
            this.loadPRs();
        }
    },

    showCreateIssueModal() {
        const modalHtml = `
            <div id="issue-create-modal" class="fixed inset-0 bg-black/80 flex items-center justify-center z-[100] animate-in fade-in duration-200">
                <div class="bg-gray-900 border border-gray-700 rounded-xl w-[500px] overflow-hidden shadow-2xl flex flex-col">
                    <div class="p-4 bg-gray-800 border-b border-gray-700 flex justify-between items-center">
                        <h3 class="font-bold text-white uppercase text-xs tracking-widest">Create New Issue</h3>
                        <button onclick="document.getElementById('issue-create-modal').remove()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="p-6 space-y-4">
                        <input type="text" id="new-issue-title" placeholder="Issue Title..." class="w-full bg-gray-950 border border-gray-800 rounded p-2 text-white">
                        <textarea id="new-issue-body" placeholder="What's the problem?" class="w-full bg-gray-950 border border-gray-800 rounded p-2 text-white h-32"></textarea>
                        <button onclick="App.create_issue_action()" class="w-full bg-green-600 hover:bg-green-500 text-white rounded p-3 font-black text-xs uppercase tracking-widest shadow-lg">Create Issue</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    /* --- GIT ACTION HELPERS --- */
    async triggerMerge(branchName) {
        if (!confirm(`Merge ${branchName} into current branch?`)) return;
        const res = await this.api('/api/merge', 'POST', { branch: branchName });
        if (res && res.status === 'success') { this.toast(`Merged ${branchName}`); this.syncWorkspace(); this.loadGraph(); }
    }
};

window.onload = () => App.init();
