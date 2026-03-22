const EditorEngine = {
    editor: null,
    openTabs: [], // Array of filepaths
    activeTab: null,
    selectedPath: null,
    selectedIsDir: false,
    treeData: [], // Cached flat list for search
    expandedFolders: new Set(), // Track open folders
    dialogType: null,
    dirtyTabs: [], 
    splitEditorInstance: null,
    isSplit: false,
    activePane: 'main', // 'main' or 'split'
    models: {}, // Cache Monaco models by filepath
    contextMenuTarget: null,

    saveState() {
        localStorage.setItem('deep_editor_tabs', JSON.stringify(this.openTabs));
        localStorage.setItem('deep_editor_active', this.activeTab || '');
        localStorage.setItem('deep_editor_split', this.isSplit);
    },

    restoreState() {
        try {
            const tabs = JSON.parse(localStorage.getItem('deep_editor_tabs'));
            const active = localStorage.getItem('deep_editor_active');
            const split = localStorage.getItem('deep_editor_split') === 'true';
            
            if (split) {
                this.isSplit = true;
                const splitDiv = document.getElementById('monaco-host-split');
                if(splitDiv) splitDiv.classList.remove('hidden');
            }

            if (tabs && tabs.length > 0) {
                this.openTabs = tabs;
                if (active) this.openFile(active);
                else this.openFile(tabs[0]);
            }
        } catch (e) { console.error("Failed to restore editor state", e); }
    },
    
    init() {
        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.36.1/min/vs' }});
        require(['vs/editor/editor.main'], () => {
            // Boot Language Engine First
            LanguageEngine.init();

            this.editor = monaco.editor.create(document.getElementById('monaco-host'), {
                value: "// Welcome to DeepStudio IDE\n// Select a file to begin.",
                theme: 'vs-dark', 
                language: 'plaintext',
                automaticLayout: true,
                minimap: { enabled: true, renderCharacters: false, scale: 0.7 },
                bracketPairColorization: { enabled: true, independentColorPoolPerBracketType: true },
                guides: { indentation: true, bracketPairs: true, highlightActiveIndentation: true },
                fontFamily: "'Fira Code', 'Consolas', monospace",
                fontLigatures: true,
                fontSize: 13,
                tabSize: 4,
                insertSpaces: true,
                smoothScrolling: true,
                cursorBlinking: "smooth",
                cursorSmoothCaretAnimation: "on",
                renderWhitespace: "boundary",
                scrollBeyondLastLine: false,
                formatOnPaste: true,
                suggest: { snippetsPreventQuickSuggestions: false }
            });

            // FIX: Initialize the Split Editor Instance
            this.splitEditorInstance = monaco.editor.create(document.getElementById('monaco-host-split'), {
                value: "// Split View",
                theme: 'vs-dark',
                readOnly: true,
                automaticLayout: true,
                minimap: { enabled: false } // Save space in split view
            });

            // Focus Tracking
            this.editor.onDidFocusEditorWidget(() => { this.activePane = 'main'; });
            this.splitEditorInstance.onDidFocusEditorWidget(() => { this.activePane = 'split'; });

            // Bind Ctrl+S to Save
            this.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => { this.saveActiveFile(); });
            this.splitEditorInstance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => { this.saveActiveFile(); });
            
            // Auto Outline parsing on change (Debounced)
            let timeout;
            this.editor.onDidChangeModelContent(async () => {
                const model = this.editor.getModel();
                if (this.activeTab && !this.dirtyTabs.includes(this.activeTab)) {
                    this.dirtyTabs.push(this.activeTab);
                    this.renderTabs(); // Show the ● dot
                }
                clearTimeout(timeout);
                timeout = setTimeout(async () => {
                    this.parseOutline();
                    
                    // Live Diagnostics / Linting (Level 2)
                    if (model && model.getLanguageId() === 'python') {
                        const res = await App.api('/api/language/analyze', 'POST', { code: model.getValue(), language: 'python' });
                        if (res && res.diagnostics) {
                            const markers = res.diagnostics.map(d => ({
                                severity: d.severity,
                                startLineNumber: d.line,
                                startColumn: d.column || 1,
                                endLineNumber: d.line,
                                endColumn: (d.column || 1) + 5,
                                message: d.message
                            }));
                            monaco.editor.setModelMarkers(model, 'flake8', markers);
                        }
                    }
                }, 1000);
            });
            this.editor.onDidChangeCursorPosition((e) => {
                const el = document.getElementById('editor-status-cursor');
                if(el) el.textContent = `Ln ${e.position.lineNumber}, Col ${e.position.column}`;
            });
            
            // Global Hotkeys
            document.addEventListener('keydown', (e) => {
                if (e.ctrlKey && e.key === '\\') { e.preventDefault(); this.toggleSplit(); }
                if (e.ctrlKey && e.key === '1') { e.preventDefault(); this.editor.focus(); }
                if (e.ctrlKey && e.key === '2' && this.isSplit) { e.preventDefault(); this.splitEditorInstance.focus(); }
            });
            
            this.loadTree();
            this.updateMetrics();
            setInterval(() => this.updateMetrics(), 3000);
            this.restoreState(); // Restore user layout
        });

        // Command Palette Hotkey (Ctrl+P)
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'p') {
                e.preventDefault();
                const cp = document.getElementById('editor-command-palette');
                cp.classList.toggle('hidden');
                if(!cp.classList.contains('hidden')) document.getElementById('cmd-input').focus();
            }
        });
    },

    async loadTree() {
        // Fetch files and git status concurrently
        const [treeRes, statusRes] = await Promise.all([
            App.api('/api/tree'),
            App.api('/api/status') // From existing backend
        ]);
        
        if (!treeRes || !treeRes.tree) return;
        
        const modified = statusRes ? (statusRes.modified || []) : [];
        const untracked = statusRes ? (statusRes.untracked || []) : [];
        
        this.treeData = []; // Reset flat cache for search

        const renderNode = (nodeMap, name, pathPrefix = "") => {
            const node = nodeMap[name];
            const isDir = node._type === 'dir';
            const fullPath = node.path || (pathPrefix + name);
            
            if (!isDir) this.treeData.push({ name, path: fullPath });

            // VS Code Git Colors
            let colorClass = "text-slate-300";
            let badge = "";

            if (isDir) {
                // Bubble up git status from children to parent folders
                let dirHasUntracked = untracked.some(p => p.startsWith(fullPath + '/'));
                let dirHasModified = modified.some(p => p.startsWith(fullPath + '/'));
                
                if (dirHasUntracked && !dirHasModified) { colorClass = "text-[#73c991]"; } // Green
                else if (dirHasModified) { colorClass = "text-[#e2c08d]"; } // Yellow
                const isOpen = this.expandedFolders.has(fullPath);
                let childrenHtml = Object.keys(node.children)
                    .sort((a,b) => node.children[a]._type === 'dir' ? -1 : 1) // Folders first
                    .map(k => renderNode(node.children, k, fullPath + "/")).join('');
                    
                // FIX: Add logic to toggle the Set on click
                return `
                <div class="ml-2">
                    <div class="flex items-center py-[2px] px-1 cursor-pointer hover:bg-slate-800/50 group rounded transition-colors ${this.selectedPath === fullPath ? 'bg-slate-800' : ''}" 
                         onclick="
                            const childDiv = this.nextElementSibling;
                            childDiv.classList.toggle('hidden');
                            const icon = this.querySelector('.fa-chevron-right');
                            icon.style.transform = childDiv.classList.contains('hidden') ? '' : 'rotate(90deg)';
                            EditorEngine.selectNode('${fullPath}', true, event);
                         "
                         oncontextmenu="event.preventDefault(); event.stopPropagation(); EditorEngine.contextMenuTarget = '${fullPath}'; const cm = document.getElementById('context-menu'); cm.classList.remove('hidden'); cm.style.left = event.pageX + 'px'; cm.style.top = event.pageY + 'px';">
                        <i class="fa-solid fa-chevron-right text-[10px] text-slate-500 mr-1 group-hover:text-white transition-transform" style="transform: ${isOpen ? 'rotate(90deg)' : ''}"></i>
                        <i class="fa-solid ${isOpen ? 'fa-folder-open' : 'fa-folder'} ${colorClass !== 'text-slate-300' ? colorClass : 'text-cyan-500'} mr-1.5 w-4 text-center"></i>
                        <span class="${colorClass !== 'text-slate-300' ? colorClass : 'text-slate-300'} truncate group-hover:text-white transition-colors">${name}</span>
                    </div>
                    <div class="${isOpen ? '' : 'hidden'} border-l border-slate-700/50 ml-2 shadow-inner">${childrenHtml}</div>
                </div>`;
            } else {
                if (untracked.includes(fullPath)) { colorClass = "text-[#73c991]"; badge = "U"; } // Green
                else if (modified.includes(fullPath)) { colorClass = "text-[#e2c08d]"; badge = "M"; } // Yellow

                // File Icon logic
                const ext = name.split('.').pop().toLowerCase();
                const icon = ext==='py'?'fa-brands fa-python text-[#3776ab]':ext==='js'?'fa-brands fa-js text-[#f1e05a]':ext==='html'?'fa-brands fa-html5 text-[#e34c26]':'fa-regular fa-file-code text-[#cccccc]';

                return `
                <div class="ml-2 flex items-center justify-between py-[2px] px-1 cursor-pointer group rounded transition-colors ${this.selectedPath === fullPath ? 'bg-cyan-900/40 text-cyan-50' : (this.activeTab === fullPath ? 'bg-slate-800/50 text-slate-200' : 'hover:bg-slate-800/50')}" 
                     onclick="EditorEngine.selectNode('${fullPath}', false, event)"
                     oncontextmenu="event.preventDefault(); event.stopPropagation(); EditorEngine.contextMenuTarget = '${fullPath}'; const cm = document.getElementById('context-menu'); cm.classList.remove('hidden'); cm.style.left = event.pageX + 'px'; cm.style.top = event.pageY + 'px';">
                    <div class="flex items-center truncate">
                        <i class="${icon} mr-1.5 w-4 text-center"></i>
                        <span class="${colorClass} truncate">${name}</span>
                    </div>
                    ${badge ? `<span class="text-[9px] font-bold ${colorClass} opacity-80 pr-1">${badge}</span>` : ''}
                </div>`;
            }
        };

        let html = Object.keys(treeRes.tree)
            .sort((a,b) => treeRes.tree[a]._type === 'dir' ? -1 : 1)
            .map(k => renderNode(treeRes.tree, k)).join('');
            
        document.getElementById('editor-tree').innerHTML = html;
    },    async openFile(path) {
        if (!this.editor) return App.toast("Editor initializing...", true);
        
        if (!this.openTabs.includes(path)) this.openTabs.push(path);
        this.activeTab = path;
        
        this.renderTabs();
        this.loadTree(); // Re-render to highlight active file
        this.saveState();
        
        const bc = document.getElementById('editor-breadcrumbs');
        if(bc) bc.innerHTML = path.split('/').map(p => `<span>${p}</span>`).join(' <i class="fa-solid fa-chevron-right text-[8px] mx-1"></i> ');

        // Retrieve or create Monaco Model
        let model = this.models[path];
        if (!model) {
            const data = await App.api(`/api/file?path=${encodeURIComponent(path)}`);
            if (!data) return;
            const content = data.isBinary ? `// Binary file\n// ${data.content}` : data.content;
            const langId = LanguageEngine.getLangFromExt(path);
            model = monaco.editor.createModel(content, langId, monaco.Uri.file(path));
            this.models[path] = model;
        }

        // Apply Model to the currently active pane
        if (this.activePane === 'split' && this.isSplit) {
            this.splitEditorInstance.setModel(model);
            this.splitEditorInstance.updateOptions({ readOnly: model.getValue().startsWith('// Binary file') });
        } else {
            this.editor.setModel(model);
            this.editor.updateOptions({ readOnly: model.getValue().startsWith('// Binary file') });
        }
        
        this.parseOutline();
    },

    async saveActiveFile() {
        if (!this.activeTab || !this.models[this.activeTab]) return;
        const content = this.models[this.activeTab].getValue();
        const res = await App.api('/api/file/save', 'POST', { filepath: this.activeTab, content });
        if (res && res.status === 'success') {
            App.toast(`Saved: ${this.activeTab}`);
            this.dirtyTabs = this.dirtyTabs.filter(t => t !== this.activeTab);
            this.renderTabs();
            this.loadTree();
        }
    },

    renderTabs() {
        const container = document.getElementById('editor-tabs');
        if(!container) return;
        container.innerHTML = this.openTabs.map(tab => {
            const filename = tab.split('/').pop();
            const isActive = tab === this.activeTab;
            const isDirty = this.dirtyTabs.includes(tab);
            const bg = isActive ? 'bg-slate-900 shadow-inner border-t-2 border-t-cyan-500 text-cyan-50' : 'bg-slate-950 text-slate-400 hover:bg-slate-900/50 hover:text-slate-300 border-t-2 border-transparent';
            
            return `
            <div class="${bg} px-4 py-2 text-[12px] font-sans cursor-pointer flex items-center gap-2 border-r border-slate-800 shrink-0 group transition-all" onclick="EditorEngine.openFile('${tab}')">
                <span class="${isDirty ? 'italic' : ''}">${filename}</span>
                <div class="flex items-center justify-center w-5 h-5 hover:bg-slate-800 rounded transition-colors" onclick="event.stopPropagation(); EditorEngine.closeTab('${tab}')">
                    ${isDirty 
                        ? `<span class="text-[8px] text-cyan-400 group-hover:hidden">●</span><i class="fa-solid fa-xmark text-[10px] hidden group-hover:block"></i>`
                        : `<i class="fa-solid fa-xmark text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"></i>`
                    }
                </div>
            </div>`;
        }).join('');
    },

    closeTab(path) {
        if (this.dirtyTabs.includes(path)) {
            if (!confirm(`You have unsaved changes in ${path.split('/').pop()}.\nDo you want to close without saving?`)) return;
            this.dirtyTabs = this.dirtyTabs.filter(t => t !== path);
        }
        
        this.openTabs = this.openTabs.filter(t => t !== path);
        this.saveState();
        if (this.activeTab === path) {
            if (this.openTabs.length > 0) this.openFile(this.openTabs[0]);
            else {
                this.activeTab = null;
                this.editor.setValue("// No file open");
                this.renderTabs();
            }
        } else this.renderTabs();
    },

    filterTree(query) {
        // Quick local fallback search
        if(!query) return this.loadTree();
        const results = this.treeData.filter(f => f.name.toLowerCase().includes(query.toLowerCase()));
        document.getElementById('editor-tree').innerHTML = results.map(f => `
            <div class="ml-2 flex items-center py-1 cursor-pointer hover:bg-[#2a2d2e] text-[#cccccc]" onclick="EditorEngine.openFile('${f.path}')">
                <i class="fa-regular fa-file-code mr-1.5 w-4 text-center"></i> <span class="truncate">${f.path}</span>
            </div>
        `).join('');
    },

    handleCommandPalette(query) {
        if(!query) return;
        const results = this.treeData.filter(f => f.name.toLowerCase().includes(query.toLowerCase())).slice(0,10);
        document.getElementById('cmd-results').innerHTML = results.map(f => `
            <div class="p-3 hover:bg-[#0060a0] cursor-pointer text-white border-b border-[#333]" onclick="EditorEngine.openFile('${f.path}'); document.getElementById('editor-command-palette').classList.add('hidden')">
                <div class="font-bold">${f.name}</div>
                <div class="text-xs text-gray-400">${f.path}</div>
            </div>
        `).join('');
    },

    parseOutline() {
        const code = this.editor.getValue();
        document.getElementById('editor-outline-container').classList.remove('hidden');
        
        let outlineHtml = '';
        // Very basic regex parsing for Python & JS functions/classes for the Outline view
        const lines = code.split('\n');
        lines.forEach((line, idx) => {
            if (line.match(/^\s*(def|class|function)\s+\w+/)) {
                const name = line.replace(/^\s*(def|class|function)\s+/, '').split('(')[0].split(':')[0];
                const type = line.includes('class') ? 'fa-cube text-orange-400' : 'fa-box text-purple-400';
                outlineHtml += `<div class="text-[#cccccc] text-[11px] py-1 cursor-pointer hover:bg-[#2a2d2e] flex items-center px-2 truncate" onclick="EditorEngine.editor.revealLine(${idx + 1})"><i class="fa-solid ${type} w-4 mr-1"></i> ${name}</div>`;
            }
        });
        document.getElementById('editor-outline').innerHTML = outlineHtml || '<div class="text-[#858585] text-[10px] p-2">No symbols found.</div>';
    },

    async updateMetrics() {
        const ws = App.state.workspace;
        const elBranch = document.getElementById('editor-status-branch');
        if(elBranch) elBranch.textContent = ws.branch || 'main';
        try {
            const diffRes = await App.api('/api/diff');
            if (diffRes && diffRes.diff) {
                let add = 0, del = 0;
                diffRes.diff.split('\n').forEach(line => {
                    if (line.startsWith('+') && !line.startsWith('+++')) add++;
                    else if (line.startsWith('-') && !line.startsWith('---')) del++;
                });
                const elAdd = document.getElementById('editor-status-add');
                const elDel = document.getElementById('editor-status-del');
                if(elAdd) elAdd.textContent = add;
                if(elDel) elDel.textContent = del;
            }
        } catch(e){}
    },

    toggleFolder(path) {
        if (this.expandedFolders.has(path)) this.expandedFolders.delete(path);
        else this.expandedFolders.add(path);
    },

    selectNode(path, isDir, event) {
        if(event) event.stopPropagation();
        this.selectedPath = path;
        this.selectedIsDir = isDir;
        if(isDir) this.toggleFolder(path);
        else this.openFile(path);
        this.loadTree();
    },

    clearSelection() {
        if (this.selectedPath !== null) {
            this.selectedPath = null;
            this.selectedIsDir = false;
            this.loadTree();
        }
    },

    promptCreate(type) {
        this.dialogType = type;
        
        let base = '';
        if (this.selectedPath) {
            base = this.selectedIsDir ? this.selectedPath : this.selectedPath.substring(0, this.selectedPath.lastIndexOf('/'));
        } else if (this.activeTab) {
            base = this.activeTab.substring(0, this.activeTab.lastIndexOf('/'));
        }
        
        document.getElementById('editor-dialog-base').textContent = base ? `${base}/` : '/';
        document.getElementById('editor-dialog-title').innerHTML = `<i class="fa-solid ${type === 'folder' ? 'fa-folder-plus text-[#dcb67a]' : 'fa-file-medical text-cyan-400'}"></i> New ${type === 'folder' ? 'Folder' : 'File'}`;
        document.getElementById('editor-dialog-input').placeholder = type === 'folder' ? 'e.g. src/components' : 'e.g. main.js';
        document.getElementById('editor-dialog-input').value = '';
        document.getElementById('editor-dialog').classList.remove('hidden');
        document.getElementById('editor-dialog-input').focus();
    },

    closeDialog() {
        document.getElementById('editor-dialog').classList.add('hidden');
    },

    async confirmDialog() {
        const input = document.getElementById('editor-dialog-input').value.trim();
        if(!input) return;
        
        let base = '';
        if (this.selectedPath) {
            base = this.selectedIsDir ? this.selectedPath : this.selectedPath.substring(0, this.selectedPath.lastIndexOf('/'));
        } else if (this.activeTab) {
            base = this.activeTab.substring(0, this.activeTab.lastIndexOf('/'));
        }
        const fullPath = (base ? base + '/' : '') + input;
        
        document.getElementById('editor-dialog-input').disabled = true;
        
        try {
            const res = await App.api('/api/item/create', 'POST', { path: fullPath, type: this.dialogType });
            if(res) {
                if (this.dialogType === 'folder') this.expandedFolders.add(fullPath);
                await this.loadTree();
                if (this.dialogType === 'file') this.openFile(fullPath);
                this.closeDialog();
            }
        } finally {
            document.getElementById('editor-dialog-input').disabled = false;
        }
    },

    toggleSplit() {
        this.isSplit = !this.isSplit;
        const splitDiv = document.getElementById('monaco-host-split');
        
        if (this.isSplit) {
            splitDiv.classList.remove('hidden');
            splitDiv.classList.add('flex'); // Ensure it participates in flex properly
            this.activePane = 'split'; 
            if(this.activeTab) this.openFile(this.activeTab); 
        } else {
            splitDiv.classList.add('hidden');
            splitDiv.classList.remove('flex');
            this.activePane = 'main';
            this.editor.focus();
        }

        this.saveState();

        // FIX: Double RequestAnimationFrame + Timeout to guarantee flexbox reflow is painted
        // before Monaco attempts to measure its container size.
        window.requestAnimationFrame(() => {
            setTimeout(() => {
                if (this.editor) this.editor.layout();
                if (this.splitEditorInstance) this.splitEditorInstance.layout();
            }, 50);
        });
    },

    ctxCreate(type) {
        const cm = document.getElementById('context-menu');
        if (cm) cm.classList.add('hidden');
        if(!this.contextMenuTarget) return;
        
        // Ensure tree target selection updates properly before prompting
        const isDir = !this.treeData.some(n => n.path === this.contextMenuTarget);
        this.selectNode(this.contextMenuTarget, isDir);
        this.promptCreate(type);
    },

    ctxCopyPath() {
        const cm = document.getElementById('context-menu');
        if (cm) cm.classList.add('hidden');
        if(!this.contextMenuTarget) return;
        navigator.clipboard.writeText(this.contextMenuTarget);
        App.toast("Copied to clipboard!");
    },
    
    ctxRename() {
        const cm = document.getElementById('context-menu');
        if (cm) cm.classList.add('hidden');
        if(!this.contextMenuTarget) return;
        const filename = this.contextMenuTarget.split('/').pop();
        const newName = prompt(`Rename ${filename}:`, filename);
        if(newName) {
            // Using placeholder /api/item/rename endpoint, fallback if missing
            App.api('/api/item/rename', 'POST', { path: this.contextMenuTarget, new_name: newName }).then(() => this.loadTree());
        }
    },
    
    ctxDelete() {
        const cm = document.getElementById('context-menu');
        if (cm) cm.classList.add('hidden');
        if(!this.contextMenuTarget) return;
        if(confirm(`Are you sure you want to permanently delete: ${this.contextMenuTarget}?`)) {
            App.api('/api/item/delete', 'POST', { path: this.contextMenuTarget }).then(() => this.loadTree());
        }
    }
};

const LanguageEngine = {
    // Top 30 Languages Registry
    extMap: {
        'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'java': 'java', 
        'cs': 'csharp', 'cpp': 'cpp', 'cc': 'cpp', 'c': 'c', 'php': 'php', 
        'sql': 'sql', 'go': 'go', 'swift': 'swift', 'kt': 'kotlin', 'rs': 'rust', 
        'rb': 'ruby', 'r': 'r', 'm': 'matlab', 'dart': 'dart', 'scala': 'scala', 
        'm': 'objective-c', 'vb': 'vb', 'sh': 'shell', 'bash': 'shell', 
        'f90': 'fortran', 'cbl': 'cobol', 'jl': 'julia', 'pl': 'perl', 
        'hs': 'haskell', 'lua': 'lua', 'asm': 'assembly', 'groovy': 'groovy', 
        'sol': 'solidity', 'html': 'html', 'css': 'css', 'json': 'json', 'md': 'markdown'
    },

    init() {
        this.setupEditorConfig();
        this.registerProviders();
    },

    getLangFromExt(filename) {
        if (!filename.includes('.')) return 'plaintext';
        const ext = filename.split('.').pop().toLowerCase();
        return this.extMap[ext] || 'plaintext';
    },

    setupEditorConfig() {
        // Level 0 & 3: Auto Closing, Bracket Matching, and Formatting Rules
        monaco.languages.getLanguages().forEach(lang => {
            monaco.languages.setLanguageConfiguration(lang.id, {
                autoClosingPairs: [
                    { open: '{', close: '}' }, { open: '[', close: ']' },
                    { open: '(', close: ')' }, { open: '"', close: '"' },
                    { open: "'", close: "'" }
                ],
                surroundingPairs: [
                    { open: '{', close: '}' }, { open: '[', close: ']' },
                    { open: '(', close: ')' }, { open: '"', close: '"' },
                    { open: "'", close: "'" }
                ],
                bracketColorizationOptions: { enabled: true }
            });
        });
    },

    registerProviders() {
        // FIX: Separate languages into Backend-dependent vs Native Monaco
        // Monaco has built-in perfect formatters for JS, TS, JSON, HTML, CSS. We MUST NOT override them.
        const backendFormatLangs = ['python', 'cpp', 'c', 'java', 'go', 'rust', 'ruby', 'php', 'sql', 'shell'];
        const hoverLangs = [...backendFormatLangs, 'javascript', 'typescript', 'json', 'html', 'css', 'markdown']; 
        
        // 1. Backend Formatting Provider (Shift+Alt+F) ONLY for languages Monaco can't format natively
        backendFormatLangs.forEach(lang => {
            monaco.languages.registerDocumentFormattingEditProvider(lang, {
                async provideDocumentFormattingEdits(model, options, token) {
                    App.toast(`Formatting ${lang}...`);
                    try {
                        const res = await App.api('/api/language/format', 'POST', {
                            code: model.getValue(), language: lang
                        });
                        
                        if (res && res.formatted && res.formatted !== model.getValue()) {
                            return [{
                                range: model.getFullModelRange(),
                                text: res.formatted
                            }];
                        }
                    } catch(e) { console.error("Formatting failed", e); }
                    return [];
                }
            });
        });

        // 2. Generic Hover Provider (Level 4)
        hoverLangs.forEach(lang => {
            monaco.languages.registerHoverProvider(lang, {
                provideHover: function (model, position) {
                    const wordInfo = model.getWordAtPosition(position);
                    if (wordInfo) {
                        return {
                            range: new monaco.Range(position.lineNumber, wordInfo.startColumn, position.lineNumber, wordInfo.endColumn),
                            contents: [
                                { value: `**${wordInfo.word}**` },
                                { value: `*Symbol in ${lang}*` }
                            ]
                        };
                    }
                    return null;
                }
            });
        });

        // 3. Keep the existing Python Jedi bindings (Completion, Definition, Live Linting) below this line!
        monaco.languages.registerCompletionItemProvider('python', {
            triggerCharacters: ['.'],
            async provideCompletionItems(model, position) {
                const res = await App.api('/api/language/complete', 'POST', {
                    code: model.getValue(),
                    line: position.lineNumber,
                    column: position.column
                });
                
                if (res && res.completions) {
                    const word = model.getWordUntilPosition(position);
                    const range = {
                        startLineNumber: position.lineNumber,
                        endLineNumber: position.lineNumber,
                        startColumn: word.startColumn,
                        endColumn: word.endColumn
                    };
                    
                    const suggestions = res.completions.map(c => ({
                        label: c.label,
                        kind: c.kind,
                        insertText: c.insertText,
                        detail: c.detail,
                        documentation: { value: c.documentation },
                        range: range
                    }));
                    return { suggestions };
                }
                return { suggestions: [] };
            }
        });

        // 2. GO TO DEFINITION (Level 1/2)
        monaco.languages.registerDefinitionProvider('python', {
            async provideDefinition(model, position, token) {
                const res = await App.api('/api/language/definition', 'POST', {
                    code: model.getValue(),
                    line: position.lineNumber,
                    column: position.column
                });
                
                if (res && res.definition) {
                    return {
                        uri: model.uri, // Assuming local file definitions for now
                        range: new monaco.Range(res.definition.line, res.definition.column, res.definition.line, res.definition.column + 5)
                    };
                }
            }
        });
    }
};

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

    isModifiedAfterStaging(file, staged, unstaged) {
        return staged.includes(file) && unstaged.includes(file);
    },

    async refreshStatus() {
        await this.syncWorkspace();
    },

    async refreshDiff() {
        await this.loadDiffContent();
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
        if (!el) {
            // Fallback for missing container
            const t = document.createElement('div');
            t.className = `fixed bottom-8 left-1/2 -translate-x-1/2 px-6 py-3 rounded-2xl text-[11px] font-black uppercase tracking-[0.2em] shadow-2xl z-[200] animate-in slide-in-from-bottom-5 duration-300 ${error ? 'bg-red-500 text-white' : 'bg-indigo-600 text-white'}`;
            t.innerHTML = `<i class="fa-solid ${error?'fa-triangle-exclamation':'fa-check-circle'} mr-2"></i> ${msg}`;
            document.body.appendChild(t);
            setTimeout(()=>t.remove(), 4000);
            return;
        }
        el.textContent = msg;
        el.className = `px-4 py-2 rounded shadow-lg border text-sm font-bold ${error ? 'bg-red-900 text-red-100 border-red-700' : 'bg-cyan-900 text-cyan-100 border-cyan-700'}`;
        container.classList.remove('opacity-0');
        setTimeout(() => container.classList.add('opacity-0'), 3000);
    },

    async api(url, method = 'GET', body = null) {
        try {
            const opts = { method, headers: {} };
            if (body) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
            const res = await fetch(url, opts);
            const data = await res.json();
            if (data && data.success === false) throw new Error(data.error || "Operation failed");
            return data.data !== undefined ? data.data : data;
        } catch (e) {
            console.error(`❌ [API Error] ${url}:`, e);
            this.toast(e.message, true);
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
        
        // Show/Hide Pop Stash button if we have stashes (simplified check: always show if we ever stashed)
        const popBtn = document.getElementById('btn-pop-stash');
        if (popBtn) popBtn.classList.remove('hidden');
    },

    switchTab(tabId) {
        this.state.tab = tabId;
        document.querySelectorAll('.activity-icon').forEach(el => el.classList.remove('active'));
        const navEl = document.getElementById(`nav-${tabId}`);
        if (navEl) navEl.classList.add('active');

        document.querySelectorAll('.panel').forEach(el => el.classList.remove('active'));
        const panelEl = document.getElementById(`panel-${tabId}`);
        if (panelEl) panelEl.classList.add('active');

        // Sidebar Visibility (Phase 6)
        const sidebar = document.getElementById('explorer-sidebar');
        if (sidebar) {
            if (tabId === 'code') sidebar.classList.remove('hidden');
            else sidebar.classList.add('hidden');
        }

        if (tabId === 'code') { 
            // Initialize Editor Engine if not already done
            if (!EditorEngine.editor) EditorEngine.init();
            else EditorEngine.loadTree(); // Refresh on tab switch
        }
        else if (tabId === 'graph') { this.loadRefsSidebar(); this.loadGraph(); }
        else if (tabId === 'diff') { this.loadDiffSidebar(); this.loadDiffContent(); }
        else if (tabId === 'prs') { this.loadPRs(); }
        else if (tabId === 'issues') { this.loadIssues(); }
    },

    /* --- EDITOR MODULE (VSCODE PARITY) --- */
    initEditor() {
        const legacySidebar = document.getElementById('explorer-sidebar');
        if (legacySidebar) legacySidebar.style.display = 'none';
        if (window.EditorApp) EditorApp.init();
    },
    async loadTree() { if (window.EditorApp) await EditorApp.loadTree(); },
    setExplorerContext(path, type) { if (window.EditorApp) EditorApp.openFile(path); },
    async openFile(path) { if (window.EditorApp) await EditorApp.openFile(path); },
    async saveCurrentFile() { if (window.EditorApp) await EditorApp.executeCommand('save'); },

    async triggerCheckout() {
        await this.showBranchPickerModal();
    },

    async showBranchPickerModal() {
        const branches = await this.api('/api/branches');
        if (!branches || !branches.length) return this.toast("No branches found", true);

        const current = this.state.workspace.branch;
        const branchListHtml = branches.map(b => `
            <div onclick="App.performCheckout('${b}')" class="group flex items-center justify-between p-4 rounded-xl border border-slate-800 hover:border-cyan-500/50 hover:bg-cyan-500/5 transition-all cursor-pointer ${b === current ? 'bg-cyan-500/10 border-cyan-500/30' : 'bg-slate-950/50'}">
                <div class="flex items-center gap-3">
                    <i class="fa-solid fa-code-branch ${b === current ? 'text-cyan-400' : 'text-slate-500 group-hover:text-cyan-400'}"></i>
                    <span class="font-mono text-sm ${b === current ? 'text-white font-bold' : 'text-slate-400 group-hover:text-white'}">${b}</span>
                </div>
                ${b === current ? '<span class="text-[9px] font-black text-cyan-500 uppercase tracking-widest">Active</span>' : ''}
            </div>
        `).join('');

        const modalHtml = `
            <div id="branch-picker-modal" class="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[110] animate-in fade-in duration-200">
                <div class="bg-slate-900 border border-slate-700 rounded-3xl w-[450px] max-w-[95vw] max-h-[80vh] shadow-2xl flex flex-col overflow-hidden">
                    <div class="p-6 bg-slate-800 border-b border-slate-700 flex justify-between items-center shrink-0">
                        <h3 class="font-black text-white text-xs uppercase tracking-[0.2em] flex items-center gap-3">
                            <i class="fa-solid fa-list-ul text-cyan-500"></i> Switch Branch
                        </h3>
                        <button onclick="document.getElementById('branch-picker-modal').remove()" class="text-slate-400 hover:text-white transition-colors"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="p-6 flex flex-col gap-3 overflow-y-auto bg-[#0b101a] custom-scrollbar">
                        ${branchListHtml}
                    </div>
                </div>
            </div>
        `;
        document.getElementById('branch-picker-modal')?.remove();
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async performCheckout(name) {
        document.getElementById('branch-picker-modal')?.remove();
        if (name === this.state.workspace.branch) return;
        if (await this.api('/api/branch/checkout', 'POST', { branch: name })) {
            this.toast(`Switched to ${name}`);
            this.syncWorkspace();
            this.loadGraph();
        }
    },

    openCommitModal() {
        const stagedBadge = document.getElementById('badge-staged');
        const count = parseInt(stagedBadge ? stagedBadge.textContent : '0', 10);
        if (count === 0) {
            this.toast("No staged changes to commit. Please stage files first.", true);
            return;
        }
        document.getElementById('commit-modal').classList.remove('hidden');
        document.getElementById('commit-modal-summary').focus();
    },

    closeCommitModal() {
        document.getElementById('commit-modal').classList.add('hidden');
        document.getElementById('commit-modal-summary').value = '';
        document.getElementById('commit-modal-desc').value = '';
    },

    async discardFile(filepath) {
        if (!confirm(`Are you sure you want to discard all unstaged changes in ${filepath}? This cannot be undone.`)) return;
        const res = await this.api('/api/discard', 'POST', { filepath });
        if (res && res.success) {
            this.toast(`Discarded changes in: ${filepath}`);
            this.syncWorkspace();
            if(this.state.tab === 'diff') this.loadDiffContent();
            if(this.state.currentFile === filepath) this.openFile(filepath); // Reload in editor if open
        }
    },

    async unstageAll() {
        if(!confirm("Unstage all files?")) return;
        const res = await this.api('/api/unstage_all', 'POST');
        if (res && res.success) {
            this.toast("All files unstaged.");
            this.syncWorkspace();
            if(this.state.tab === 'diff') this.loadDiffContent();
        }
    },

    async discardAll() {
        if (!confirm("Are you sure you want to discard ALL changes (tracked and untracked)? This CANNOT be undone.")) return;
        const res = await this.api('/api/discard_all', 'POST');
        if (res && res.success) {
            this.toast("All changes discarded.");
            this.syncWorkspace();
            this.loadDiffContent();
        }
    },

    async stashChanges() {
        const msg = prompt("Enter stash message (optional):", "Studio Stash");
        if (msg === null) return;
        const res = await this.api('/api/stash/push', 'POST', { message: msg });
        if (res && res.success) {
            this.toast("Changes stashed.");
            this.syncWorkspace();
            this.loadDiffContent();
        }
    },

    async popStash() {
        const res = await this.api('/api/stash/pop', 'POST');
        if (res && res.success) {
            this.toast("Stash popped successfully.");
            this.syncWorkspace();
            this.loadDiffContent();
        }
    },

    filterWorkingTree() {
        const q = document.getElementById('wt-search-input').value.toLowerCase();
        document.querySelectorAll('#list-unstaged > div, #list-staged > div').forEach(el => {
            const text = el.querySelector('span').textContent.toLowerCase();
            el.style.display = text.includes(q) ? 'flex' : 'none';
        });
        
        // Also filter diff tiles
        document.querySelectorAll('.glass-tile').forEach(tile => {
            const text = tile.querySelector('h4').textContent.toLowerCase();
            tile.style.display = text.includes(q) ? 'block' : 'none';
        });
    },

    getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            py: 'fa-brands fa-python text-blue-400',
            js: 'fa-brands fa-js text-yellow-400',
            ts: 'fa-solid fa-code text-blue-500',
            html: 'fa-brands fa-html5 text-orange-500',
            css: 'fa-brands fa-css3-alt text-blue-400',
            json: 'fa-regular fa-file-lines text-amber-300',
            md: 'fa-brands fa-markdown text-slate-300',
            txt: 'fa-regular fa-file-lines text-slate-400',
            default: 'fa-regular fa-file-code text-slate-500'
        };
        return icons[ext] || icons.default;
    },

    async generateAICommit() {
        // Find whichever AI Suggest button is visible (either in Commit Modal or Editor)
        const btn = document.getElementById('btn-ai-suggest') || document.getElementById('modal-btn-ai-suggest');
        const defaultText = btn ? btn.innerHTML : '';
        if (btn) {
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Thinking...';
            btn.disabled = true;
        }

        const res = await this.api('/api/ai/suggest');
        
        if (btn) {
            btn.innerHTML = defaultText || '<i class="fa-solid fa-wand-magic-sparkles"></i> AI Suggest';
            btn.disabled = false;
        }

        if (res && res.title) {
            // Apply to Modal if open, else Editor
            const sumInput = document.getElementById('commit-modal-summary') || document.getElementById('commit-msg-input');
            const descInput = document.getElementById('commit-modal-desc') || document.getElementById('commit-desc-input');
            
            if (sumInput) sumInput.value = res.title;
            if (descInput && res.body) descInput.value = res.body;
            
            this.toast("✨ AI Suggestion applied!");
        } else if (res && res.error) {
            this.toast(res.error, true);
        }
    },

    async executeCommit() {
        const summary = document.getElementById('commit-modal-summary').value.trim();
        const desc = document.getElementById('commit-modal-desc').value.trim();
        
        if (!summary) {
            this.toast("Commit summary is required!", true);
            return;
        }

        const message = desc ? `${summary}\n\n${desc}` : summary;
        const amend = document.getElementById('commit-modal-amend')?.checked || false;
        
        const res = await this.api('/api/commit', 'POST', { message, amend });
        if (res && res.success) {
            this.toast("Commit successful!");
            this.closeCommitModal();
            this.loadDiffContent();
            this.loadGraph();
            this.loadTree();
        } else {
            this.toast(res?.error || "Commit failed", true);
        }
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
        if (res) {
            this.toast(`${type.charAt(0).toUpperCase() + type.slice(1)} created successfully.`);
            this.state.activeContextPath = res.path; 
            this.loadTree(); 
        }
    },

    async commitCurrentFile() {
        if (!this.state.currentFile) return this.toast("No file open.", true);
        const msg = document.getElementById('commit-msg-input')?.value.trim() || "Update";
        // if (!msg) return this.toast("Message required.", true); // let it be optional as user said allow_empty
        const res = await this.api('/api/commit', 'POST', { filepath: this.state.currentFile, content: this.state.editor.getValue(), message: msg });
        if (res) { 
            this.toast("Committed successfully!"); 
            const msgInput = document.getElementById('commit-msg-input');
            if(msgInput) msgInput.value = ''; 
            await this.refreshStatus(); 
            if (this.state.tab === 'diff') await this.refreshDiff();
        }
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
        const data = await this.api('/api/graph');
        if (!data) return;

        let nodes = new vis.DataSet();
        let edges = new vis.DataSet();
        let rMap = {};
        
        // Map SHAs to branch/tag names
        for (const [r, sha] of Object.entries(data.refs || {})) {
            if (r === 'HEAD') continue;
            if (!rMap[sha]) rMap[sha] = [];
            rMap[sha].push(r.replace('branch:', '').replace('tag:', ''));
        }

        const colors = ['#06b6d4', '#8b5cf6', '#10b981', '#f43f5e', '#f59e0b', '#3b8edb'];
        const branchColorMap = {};
        let colorIdx = 0;

        // Process commits
        data.commits.forEach((c) => {
            const hasRefs = rMap[c.sha];
            const isHead = data.refs['HEAD'] === c.sha;
            
            // Determine Color (pick a stable color per branch if possible)
            let nodeColor = '#334155';
            let borderColor = '#475569';
            let borderWidth = 2;

            if (hasRefs) {
                const bName = hasRefs[0];
                if (!branchColorMap[bName]) branchColorMap[bName] = colors[colorIdx++ % colors.length];
                nodeColor = branchColorMap[bName];
                borderColor = nodeColor;
                borderWidth = 4;
            }
            
            if (isHead) {
                borderColor = '#ffffff';
                borderWidth = 4;
            }

            // Create Label (compact for node, detailed for tooltip/panel)
            let label = ""; 
            if (hasRefs) label = hasRefs.join('\n');

            nodes.add({
                id: c.sha,
                label: label,
                shape: 'dot',
                size: isHead ? 10 : 7,
                color: {
                    background: nodeColor,
                    border: borderColor,
                    highlight: { background: '#fff', border: nodeColor }
                },
                borderWidth: borderWidth,
                font: { color: '#94a3b8', size: 10, face: 'monospace', align: 'top', vadjust: -20 },
                title: `${c.sha.substring(0, 7)}: ${c.message.split('\n')[0]}` // Tooltip
            });

            if (c.parents) {
                c.parents.forEach(p => {
                    edges.add({
                        from: c.sha,
                        to: p,
                        arrows: 'to',
                        color: { color: '#334155', opacity: 0.5, highlight: '#64748b' },
                        smooth: { type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.5 }
                    });
                });
            }
        });

        if (this.state.graphInstance) this.state.graphInstance.destroy();
        
        const container = document.getElementById('network-canvas');
        this.state.graphInstance = new vis.Network(container, { nodes, edges }, {
            layout: {
                hierarchical: {
                    direction: 'LR',
                    sortMethod: 'directed',
                    nodeSpacing: 100,
                    levelSeparation: 150,
                    edgeMinimization: true,
                    parentCentralization: false
                }
            },
            physics: { enabled: false },
            interaction: {
                hover: true,
                tooltipDelay: 200,
                hideEdgesOnDrag: true
            }
        });

        // Event: Click to show details
        this.state.graphInstance.on("selectNode", (params) => {
            if (params.nodes.length > 0) this.showCommitDetails(params.nodes[0]);
        });

        this.state.graphInstance.on("deselectNode", () => {
            this.hideCommitDetails();
        });
    },

    filterGraph() {
        const q = document.getElementById('graph-search').value.toLowerCase();
        if (!this.state.graphInstance) return;
        // Simple highlight logic: find nodes that match and select them
        const allNodes = this.state.graphInstance.body.data.nodes.get();
        const matches = allNodes.filter(n => 
            n.id.toLowerCase().includes(q) || 
            (n.label && n.label.toLowerCase().includes(q)) ||
            (n.title && n.title.toLowerCase().includes(q))
        ).map(n => n.id);
        
        if (q && matches.length > 0) {
            this.state.graphInstance.selectNodes(matches);
            if (matches.length === 1) this.state.graphInstance.focus(matches[0], { scale: 1.2, animation: true });
        } else {
            this.state.graphInstance.unselectNodes();
        }
    },

    fitGraph() {
        if (this.state.graphInstance) this.state.graphInstance.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
    },

    async showCommitDetails(sha) {
        const panel = document.getElementById('commit-details-panel');
        panel.classList.remove('hidden');
        
        // Show Loading State
        document.getElementById('cd-sha').textContent = sha.substring(0, 12) + "...";
        document.getElementById('cd-author').textContent = "Loading...";
        document.getElementById('cd-msg').textContent = "";
        document.getElementById('cd-files-list').innerHTML = `<div class="animate-pulse flex space-y-2 flex-col"><div class="h-4 bg-slate-800 rounded w-3/4"></div><div class="h-4 bg-slate-800 rounded w-1/2"></div></div>`;

        const data = await this.api(`/api/commit/details?sha=${sha}`);
        if (!data) return;

        document.getElementById('cd-sha').textContent = data.sha;
        document.getElementById('cd-author').textContent = data.author.split(' <')[0];
        document.getElementById('cd-date').textContent = new Date(data.timestamp * 1000).toLocaleString();
        document.getElementById('cd-msg').textContent = data.message;
        
        const avatar = document.getElementById('cd-avatar');
        avatar.textContent = data.author.charAt(0).toUpperCase();

        const fileList = document.getElementById('cd-files-list');
        fileList.innerHTML = data.files.map(f => `
            <div onclick="App.showCommitFileDiff('${sha}', '${f.path}')" class="group flex items-center justify-between p-3 rounded-xl bg-slate-900/50 border border-slate-800 hover:border-cyan-500/50 hover:bg-slate-800 transition-all cursor-pointer">
                <div class="flex items-center gap-3 truncate">
                    <i class="${this.getFileIcon(f.path)} text-[10px] opacity-50"></i>
                    <span class="text-xs font-mono text-slate-300 group-hover:text-white truncate">${f.path}</span>
                </div>
                <div class="flex items-center gap-2 font-mono text-[9px] shrink-0">
                    <span class="text-green-500">+${f.added}</span>
                    <span class="text-red-500">-${f.deleted}</span>
                </div>
            </div>
        `).join('');

        // Wire buttons
        document.getElementById('cd-btn-checkout').onclick = () => this.performCheckout(sha);
        document.getElementById('cd-btn-reset').onclick = () => {
            if(confirm("Hard reset to this commit? All current uncommitted changes will be lost.")) {
                this.api('/api/reset', 'POST', { sha, hard: true }).then(() => {
                    this.toast("Reset successful");
                    this.syncWorkspace();
                    this.loadGraph();
                });
            }
        };
    },

    hideCommitDetails() {
        document.getElementById('commit-details-panel').classList.add('hidden');
        if (this.state.graphInstance) this.state.graphInstance.unselectNodes();
    },

    async showCommitFileDiff(sha, path) {
        // We'll reuse the existing diff rendering logic but in a modal
        this.toast(`Loading diff for ${path}...`);
        // For simplicity, we fetch the tree-diff text from the server if we add an endpoint, 
        // OR we just use the current logic if it can be adapted.
        // Let's assume we have /api/commit/file_diff?sha=...&path=...
        const data = await this.api(`/api/diff?sha=${sha}&path=${path}`);
        if (!data || !data.diff) return;
        
        const modalHtml = `
            <div id="diff-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center z-[200] animate-in fade-in duration-200">
                <div class="bg-slate-900 border border-slate-700 rounded-3xl w-[800px] max-w-[95vw] h-[600px] max-h-[90vh] shadow-2xl flex flex-col overflow-hidden">
                    <div class="p-6 bg-slate-800 border-b border-slate-700 flex justify-between items-center shrink-0">
                        <div>
                            <div class="text-[9px] font-black text-cyan-500 uppercase tracking-widest mb-1">File Diff Viewer</div>
                            <h3 class="text-white font-mono text-xs font-bold truncate">${path} <span class="text-slate-500 ml-2">@ ${sha.substring(0,7)}</span></h3>
                        </div>
                        <button onclick="document.getElementById('diff-modal').remove()" class="text-slate-400 hover:text-white transition-colors p-2"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="flex-1 overflow-y-auto bg-[#0b0f19] p-4 font-mono text-[11px] custom-scrollbar">
                        <div class="pb-8">
                            ${data.diff.split('\n').map(l => {
                                let cls = '';
                                if(l.startsWith('+') && !l.startsWith('+++')) cls = 'bg-green-950/40 text-green-300 border-l-2 border-green-500';
                                else if(l.startsWith('-') && !l.startsWith('---')) cls = 'bg-red-950/40 text-red-300 border-l-2 border-red-500';
                                else if(l.startsWith('@@')) cls = 'text-cyan-500 bg-cyan-950/20 py-1';
                                return `<div class="px-3 whitespace-pre-wrap ${cls}">${l.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>`;
                            }).join('')}
                        </div>
                    </div>
                </div>
            </div>`;
        document.getElementById('diff-modal')?.remove();
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async loadDiffSidebar() {
        // Redirect legacy sidebar load to do nothing, as we moved logic to the main diff panel.
        document.getElementById('sidebar-content').innerHTML = "<div class='text-gray-500 text-center mt-10'>Manage changes in the main Working Tree panel.</div>";
    },

    async loadDiffContent() {
        const statusData = await this.api('/api/status');
        const diffData = await this.api('/api/diff');
        if (!statusData) return;

        const unstaged = [...new Set([...(statusData.modified || []), ...(statusData.untracked || []), ...(statusData.deleted || [])])];
        const staged = statusData.staged || []; 

        const renderList = (filesList, type) => {
            if (!filesList || filesList.length === 0) return `<div class="text-slate-600 italic text-sm py-2">Empty</div>`;
            return filesList.map(f => {
                const isBoth = type === 'unstaged' && staged.includes(f);
                const badge = isBoth ? `<span class="ml-2 text-[9px] bg-yellow-900/80 text-yellow-300 px-1.5 py-0.5 rounded border border-yellow-700/50 uppercase tracking-widest">Modified</span>` : '';
                const iconClass = this.getFileIcon(f);
                const checkIcon = type === 'staged' ? 'fa-circle-check text-green-500' : iconClass;
                
                // Discard button only for unstaged changes
                const discardBtn = type === 'unstaged' ? `<button onclick="App.discardFile('${f}')" title="Discard Changes" class="opacity-0 group-hover:opacity-100 px-2 py-0.5 text-xs rounded bg-red-900/30 text-red-500 hover:bg-red-800 hover:text-white transition-all mr-1"><i class="fa-solid fa-trash-can"></i></button>` : '';

                return `
                <div class="flex justify-between items-center group hover:bg-slate-800/80 p-1.5 rounded transition-colors">
                    <span class="text-slate-300 text-sm font-mono truncate flex items-center cursor-pointer hover:text-cyan-400" onclick="App.switchTab('code'); App.openFile('${f}')" title="Open in Editor">
                        <i class="${checkIcon} mr-2"></i> ${f} ${badge}
                    </span>
                    <div class="flex items-center">
                        ${discardBtn}
                        <button onclick="App.${type === 'staged' ? 'unstageFile' : 'stageFile'}('${f}')" title="${type === 'staged' ? 'Unstage' : 'Stage'}" class="opacity-0 group-hover:opacity-100 px-2 py-0.5 text-[10px] font-bold rounded ${type === 'staged' ? 'bg-amber-900/30 text-amber-500 hover:bg-amber-800' : 'bg-cyan-900/30 text-cyan-400 hover:bg-cyan-800'} hover:text-white transition-all shadow flex items-center gap-1">
                            <i class="fa-solid ${type === 'staged' ? 'fa-minus' : 'fa-plus'} text-[8px]"></i> ${type === 'staged' ? 'Unstage' : 'Stage'}
                        </button>
                    </div>
                </div>
            `}).join('');
        }; 

        const elUnstaged = document.getElementById('list-unstaged');
        const badgeUnstaged = document.getElementById('badge-unstaged');
        if (elUnstaged) elUnstaged.innerHTML = renderList(unstaged, 'unstaged');
        if (badgeUnstaged) badgeUnstaged.textContent = unstaged.length;
        
        const elStaged = document.getElementById('list-staged');
        const badgeStaged = document.getElementById('badge-staged');
        if (elStaged) elStaged.innerHTML = renderList(staged, 'staged');
        if (badgeStaged) badgeStaged.textContent = staged.length;

        const grid = document.getElementById('diff-grid');
        if (!grid) return;

        if (!diffData || !diffData.diff || diffData.diff.trim() === '') {
            grid.innerHTML = `<div class="col-span-full text-center text-slate-500 py-10 text-lg bg-slate-900/20 rounded-xl border border-slate-800">No visible diff content. Try modifying a tracked file.</div>`;
            return;
        }

        const files = [];
        let currentFile = null;
        
        diffData.diff.split('\n').forEach(line => {
            if (line.startsWith('diff --deep ')) {
                if (currentFile) files.push(currentFile);
                currentFile = { name: line.split(' b/')[1], added: 0, deleted: 0, lines: [], minimap: [] };
            } else if (currentFile) {
                let type = 'null';
                if (line.startsWith('+') && !line.startsWith('+++')) { type = 'add'; currentFile.added++; }
                else if (line.startsWith('-') && !line.startsWith('---')) { type = 'del'; currentFile.deleted++; }
                else if (line.startsWith('@@')) type = 'header';
                else if (line.startsWith('+++') || line.startsWith('---')) type = 'header';
                else if (line.trim() !== '') type = 'mod';
                
                if (type !== 'null' || line.trim() !== '') {
                    currentFile.lines.push({ text: line, type });
                    if(type !== 'header') currentFile.minimap.push(type);
                }
            }
        });
        if (currentFile) files.push(currentFile);

        grid.innerHTML = files.map((file, idx) => {
            const parts = file.name ? file.name.split('/') : ['unknown'];
            const filename = parts.pop();
            const folder = parts.join('/') || 'root';

            const totalLines = file.lines.length || 1;
            const changeRatio = (file.added + file.deleted) / totalLines;
            const glowOpacity = Math.min(0.5, changeRatio * 2);

            const maxMinimap = 40;
            const minimapScale = Math.max(1, Math.floor(file.minimap.length / maxMinimap));
            const scaledMinimap = file.minimap.filter((_, i) => i % minimapScale === 0).slice(0, maxMinimap);
            const minimapHtml = scaledMinimap.map(t => `<div class="minimap-line minimap-${t}"></div>`).join('');

            const codeHtml = file.lines.map(l => 
                `<div class="diff-line ${l.type}"><span>${l.text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</span></div>`
            ).join('');

            const isBoth = App.isModifiedAfterStaging(file.name, staged, unstaged);
            const isStaged = staged.includes(file.name);
            let diffType = '';
            if (isBoth) diffType = 'WORKING TREE vs STAGED';
            else if (isStaged) diffType = 'STAGED vs HEAD';
            else diffType = 'WORKING TREE vs HEAD';

            return `
            <div class="glass-tile rounded-2xl p-5 relative overflow-hidden group wave-active" style="box-shadow: 0 8px 32px 0 rgba(6, 182, 212, ${glowOpacity * 0.3});">
                <div class="absolute top-0 left-0 h-1 w-full bg-gradient-to-r from-green-500 via-yellow-500 to-red-500" style="opacity: ${glowOpacity + 0.2};"></div>
                
                <div class="flex justify-between items-start mb-4 relative z-10">
                    <div class="truncate pr-4">
                        <div class="text-[10px] font-bold text-cyan-500 uppercase tracking-widest mb-1 shadow-sm">${diffType}</div>
                        <h4 class="text-lg font-bold text-white truncate group-hover:text-cyan-300 transition-colors cursor-pointer" onclick="App.switchTab('code'); App.openFile('${file.name}')">${filename}</h4>
                    </div>
                    <div class="flex flex-col items-end shrink-0">
                        <div class="bg-slate-900/80 border border-slate-700 px-2 py-1 rounded-lg flex items-center gap-2 font-mono text-xs font-bold mb-2">
                            <span class="text-green-400">+${file.added}</span>
                            <span class="text-red-400">-${file.deleted}</span>
                        </div>
                        <button onclick="App.${isStaged ? 'unstageFile' : 'stageFile'}('${file.name}')" class="text-xs ${isStaged ? 'bg-amber-700/50 hover:bg-amber-600 text-amber-100' : 'bg-cyan-700/50 hover:bg-cyan-600 text-cyan-100'} px-3 py-1 rounded border ${isStaged ? 'border-amber-500/50' : 'border-cyan-500/50'} transition-colors shadow flex items-center gap-1">
                            <i class="fa-solid ${isStaged ? 'fa-minus' : 'fa-plus'}"></i> ${isStaged ? 'Unstage' : 'Stage'}
                        </button>
                    </div>
                </div>

                <div class="flex gap-3 h-64 relative z-10">
                    <div class="diff-block flex-1 bg-[#0b0f19]/80 border border-slate-700/50 overflow-y-auto relative rounded shadow-inner">
                        <div class="absolute inset-0 pb-4">
                            ${codeHtml}
                        </div>
                    </div>
                    <div class="diff-minimap shrink-0 shadow-inner p-0.5 gap-px">
                        ${minimapHtml}
                    </div>
                </div>
            </div>`;
        }).join('');
    },

    /* API Actions */
    async stageFile(file) {
        if(!file) return;
        console.log("staging", file);
        await this.api('/api/stage', 'POST', { filepath: file });
        await this.refreshStatus();
        await this.refreshDiff();
    },

    async unstageFile(file) {
        if(!file) return;
        console.log("unstaging", file);
        await this.api('/api/unstage', 'POST', { filepath: file });
        await this.refreshStatus();
        await this.refreshDiff();
    },
    
    async stageAll() {
        const statusData = await this.api('/api/status');
        if (!statusData) return;
        const unstaged = [...(statusData.modified || []), ...(statusData.untracked || []), ...(statusData.deleted || [])];
        if (unstaged.length === 0) return this.toast("Nothing to stage.", true);
        
        for (const f of unstaged) {
            await this.api('/api/stage', 'POST', { file: f });
        }
        this.toast("All changes staged.");
        await this.refreshStatus();
        await this.refreshDiff();
    },

    /* --- ISSUES MANAGEMENT --- */
    async loadIssues() {
        const data = await this.api('/api/issues/local');
        if (!data || !data.issues) return;

        const openCol = document.getElementById('issues-open-column');
        const closedCol = document.getElementById('issues-closed-column');
        const openBadge = document.getElementById('badge-issues-open');
        const closedBadge = document.getElementById('badge-issues-closed');

        if (!openCol || !closedCol) return;

        const renderIssueCard = (iss) => {
            const priorityColors = {
                'High': 'text-red-400 border-red-900/50 bg-red-900/10',
                'Medium': 'text-amber-400 border-amber-900/50 bg-amber-900/10',
                'Low': 'text-emerald-400 border-emerald-900/50 bg-emerald-900/10'
            };
            const pClass = priorityColors[iss.priority || 'Medium'];
            const typeIcon = iss.type === 'bug' ? 'fa-bug text-red-500' : iss.type === 'feature' ? 'fa-wand-magic-sparkles text-purple-500' : 'fa-list-check text-blue-500';

            return `
            <div class="glass-issue-card group bg-slate-900/40 border border-slate-800/50 p-4 rounded-2xl hover:border-emerald-500/50 hover:bg-slate-800/50 transition-all cursor-pointer shadow-xl backdrop-blur-sm relative overflow-hidden" onclick="App.showIssueDetails(${iss.id})">
                <div class="absolute top-0 right-0 w-32 h-32 bg-emerald-500/5 blur-[80px] rounded-full -mr-16 -mt-16 group-hover:bg-emerald-500/10 transition-colors"></div>
                <div class="flex justify-between items-start mb-3 relative z-10">
                    <span class="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                        <i class="fa-solid ${typeIcon}"></i> ${iss.type || 'task'}
                    </span>
                    <span class="px-2 py-0.5 rounded-md text-[9px] font-black border uppercase tracking-tighter ${pClass}">
                        ${iss.priority || 'Medium'}
                    </span>
                </div>
                <h4 class="text-white font-bold text-sm mb-2 group-hover:text-emerald-400 transition-colors line-clamp-2">#${iss.id} ${iss.title}</h4>
                <div class="text-slate-500 text-xs line-clamp-2 font-mono opacity-80 mb-4 h-8">
                    ${iss.description || iss.body || 'No description provided.'}
                </div>
                <div class="flex justify-between items-center relative z-10 pt-3 border-t border-slate-800/50">
                    <div class="flex items-center gap-2">
                        <div class="w-5 h-5 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] text-slate-400">
                            <i class="fa-solid fa-user-ninja"></i>
                        </div>
                        <span class="text-[10px] text-slate-500 font-bold">${iss.author || 'AI Agent'}</span>
                    </div>
                    <span class="text-[9px] text-slate-600 font-mono">${new Date(iss.created_at).toLocaleDateString()}</span>
                </div>
            </div>`;
        };

        const openIssues = data.issues.filter(i => i.state === 'OPEN');
        const closedIssues = data.issues.filter(i => i.state !== 'OPEN');

        openCol.innerHTML = openIssues.length ? openIssues.map(renderIssueCard).join('') : `<div class='text-slate-600 border-2 border-dashed border-slate-800/50 p-10 rounded-2xl text-center italic text-sm'>All caught up! No open issues.</div>`;
        closedCol.innerHTML = closedIssues.length ? closedIssues.map(renderIssueCard).join('') : `<div class='text-slate-700 border border-slate-800/30 p-8 rounded-2xl text-center italic text-xs'>Archive is empty.</div>`;
        
        if (openBadge) openBadge.textContent = openIssues.length;
        if (closedBadge) closedBadge.textContent = closedIssues.length;
    },

    filterIssues() {
        const q = document.getElementById('issue-search-input').value.toLowerCase();
        document.querySelectorAll('.glass-issue-card').forEach(card => {
            const text = card.textContent.toLowerCase();
            card.style.display = text.includes(q) ? 'block' : 'none';
        });
    },

    async showIssueDetails(issueId) {
        const data = await this.api('/api/issues/local');
        if(!data || !data.issues) return;
        const iss = data.issues.find(i => i.id == issueId);
        if(!iss) return;

        document.getElementById('issue-detail-modal')?.remove();

        const isOpen = iss.state === 'OPEN';
        const priorityColors = { 'High': 'text-red-400 bg-red-950/30 border-red-700', 'Medium': 'text-amber-400 bg-amber-950/30 border-amber-700', 'Low': 'text-emerald-400 bg-emerald-950/30 border-emerald-700' };
        const pClass = priorityColors[iss.priority || 'Medium'];
        const stateColor = isOpen ? 'text-emerald-400 bg-emerald-950/30 border-emerald-700' : 'text-purple-400 bg-purple-950/30 border-purple-700';

        // Structured Description Parsing (CLI Parity)
        let descriptionHtml = '';
        const desc = iss.description || iss.body || '';
        if (desc.startsWith('[BUG]')) {
            const parts = desc.replace('[BUG]\n', '').split('\n\n');
            descriptionHtml = parts.map(p => {
                const [label, ...val] = p.split(':\n');
                return `<div class="mb-4"><label class="text-[10px] font-black text-red-500 uppercase tracking-widest block mb-1">${label}</label><div class="bg-slate-900/50 p-3 rounded-xl border border-slate-800/50 text-slate-300 font-mono text-xs">${val.join(':\n') || 'N/A'}</div></div>`;
            }).join('');
        } else if (desc.startsWith('[FEATURE]')) {
            const parts = desc.replace('[FEATURE]\n', '').split('\n\n');
            descriptionHtml = parts.map(p => {
                const [label, ...val] = p.split(':\n');
                return `<div class="mb-4"><label class="text-[10px] font-black text-cyan-500 uppercase tracking-widest block mb-1">${label}</label><div class="bg-slate-900/50 p-3 rounded-xl border border-slate-800/50 text-slate-300 font-mono text-xs">${val.join(':\n') || 'N/A'}</div></div>`;
            }).join('');
        } else {
            descriptionHtml = `<div class="text-slate-300 font-mono text-sm leading-relaxed">${desc || '<span class="italic text-slate-600">No description provided.</span>'}</div>`;
        }

        // Timeline Rendering
        const timelineHtml = (iss.timeline || []).map(ev => {
            const ts = new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            let icon = 'fa-circle-dot';
            let color = 'text-slate-500';
            let msg = ev.event.replace(/_/g, ' ');

            if (ev.event === 'created') { icon = 'fa-star'; color = 'text-emerald-500'; }
            else if (ev.event === 'linked_pr') { icon = 'fa-code-branch'; color = 'text-purple-500'; msg = `Linked to PR #${ev.pr}`; }
            else if (ev.event === 'closed_by_pr') { icon = 'fa-check-double'; color = 'text-purple-400'; msg = `Closed by PR #${ev.pr}`; }
            else if (ev.event === 'closed') { icon = 'fa-circle-check'; color = 'text-red-500'; }
            else if (ev.event === 'reopened') { icon = 'fa-rotate-left'; color = 'text-emerald-400'; }

            return `
                <div class="flex gap-4 items-start relative pb-6 last:pb-0">
                    <div class="absolute left-[9px] top-6 bottom-0 w-[2px] bg-slate-800 last:hidden"></div>
                    <div class="w-5 h-5 rounded-full bg-slate-900 border border-slate-700 flex items-center justify-center z-10">
                        <i class="fa-solid ${icon} text-[8px] ${color}"></i>
                    </div>
                    <div class="flex-1 -mt-0.5">
                        <div class="flex justify-between items-center mb-0.5">
                            <span class="text-[10px] font-black text-slate-400 uppercase tracking-widest">${msg}</span>
                            <span class="text-[9px] font-mono text-slate-600">${ts}</span>
                        </div>
                    </div>
                </div>`;
        }).join('');

        const modalHtml = `
            <div id="issue-detail-modal" class="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[100] animate-in fade-in zoom-in-95 duration-200">
                <div class="bg-slate-900 border border-slate-700 rounded-3xl w-[750px] shadow-2xl flex flex-col overflow-hidden max-h-[85vh]">
                    <div class="p-6 border-b border-slate-800 bg-slate-800 flex justify-between items-start">
                        <div class="space-y-3">
                            <div class="flex items-center gap-3">
                                <span class="font-black text-[10px] px-2 py-1 rounded-md border uppercase tracking-widest ${stateColor}">${iss.state}</span>
                                <span class="font-black text-[10px] px-2 py-1 rounded-md border uppercase tracking-widest ${pClass}">${iss.priority || 'Medium'}</span>
                                <span class="text-xs text-slate-500 font-mono">#${iss.id}</span>
                            </div>
                            <h2 class="text-2xl font-black text-white tracking-tight">${iss.title}</h2>
                        </div>
                        <button onclick="document.getElementById('issue-detail-modal').remove()" class="bg-slate-700 hover:bg-slate-600 text-slate-400 hover:text-white w-10 h-10 rounded-full flex items-center justify-center transition-all"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    
                    <div class="flex flex-1 overflow-hidden">
                        <!-- Description Column -->
                        <div class="flex-1 p-8 overflow-y-auto border-r border-slate-800 bg-slate-950/30 custom-scrollbar">
                            <label class="block text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-6">Report Details</label>
                            ${descriptionHtml}
                        </div>
                        
                        <!-- Timeline Column -->
                        <div class="w-[280px] p-6 bg-slate-900/50 overflow-y-auto custom-scrollbar">
                            <label class="block text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-6">Activity Timeline</label>
                            <div class="space-y-1">
                                ${timelineHtml || '<div class="text-[10px] text-slate-600 italic">No activity yet.</div>'}
                            </div>
                        </div>
                    </div>

                    <div class="p-6 bg-slate-800 border-t border-slate-700 flex justify-between items-center shrink-0">
                        <div class="flex gap-2">
                            ${(iss.labels || []).map(l => `<span class="bg-slate-700 text-slate-400 px-2 py-1 rounded text-[10px] font-bold border border-slate-600">#${l}</span>`).join('')}
                        </div>
                        <div class="flex gap-3">
                            ${isOpen 
                                ? `<button onclick="App.manageIssue(${iss.id}, 'close'); document.getElementById('issue-detail-modal').remove();" class="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2 rounded-xl font-black text-[10px] uppercase tracking-widest transition-all shadow-lg shadow-emerald-900/20"><i class="fa-solid fa-check mr-2"></i>Close Issue</button>` 
                                : `<button onclick="App.manageIssue(${iss.id}, 'reopen'); document.getElementById('issue-detail-modal').remove();" class="bg-purple-600 hover:bg-purple-500 text-white px-6 py-2 rounded-xl font-black text-[10px] uppercase tracking-widest transition-all shadow-lg shadow-purple-900/20"><i class="fa-solid fa-rotate-left mr-2"></i>Reopen Issue</button>`
                            }
                        </div>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },
    showCreateIssueModal() {
        const modalHtml = `
            <div id="create-issue-modal" class="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[100] animate-in fade-in zoom-in-95 duration-200">
                <div class="bg-slate-900 border border-slate-700 rounded-3xl w-[550px] max-w-[95vw] max-h-[90vh] shadow-2xl flex flex-col overflow-hidden">
                    <div class="p-6 bg-slate-800 border-b border-slate-700 flex justify-between items-center shrink-0">
                        <h3 class="font-black text-white text-xs uppercase tracking-[0.2em] flex items-center gap-3">
                            <i class="fa-solid fa-circle-plus text-emerald-500"></i> New Core Issue
                        </h3>
                        <button onclick="document.getElementById('create-issue-modal').remove()" class="text-slate-400 hover:text-white transition-colors"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="p-8 flex flex-col gap-6 bg-[#0b0f19] overflow-y-auto custom-scrollbar">
                        <div class="space-y-4">
                            <input type="text" id="ci-title" placeholder="What is the issue?" class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full outline-none focus:border-emerald-600/50 focus:ring-1 focus:ring-emerald-500/20 transition-all font-bold">
                            
                            <div class="grid grid-cols-2 gap-4">
                                <div>
                                    <label class="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Priority</label>
                                    <select id="ci-priority" class="bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-200 w-full outline-none focus:border-emerald-600/50 appearance-none font-bold">
                                        <option value="Low">Low Priority</option>
                                        <option value="Medium" selected>Medium Priority</option>
                                        <option value="High">High Priority</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Type</label>
                                    <select id="ci-type" onchange="App.toggleIssueTemplate(this.value)" class="bg-slate-950 border border-slate-800 rounded-xl p-3 text-slate-200 w-full outline-none focus:border-emerald-600/50 appearance-none font-bold">
                                        <option value="task">General Task</option>
                                        <option value="bug">Bug Report</option>
                                        <option value="feature">New Feature</option>
                                    </select>
                                </div>
                            </div>

                            <div id="ci-template-container" class="space-y-4">
                                <textarea id="ci-body" placeholder="Describe the details, steps to reproduce, or objectives..." class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full h-40 outline-none focus:border-emerald-600/50 focus:ring-1 focus:ring-emerald-500/20 transition-all font-mono text-sm resize-none"></textarea>
                            </div>
                        </div>
                        
                        <button onclick="App.submitNewIssue()" class="bg-emerald-600 hover:bg-emerald-500 text-white font-black py-4 rounded-2xl uppercase text-[11px] tracking-[0.2em] transition-all shadow-xl shadow-emerald-900/40 active:scale-[0.98]">
                            <i class="fa-solid fa-paper-plane mr-2"></i> Deploy Issue
                        </button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('ci-title').focus();
    },

    toggleIssueTemplate(type) {
        const container = document.getElementById('ci-template-container');
        if (!container) return;

        if (type === 'bug') {
            container.innerHTML = `
                <textarea id="ci-bug-steps" placeholder="Steps to reproduce..." class="bg-slate-950 border border-slate-800 rounded-xl p-3 text-white w-full h-24 outline-none focus:border-emerald-600/50 text-sm font-mono resize-none"></textarea>
                <textarea id="ci-bug-expected" placeholder="Expected behavior..." class="bg-slate-950 border border-slate-800 rounded-xl p-3 text-white w-full h-20 outline-none focus:border-emerald-600/50 text-sm font-mono resize-none"></textarea>
                <textarea id="ci-bug-actual" placeholder="Actual behavior (Not good...)" class="bg-slate-950 border border-slate-800 rounded-xl p-3 text-white w-full h-20 outline-none focus:border-emerald-600/50 text-sm font-mono resize-none"></textarea>
            `;
        } else if (type === 'feature') {
            container.innerHTML = `
                <textarea id="ci-feat-problem" placeholder="What problem does this solve?" class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full h-24 outline-none focus:border-emerald-600/50 text-sm font-mono resize-none"></textarea>
                <textarea id="ci-feat-solution" placeholder="Proposed solution..." class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full h-24 outline-none focus:border-emerald-600/50 text-sm font-mono resize-none"></textarea>
            `;
        } else {
            container.innerHTML = `
                <textarea id="ci-body" placeholder="Describe the details, steps to reproduce, or objectives..." class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full h-40 outline-none focus:border-emerald-600/50 focus:ring-1 focus:ring-emerald-500/20 transition-all font-mono text-sm resize-none"></textarea>
            `;
        }
    },

    async submitNewIssue() {
        const title = document.getElementById('ci-title').value.trim();
        const priority = document.getElementById('ci-priority').value;
        const type = document.getElementById('ci-type').value;
        let body = "";

        if (type === 'bug') {
            const steps = document.getElementById('ci-bug-steps').value.trim();
            const expected = document.getElementById('ci-bug-expected').value.trim();
            const actual = document.getElementById('ci-bug-actual').value.trim();
            body = `[BUG]\nSteps:\n${steps}\n\nExpected:\n${expected}\n\nActual:\n${actual}`;
        } else if (type === 'feature') {
            const problem = document.getElementById('ci-feat-problem').value.trim();
            const solution = document.getElementById('ci-feat-solution').value.trim();
            body = `[FEATURE]\nProblem:\n${problem}\n\nSolution:\n${solution}`;
        } else {
            body = document.getElementById('ci-body').value.trim();
        }

        if (!title) return this.toast("Issue title is mandatory.", true);
        
        const res = await this.api('/api/issue/create', 'POST', { title, body, priority, type });
        if (res) { 
            this.toast("Issue successfully registered on the board."); 
            document.getElementById('create-issue-modal').remove(); 
            this.loadIssues(); 
        }
    },

    async manageIssue(issue_id, action) {
        if (await this.api('/api/issue/manage', 'POST', { issue_id, action })) { this.toast(`Issue ${action === 'close' ? 'closed' : 'reopened'}`); this.loadIssues(); }
    },

    /* --- PULL REQUESTS MANAGEMENT --- */
    async loadPRs() {
        const data = await this.api('/api/prs/local');
        if (!data || !data.prs) return;

        const openCol = document.getElementById('prs-open-column');
        const reviewCol = document.getElementById('prs-review-column');
        const mergedCol = document.getElementById('prs-merged-column');
        
        const openBadge = document.getElementById('badge-prs-open');
        const reviewBadge = document.getElementById('badge-prs-review');
        const mergedBadge = document.getElementById('badge-prs-merged');

        if (!openCol || !reviewCol || !mergedCol) return;

        const renderPRCard = (pr) => {
            const isApproved = pr.state === 'APPROVED';
            const isMerged = pr.state === 'MERGED' || pr.state === 'CLOSED';
            const statusClass = isApproved ? 'text-emerald-400 border-emerald-900/50 bg-emerald-900/10' : isMerged ? 'text-slate-400 border-slate-700 bg-slate-800/20' : 'text-blue-400 border-blue-900/50 bg-blue-900/10';

            return `
            <div class="glass-pr-card group bg-slate-900/40 border border-slate-800/50 p-5 rounded-2xl hover:border-purple-500/50 hover:bg-slate-800/50 transition-all cursor-pointer shadow-xl backdrop-blur-sm relative overflow-hidden" onclick="App.showPRDetails(${pr.id})">
                <div class="absolute top-0 right-0 w-32 h-32 bg-purple-500/5 blur-[80px] rounded-full -mr-16 -mt-16 group-hover:bg-purple-500/10 transition-colors"></div>
                <div class="flex justify-between items-start mb-4 relative z-10">
                    <span class="px-2 py-0.5 rounded-md text-[9px] font-black border uppercase tracking-widest ${statusClass}">
                        ${pr.state}
                    </span>
                    <span class="text-[10px] text-slate-500 font-mono">#${pr.id}</span>
                </div>
                <h4 class="text-white font-bold text-sm mb-4 group-hover:text-purple-400 transition-colors line-clamp-1">${pr.title}</h4>
                
                <div class="flex items-center gap-3 mb-6 bg-slate-950/50 p-2 rounded-lg border border-slate-800/30">
                    <div class="flex flex-col items-center gap-1">
                        <span class="text-[8px] text-slate-600 font-black uppercase tracking-tighter">from</span>
                        <span class="text-[10px] text-cyan-400 font-mono font-bold max-w-[80px] truncate">${pr.head}</span>
                    </div>
                    <i class="fa-solid fa-arrow-right-long text-slate-700 text-[10px]"></i>
                    <div class="flex flex-col items-center gap-1">
                        <span class="text-[8px] text-slate-600 font-black uppercase tracking-tighter">into</span>
                        <span class="text-[10px] text-slate-400 font-mono font-bold max-w-[80px] truncate">${pr.base}</span>
                    </div>
                </div>

                <div class="flex justify-between items-center pt-3 border-t border-slate-800/50 relative z-10">
                    <div class="flex items-center gap-2">
                        <div class="flex -space-x-2">
                            <div class="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] text-slate-400" title="${pr.author || 'AI'}">
                                <i class="fa-solid fa-user-astronaut"></i>
                            </div>
                            <div class="w-6 h-6 rounded-full bg-purple-900 border border-purple-700 flex items-center justify-center text-[8px] text-white font-black" title="Approvals">
                                ${pr.reviews ? pr.reviews.filter(r => r.state === 'APPROVED').length : 0}
                            </div>
                        </div>
                    </div>
                    <span class="text-[9px] text-slate-600 font-mono">${new Date().toLocaleDateString()}</span>
                </div>
            </div>`;
        };

        const openPRs = data.prs.filter(p => (p.state === 'OPEN' || p.state === 'DRAFT') && (p.reviews || []).length === 0 && (p.threads || []).length === 0);
        const reviewPRs = data.prs.filter(p => (p.state === 'OPEN' || p.state === 'DRAFT' || p.state === 'APPROVED' || p.state === 'CHANGES_REQUESTED') && ((p.reviews || []).length > 0 || (p.threads || []).length > 0));
        const closedPRs = data.prs.filter(p => p.state === 'MERGED' || p.state === 'CLOSED');

        openCol.innerHTML = openPRs.length ? openPRs.map(renderPRCard).join('') : `<div class='text-slate-600 border border-dashed border-slate-800/50 p-6 rounded-xl text-center italic text-[10px]'>Queue is empty</div>`;
        reviewCol.innerHTML = reviewPRs.length ? reviewPRs.map(renderPRCard).join('') : `<div class='text-slate-600 border border-dashed border-slate-800/50 p-6 rounded-xl text-center italic text-[10px]'>Clear</div>`;
        mergedCol.innerHTML = closedPRs.length ? closedPRs.map(renderPRCard).join('') : `<div class='text-slate-700 border border-slate-800/30 p-6 rounded-xl text-center italic text-[9px]'>History empty</div>`;
        
        if (openBadge) openBadge.textContent = openPRs.length;
        if (reviewBadge) reviewBadge.textContent = reviewPRs.length;
        if (mergedBadge) mergedBadge.textContent = closedPRs.length;
    },

    filterPRs() {
        const q = document.getElementById('pr-search-input').value.toLowerCase();
        document.querySelectorAll('.glass-pr-card').forEach(card => {
            const text = card.textContent.toLowerCase();
            card.style.display = text.includes(q) ? 'block' : 'none';
        });
    },

    async showPRDetails(prId) {
        const data = await this.api('/api/prs/local');
        if(!data || !data.prs) return;
        const pr = data.prs.find(p => p.id == prId);
        if(!pr) return;

        document.getElementById('pr-detail-modal')?.remove();

        const isApproved = pr.isApproved || pr.state === "APPROVED";
        const isMerged = pr.state === "MERGED" || pr.state === "CLOSED";
        const stateColor = isApproved ? 'text-emerald-400 bg-emerald-950/30 border-emerald-700' : isMerged ? 'text-slate-400 bg-slate-800/30 border-slate-700' : 'text-blue-400 bg-blue-950/30 border-blue-700';
        
        const reviewsHtml = (pr.reviews && pr.reviews.length > 0) ? pr.reviews.map(r => `
            <div class="bg-slate-900 border border-slate-800 p-4 rounded-2xl mb-3 flex flex-col gap-2 shadow-inner">
                <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                        <div class="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] text-slate-500">
                            <i class="fa-solid fa-user-ninja"></i>
                        </div>
                        <span class="text-xs font-black text-slate-300 tracking-tight">${r.reviewer}</span>
                    </div>
                    <span class="text-[9px] font-black px-2 py-0.5 rounded border uppercase tracking-widest ${r.state === 'APPROVED' ? 'text-emerald-400 border-emerald-900/50 bg-emerald-900/10' : 'text-amber-400 border-amber-900/50 bg-amber-900/10'}">${r.state}</span>
                </div>
                ${r.comment ? `<p class="text-xs text-slate-400 font-mono bg-slate-950/50 p-3 rounded-xl border border-slate-800/30">${r.comment}</p>` : ''}
            </div>`).join('') : `<div class="text-slate-600 italic text-[10px] text-center p-6 bg-slate-900/50 rounded-2xl border border-dashed border-slate-800/50">Waiting for first review...</div>`;

        const modalHtml = `
            <div id="pr-detail-modal" class="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[100] animate-in fade-in duration-200">
                <div class="bg-slate-900 border border-slate-700 rounded-3xl w-[800px] max-w-[95vw] max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
                    <div class="p-6 border-b border-slate-800 bg-slate-900/80 flex justify-between items-start shrink-0">
                        <div class="space-y-4 w-full mr-12">
                            <div class="flex items-center gap-3">
                                <span class="font-black text-[10px] px-2 py-1 rounded-md border uppercase tracking-widest ${stateColor}">${pr.state}</span>
                                <span class="text-[10px] text-slate-500 font-mono uppercase tracking-tighter">PR #${pr.id}</span>
                            </div>
                            <h2 class="text-2xl font-black text-white tracking-tight">${pr.title}</h2>
                            <div class="flex items-center gap-3 bg-slate-950/80 p-3 rounded-2xl border border-slate-800 w-fit">
                                <div class="flex flex-col items-center px-3 border-r border-slate-800/50">
                                    <span class="text-[8px] text-slate-600 font-black uppercase tracking-widest mb-1">Source</span>
                                    <span class="text-xs font-mono font-bold text-cyan-400"><i class="fa-solid fa-code-branch mr-2 opacity-50"></i>${pr.head}</span>
                                </div>
                                <div class="px-2"><i class="fa-solid fa-arrow-right-long text-slate-700"></i></div>
                                <div class="flex flex-col items-center px-3">
                                    <span class="text-[8px] text-slate-600 font-black uppercase tracking-widest mb-1">Target</span>
                                    <span class="text-xs font-mono font-bold text-slate-400"><i class="fa-solid fa-code-merge mr-2 opacity-50"></i>${pr.base}</span>
                                </div>
                            </div>
                        </div>
                        <button onclick="document.getElementById('pr-detail-modal').remove()" class="bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white w-10 h-10 rounded-full flex items-center justify-center transition-all shrink-0"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    
                    <div class="p-8 overflow-y-auto space-y-8 bg-[#0b0f19] custom-scrollbar flex-1">
                        <div>
                            <h3 class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-3 flex items-center gap-2">
                                <i class="fa-solid fa-align-left text-indigo-500"></i> Description
                            </h3>
                            <div class="text-slate-300 bg-slate-900/50 p-5 rounded-2xl border border-slate-800 font-mono text-xs leading-relaxed whitespace-pre-wrap">${pr.desc || '<span class="italic text-slate-600">No description provided.</span>'}</div>
                        </div>

                        <div>
                            <h3 class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-4 flex items-center gap-2">
                                <i class="fa-solid fa-comments text-cyan-500"></i> Code Discussions
                            </h3>
                            <div id="pr-threads-container" class="space-y-4">
                                ${(pr.threads || []).map(t => `
                                    <div class="bg-slate-900/80 border ${t.resolved ? 'border-emerald-900/50 bg-emerald-950/10' : 'border-slate-800'} p-5 rounded-2xl shadow-sm relative overflow-hidden">
                                        <div class="flex justify-between items-start mb-3">
                                            <div class="flex items-center gap-2">
                                                <div class="w-7 h-7 rounded-full bg-slate-800 flex items-center justify-center text-[10px] text-slate-400 border border-slate-700">
                                                    <i class="fa-solid fa-user-ninja"></i>
                                                </div>
                                                <span class="text-xs font-black text-slate-200">@${t.author}</span>
                                            </div>
                                            ${t.resolved 
                                                ? '<span class="text-[9px] font-black text-emerald-500 uppercase tracking-widest flex items-center gap-1"><i class="fa-solid fa-check-circle"></i> Resolved</span>'
                                                : `<button onclick="App.resolvePRThread(${pr.id}, ${t.id})" class="text-[9px] font-black text-slate-500 hover:text-emerald-500 uppercase tracking-widest transition-colors">Mark Resolved</button>`
                                            }
                                        </div>
                                        <p class="text-sm text-slate-300 ml-9 leading-relaxed font-mono">${t.text}</p>
                                        
                                        <div class="mt-4 ml-9 space-y-3 border-l-2 border-slate-800 pl-4">
                                            ${(t.replies || []).map(r => `
                                                <div class="text-xs">
                                                    <div class="flex items-center gap-2 mb-1">
                                                        <span class="font-black text-slate-400">@${r.author}</span>
                                                    </div>
                                                    <p class="text-slate-500 font-mono">${r.text}</p>
                                                </div>
                                            `).join('')}
                                            <div class="flex gap-2 mt-4 pt-2 border-t border-slate-800/50">
                                                <input type="text" id="reply-to-${t.id}" placeholder="Type a reply..." class="flex-1 bg-transparent border-none text-xs text-slate-400 outline-none placeholder-slate-700">
                                                <button onclick="App.addPRReply(${pr.id}, ${t.id})" class="text-[10px] text-purple-500 font-black uppercase tracking-widest hover:text-purple-400">Reply</button>
                                            </div>
                                        </div>
                                    </div>
                                `).join('')}
                                
                                <div class="bg-slate-950/50 border border-slate-800/50 p-5 rounded-2xl border-dashed">
                                    <textarea id="pr-new-thread-text" placeholder="Start a new discussion thread..." class="w-full bg-transparent border-none text-sm text-slate-400 outline-none h-16 resize-none placeholder-slate-800 font-mono"></textarea>
                                    <div class="flex justify-end mt-2">
                                        <button onclick="App.addPRComment(${pr.id})" class="bg-purple-600/20 hover:bg-purple-600/40 text-purple-400 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all">Start Thread</button>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div>
                            <h3 class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em] mb-3 flex items-center gap-2">
                                <i class="fa-solid fa-user-check text-purple-500"></i> Review Approvals
                            </h3>
                            <div class="space-y-1">${reviewsHtml}</div>
                        </div>
                        
                        ${!isMerged && !isApproved ? `
                        <div class="bg-slate-900 p-6 rounded-3xl border border-slate-800 shadow-inner">
                            <h3 class="text-xs font-black text-slate-300 uppercase tracking-widest mb-4">Submit Your Review</h3>
                            <textarea id="review-comment" class="w-full bg-slate-950 border border-slate-800 rounded-2xl p-4 text-white mb-4 h-24 focus:border-purple-600/50 focus:ring-1 focus:ring-purple-500/20 focus:outline-none placeholder-slate-700 text-sm font-mono" placeholder="Internal review notes (optional)..."></textarea>
                            <div class="flex gap-4">
                                <button onclick="App.submitPRReview(${pr.id}, 'APPROVED')" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white py-3 rounded-xl font-black text-[11px] uppercase tracking-widest transition-all shadow-lg shadow-emerald-900/20 active:scale-95"><i class="fa-solid fa-check-circle mr-2"></i> Approve Changes</button>
                                <button onclick="App.submitPRReview(${pr.id}, 'CHANGES_REQUESTED')" class="flex-1 bg-slate-800 hover:bg-amber-600 text-slate-400 hover:text-white py-3 rounded-xl font-black text-[11px] uppercase tracking-widest transition-all border border-slate-700 hover:border-amber-500 active:scale-95"><i class="fa-solid fa-triangle-exclamation mr-2"></i> Request Fixes</button>
                            </div>
                        </div>` : ''}
                    </div>
                    
                    <div class="p-6 bg-slate-900 border-t border-slate-800 flex justify-between items-center shrink-0">
                        <div class="flex items-center gap-4">
                            <div class="flex -space-x-3">
                                <div class="w-8 h-8 rounded-full bg-slate-800 border-2 border-slate-900 flex items-center justify-center text-xs text-slate-500 shadow-xl"><i class="fa-solid fa-user-shield"></i></div>
                                <div class="w-8 h-8 rounded-full bg-purple-600 border-2 border-slate-900 flex items-center justify-center text-[10px] text-white font-black shadow-xl" title="Approvals Required">1</div>
                            </div>
                            <span class="text-[10px] font-black text-slate-500 uppercase tracking-widest">Merge Readiness: ${isApproved ? 'READY' : 'PENDING'}</span>
                        </div>
                        <button onclick="App.mergePR(${pr.id})" class="${isApproved ? 'bg-purple-600 hover:bg-purple-500 shadow-lg shadow-purple-900/40' : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'} text-white px-8 py-3 rounded-2xl font-black text-xs uppercase tracking-[0.2em] flex items-center transition-all active:scale-95" ${!isApproved ? 'disabled' : ''}>
                            <i class="fa-solid fa-code-merge mr-2"></i> Deploy Merge
                        </button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    },

    async showCreatePRModal() {
        const [branches, issuesData] = await Promise.all([
            this.api('/api/branches'),
            this.api('/api/issues/local')
        ]);
        
        const openIssues = (issuesData?.issues || []).filter(i => i.state === 'OPEN');
        // Final fallback: if API fails, at least show current branch
        let branchList = branches;
        if (!branches || !branches.length) {
            branchList = [this.state.workspace.branch || 'main'];
        }
        
        const optStyle = 'style="background-color: #0b0f19; color: white;"';
        const branchOpts = branchList.map(b => `<option value="${b}" ${b === this.state.workspace.branch ? 'selected' : ''} ${optStyle}>${b}</option>`).join('');
        const targetOpts = branchList.map(b => `<option value="${b}" ${b === 'main' ? 'selected' : ''} ${optStyle}>${b}</option>`).join('');
        const issueOpts = `<option value="" ${optStyle}>-- No Linked Issue --</option>` + openIssues.map(i => `<option value="${i.id}" ${optStyle}>#${i.id}: ${i.title}</option>`).join('');

        const modalHtml = `
            <div id="create-pr-modal" class="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[100] animate-in fade-in zoom-in-95 duration-200">
                <div class="bg-slate-900 border border-slate-700 rounded-3xl w-[550px] max-w-[95vw] max-h-[90vh] shadow-2xl flex flex-col overflow-hidden">
                    <div class="p-6 bg-slate-800 border-b border-slate-700 flex justify-between items-center shrink-0">
                        <h3 class="font-black text-white text-xs uppercase tracking-[0.2em] flex items-center gap-3">
                            <i class="fa-solid fa-code-pull-request text-purple-500"></i> Initialize Pull Request
                        </h3>
                        <button onclick="document.getElementById('create-pr-modal').remove()" class="text-slate-400 hover:text-white transition-colors"><i class="fa-solid fa-xmark"></i></button>
                    </div>
                    <div class="p-8 flex flex-col gap-6 bg-[#0b0f19] overflow-y-auto custom-scrollbar">
                        <div class="space-y-5">
                            <div>
                                <label class="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">PR Title</label>
                                <input type="text" id="cpr-title" placeholder="e.g., Refactor merge logic" class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full outline-none focus:border-purple-600/50 focus:ring-1 focus:ring-purple-500/20 transition-all font-bold">
                            </div>
                            
                            <div class="flex items-center gap-2 bg-slate-950/40 p-2 rounded-2xl border border-slate-800/50">
                                <div class="flex-1">
                                    <label class="block text-[7px] font-black text-slate-600 uppercase tracking-widest px-2 mb-1">Merge From</label>
                                    <select id="cpr-head" class="bg-transparent border-none text-cyan-400 font-mono font-bold w-full text-sm outline-none cursor-pointer">
                                        ${branchOpts}
                                    </select>
                                </div>
                                <div class="shrink-0 text-slate-700 pt-3">
                                    <i class="fa-solid fa-arrow-right-long text-xs"></i>
                                </div>
                                <div class="flex-1">
                                    <label class="block text-[7px] font-black text-slate-600 uppercase tracking-widest px-2 mb-1">Merge Into</label>
                                    <select id="cpr-base" class="bg-transparent border-none text-slate-400 font-mono font-bold w-full text-sm outline-none cursor-pointer">
                                        ${targetOpts}
                                    </select>
                                </div>
                            </div>

                            <div>
                                <label class="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Detailed Description</label>
                                <textarea id="cpr-desc" placeholder="What does this PR change? Include context..." class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full h-28 outline-none focus:border-purple-600/50 focus:ring-1 focus:ring-purple-500/20 transition-all font-mono text-sm resize-none"></textarea>
                            </div>

                            <div>
                                <label class="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Relate Issue ID</label>
                                <select id="cpr-issue" class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full outline-none focus:border-purple-600/50 focus:ring-1 focus:ring-purple-500/20 transition-all font-mono cursor-pointer">
                                    ${issueOpts}
                                </select>
                            </div>

                            <div>
                                <label class="block text-[10px] font-black text-slate-500 uppercase tracking-widest mb-2">Assign Reviewers</label>
                                <input type="text" id="cpr-reviewers" placeholder="Comma separated, e.g. alice, bob" class="bg-slate-950 border border-slate-800 rounded-xl p-4 text-white w-full outline-none focus:border-purple-600/50 focus:ring-1 focus:ring-purple-500/20 transition-all font-mono">
                            </div>
                        </div>
                        
                        <button onclick="App.submitNewPR()" class="bg-purple-600 hover:bg-purple-500 text-white font-black py-4 rounded-2xl uppercase text-[11px] tracking-[0.2em] transition-all shadow-xl shadow-purple-900/40 active:scale-[0.98]">
                            <i class="fa-solid fa-paper-plane mr-2"></i> Submit Proposal
                        </button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        document.getElementById('cpr-title').focus();
    },

    async submitNewPR() {
        const id = (i) => document.getElementById(i);
        const payload = { 
            title: id('cpr-title').value.trim(), 
            desc: id('cpr-desc').value.trim(), 
            head: id('cpr-head').value.trim(), 
            base: id('cpr-base').value.trim(), 
            issue_id: id('cpr-issue').value.trim() || null,
            reviewers: id('cpr-reviewers').value.trim()
        };
        if (!payload.title || !payload.head) return this.toast("Title and Head required", true);
        if (await this.api('/api/pr/create', 'POST', payload)) { 
            this.toast("PR created!"); 
            id('create-pr-modal').remove(); 
            this.loadPRs(); 
        }
    },

    async submitPRReview(pr_id, state) {
        const comment = document.getElementById('review-comment')?.value || (state === 'APPROVED' ? "LGTM!" : "Please fix...");
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

    async addPRComment(pr_id) {
        const text = document.getElementById('pr-new-thread-text').value.trim();
        if (!text) return;
        if (await this.api('/api/pr/comment', 'POST', { pr_id, text })) {
            this.toast("Thread started");
            this.showPRDetails(pr_id);
        }
    },

    async addPRReply(pr_id, thread_id) {
        const text = document.getElementById(`reply-to-${thread_id}`).value.trim();
        if (!text) return;
        if (await this.api('/api/pr/reply', 'POST', { pr_id, thread_id, text })) {
            this.toast("Reply posted");
            this.showPRDetails(pr_id);
        }
    },

    async resolvePRThread(pr_id, thread_id) {
        if (await this.api('/api/pr/resolve', 'POST', { pr_id, thread_id })) {
            this.toast("Thread resolved");
            this.showPRDetails(pr_id);
        }
    },

    async triggerMerge(b) { if(confirm(`Merge ${b}?`)){ if(await this.api('/api/merge','POST',{branch:b})) { this.toast(`Merged ${b}`); this.syncWorkspace(); this.loadGraph(); }}}
};

window.onload = () => App.init();

// ====================================================
// DEEP STUDIO VSCODE ENGINE (EDITOR ONLY)
// ====================================================
const EditorApp = {
    state: {
        activeSidebarArea: 'explorer',
        tabs: [], activeTab: null, activeGroup: 1,
        models: {}, trees: {}, status: null,
        editors: { 1: null, 2: null }, isSplit: false, debounceSaveTimer: null
    },

    async init() {
        this.initMonaco();
        await this.loadTree();
        this.setupDragDrop();
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#editor-context-menu')) {
                const cx = document.getElementById('editor-context-menu');
                if(cx) cx.classList.add('hidden');
            }
        });
    },

    initMonaco() {
        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.36.1/min/vs' }});
        require(['vs/editor/editor.main'], () => {
            const config = {
                theme: 'vs-dark', automaticLayout: true, minimap: { enabled: true, renderCharacters: false },
                bracketPairColorization: { enabled: true }, stickyScroll: { enabled: true }, folding: true,
                guides: { indentation: true, bracketPairs: true }, smoothScrolling: true, fontLigatures: true,
                cursorBlinking: "smooth", cursorSmoothCaretAnimation: "on", renderLineHighlight: "all",
                wordWrap: "on", renderWhitespace: "all", glyphMargin: true, fontSize: 13, fontFamily: "Consolas, 'Courier New', monospace"
            };
            this.state.editors[1] = monaco.editor.create(document.getElementById('monaco-container-1'), config);
            this.state.editors[2] = monaco.editor.create(document.getElementById('monaco-container-2'), config);
            this.state.editors[1].onDidFocusEditorWidget(() => this.focusGroup(1));
            this.state.editors[2].onDidFocusEditorWidget(() => this.focusGroup(2));
            this.state.editors[1].onDidChangeModelContent(() => this.handleContentChange(1));
            this.state.editors[2].onDidChangeModelContent(() => this.handleContentChange(2));
            this.state.editors[1].onDidChangeCursorPosition((e) => this.updateCursorStatus(e.position));
            this.state.editors[2].onDidChangeCursorPosition((e) => this.updateCursorStatus(e.position));
            this.setupProviders();
            this.setupKeybindings();
        });
    },

    toggleSidebar(area) {
        this.state.activeSidebarArea = area;
        ['explorer', 'search', 'outline'].forEach(a => {
            document.getElementById(`editor-view-${a}`)?.classList.add('hidden');
            document.getElementById(`editor-activity-indicator-${a}`)?.classList.add('hidden');
            const icons = document.querySelectorAll('.editor-activity-icon');
            if(icons.length > 0) {
              const icon = icons[['explorer', 'search', 'outline'].indexOf(a)];
              if(icon) { icon.classList.remove('text-white'); icon.classList.add('text-slate-500'); }
            }
        });
        document.getElementById(`editor-view-${area}`)?.classList.remove('hidden');
        document.getElementById(`editor-activity-indicator-${area}`)?.classList.remove('hidden');
        const icons = document.querySelectorAll('.editor-activity-icon');
        if(icons.length > 0) {
            const activeIcon = icons[['explorer', 'search', 'outline'].indexOf(area)];
            if(activeIcon) { activeIcon.classList.remove('text-slate-500'); activeIcon.classList.add('text-white'); }
        }
    },

    focusGroup(groupId) {
        this.state.activeGroup = groupId;
        const g1 = document.getElementById('editor-group-1');
        const g2 = document.getElementById('editor-group-2');
        if(g1) g1.style.opacity = groupId === 1 ? '1' : '0.8';
        if (this.state.isSplit && g2) { g2.style.opacity = groupId === 2 ? '1' : '0.8'; }
    },

    async api(url, method = 'GET', body = null) { return App.api(url, method, body); },
    toast(msg, err=false) { App.toast(msg, err); },
    async loadTree() {
        const [treeData, statusData] = await Promise.all([
            this.api('/api/tree'),
            this.api('/api/status')
        ]);
        if (!treeData || !treeData.tree) return;
        this.state.trees = treeData.tree;
        this.state.status = statusData || { unstaged: [], staged: [], modified: [], untracked: [], deleted: [] };
        this.renderTree();
    },

    getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            py: 'fa-brands fa-python text-[#3776ab]', js: 'fa-brands fa-js text-[#f7df1e]',
            ts: 'fa-solid fa-code text-[#3178c6]', html: 'fa-brands fa-html5 text-[#e34f26]',
            css: 'fa-brands fa-css3-alt text-[#1572b6]', json: 'fa-regular fa-file-lines text-[#cbcb41]',
            yaml: 'fa-solid fa-file-lines text-[#cb171e]', md: 'fa-brands fa-markdown text-[#ffffff]',
            c: 'fa-solid fa-c text-[#a8b9cc]', cpp: 'fa-solid fa-c text-[#00599c]',
            java: 'fa-brands fa-java text-[#b07219]', go: 'fa-solid fa-g text-[#00add8]',
            rust: 'fa-brands fa-rust text-[#dea584]', sh: 'fa-solid fa-terminal text-[#4ebb8e]',
            bash: 'fa-solid fa-terminal text-[#4ebb8e]', php: 'fa-brands fa-php text-[#777bb4]',
            rb: 'fa-solid fa-gem text-[#701516]', txt: 'fa-regular fa-file-lines text-[#cccccc]',
            default: 'fa-regular fa-file-code text-[#cccccc]'
        };
        return icons[ext] || icons.default;
    },

    getGitStatusColor(path) {
        if (!this.state.status) return '';
        const { modified = [], untracked = [], deleted = [], staged = [] } = this.state.status;
        if (staged.includes(path)) return 'text-[#4ea1df]'; 
        if (untracked.includes(path)) return 'text-[#73c991]'; 
        if (modified.includes(path)) return 'text-[#e2c08d]'; 
        if (deleted.includes(path)) return 'text-[#f14c4c]'; 
        return '';
    },

    getDirGitStatus(dirPath, node) {
        let color = '';
        const check = (n, currentPath) => {
            if (n._type === 'dir') {
                for(let k in n.children) check(n.children[k], n.children[k].path || `${currentPath}/${k}`);
            } else {
                const c = this.getGitStatusColor(n.path || currentPath);
                if (c) color = c; 
            }
        };
        check(node, dirPath);
        return color;
    },

    renderTree() {
        const renderNode = (nodeMap, name, depth = 0) => {
            const node = nodeMap[name];
            const isDir = node._type === 'dir';
            const currentPath = node.path || (isDir ? name : ''); 
            const isActive = this.state.activeTab === currentPath;
            const indent = depth * 12;

            if (isDir) {
                let childHtml = '';
                const sortedKeys = Object.keys(node.children).sort((a, b) => {
                    const typeA = node.children[a]._type;
                    const typeB = node.children[b]._type;
                    if (typeA === typeB) return a.localeCompare(b);
                    return typeA === 'dir' ? -1 : 1;
                });
                for (const key of sortedKeys) childHtml += renderNode(node.children, key, depth + 1);
                
                const dirColor = this.getDirGitStatus(currentPath, node) || 'text-slate-300';
                return `
                <div>
                    <div class="cursor-pointer flex items-center py-[2px] hover:bg-slate-800/50 transition-colors" 
                         style="padding-left: ${indent}px;"
                         onclick="this.nextElementSibling.classList.toggle('hidden'); const i = this.querySelector('.fa-chevron-right, .fa-chevron-down'); if(i.classList.contains('fa-chevron-right')) { i.classList.replace('fa-chevron-right', 'fa-chevron-down'); } else { i.classList.replace('fa-chevron-down', 'fa-chevron-right'); }">
                        <i class="fa-solid fa-chevron-right text-[8px] text-slate-500 w-4 text-center"></i>
                        <span class="${dirColor} truncate">${name}</span>
                    </div>
                    <div class="hidden">
                        ${childHtml}
                    </div>
                </div>`;
            } else {
                const iconClass = this.getFileIcon(name);
                const fileColor = this.getGitStatusColor(currentPath) || (isActive ? 'text-white' : 'text-slate-300');
                const activeBg = isActive ? 'bg-cyan-900/60' : '';
                
                return `
                <div class="cursor-pointer flex items-center py-[2px] hover:bg-slate-800/50 transition-colors ${activeBg}" 
                     style="padding-left: ${indent + 16}px;"
                     onclick="EditorApp.openFile('${currentPath}')"
                     oncontextmenu="EditorApp.showContextMenu(event, '${currentPath}', 'file')"
                     draggable="true" ondragstart="event.dataTransfer.setData('text/plain', '${currentPath}')">
                    <i class="${iconClass} w-5 text-center text-[10px]"></i> 
                    <span class="${fileColor} truncate">${name}</span>
                </div>`;
            }
        };

        const rootKeys = Object.keys(this.state.trees).sort((a,b) => {
            const typeA = this.state.trees[a]._type;
            const typeB = this.state.trees[b]._type;
            if (typeA === typeB) return a.localeCompare(b);
            return typeA === 'dir' ? -1 : 1;
        });

        let html = '<div class="pt-1">';
        for (const key of rootKeys) html += renderNode(this.state.trees, key);
        html += '</div>';

        const treeEl = document.getElementById('editor-explorer-tree');
        if(treeEl) treeEl.innerHTML = html;
    },

    collapseAll() {
        document.querySelectorAll('#editor-explorer-tree .fa-chevron-down').forEach(el => {
            el.classList.replace('fa-chevron-down', 'fa-chevron-right');
            el.closest('div').nextElementSibling.classList.add('hidden');
        });
    },
    async openFile(path, group = null) {
        if (!path) return;
        const targetGroup = group || this.state.activeGroup;
        
        if (!this.state.tabs.includes(path)) {
            this.state.tabs.push(path);
        }
        
        this.state.activeTab = path;
        this.renderTabs();
        this.renderTree();
        this.updateBreadcrumbs(path);
        
        const editor = this.state.editors[targetGroup];
        if (!editor) return;

        if (this.state.models[path]) {
            editor.setModel(this.state.models[path].monacoModel);
            this.updateCursorStatus(editor.getPosition());
            return;
        }

        const data = await this.api(`/api/file?path=${encodeURIComponent(path)}`);
        if (!data || data.error) return this.toast(`Failed to load ${path}`, true);

        const ext = path.split('.').pop().toLowerCase();
        const langs = { py: 'python', js: 'javascript', ts: 'typescript', html: 'html', css: 'css', json: 'json', yaml: 'yaml', md: 'markdown', c: 'c', cpp: 'cpp', java: 'java', go: 'go', rs: 'rust', sh: 'shell', php: 'php', rb: 'ruby', txt: 'plaintext' };
        
        const model = monaco.editor.createModel(data.isBinary ? `// System Note: ${data.content}` : data.content, langs[ext] || 'plaintext');
        model.updateOptions({ tabSize: 4, insertSpaces: true });
        
        this.state.models[path] = { monacoModel: model, isBinary: !!data.isBinary, dirty: false };

        editor.setModel(model);
        if(data.isBinary) editor.updateOptions({ readOnly: true });
        else editor.updateOptions({ readOnly: false });
        
        this.updateCursorStatus(editor.getPosition());
    },

    closeTab(path, e) {
        if(e) e.stopPropagation();
        this.state.tabs = this.state.tabs.filter(t => t !== path);
        
        if (this.state.activeTab === path) {
            this.state.activeTab = this.state.tabs.length > 0 ? this.state.tabs[this.state.tabs.length - 1] : null;
            if (this.state.activeTab) {
                this.openFile(this.state.activeTab);
            } else {
                this.state.editors[1].setModel(null);
                this.state.editors[2].setModel(null);
                this.updateBreadcrumbs('');
            }
        }
        this.renderTabs();
    },

    renderTabs() {
        const tabsEl = document.getElementById('editor-tabs');
        if (!tabsEl) return;
        
        tabsEl.innerHTML = this.state.tabs.map(path => {
            const filename = path.split('/').pop();
            const isActive = this.state.activeTab === path;
            const icon = this.getFileIcon(filename);
            const isDirty = this.state.models[path]?.dirty;
            
            return `
            <div class="flex items-center min-w-[120px] max-w-[200px] h-full px-3 border-r border-slate-800 cursor-pointer group ${isActive ? 'editor-active-tab' : 'bg-slate-900 text-slate-500 hover:bg-slate-900/60 hover:text-slate-300'}"
                 onclick="EditorApp.openFile('${path}')"
                 onauxclick="if(event.button === 1) EditorApp.closeTab('${path}', event)"
                 ondblclick="EditorApp.showCommandPalette('Rename: ${path}')">
                <i class="${icon} text-[12px] mr-2"></i>
                <span class="text-[12px] truncate flex-1">${filename}</span>
                <div class="w-4 h-4 flex items-center justify-center ml-2 rounded hover:bg-white/10 ${isDirty ? 'visible' : 'invisible group-hover:visible'}" onclick="EditorApp.closeTab('${path}', event)">
                    ${isDirty && !isActive ? '<div class="w-2 h-2 rounded-full bg-white"></div>' : '<i class="fa-solid fa-xmark text-[10px]"></i>'}
                </div>
            </div>`;
        }).join('');
    },

    updateBreadcrumbs(path) {
        const bc = document.getElementById('editor-breadcrumbs');
        if(!bc) return;
        if(!path) { bc.innerHTML = ''; return; }
        const parts = path.split('/');
        bc.innerHTML = parts.map((p, i) => `
            <span class="${i === parts.length - 1 ? 'text-slate-300' : 'text-slate-500'}">${p}</span>
            ${i < parts.length - 1 ? '<i class="fa-solid fa-chevron-right text-[8px] mx-1 opacity-50"></i>' : ''}
        `).join('');
    },

    toggleSplit() {
        this.state.isSplit = !this.state.isSplit;
        const g2 = document.getElementById('editor-group-2');
        const div = document.getElementById('editor-split-divider');
        
        if (this.state.isSplit) {
            g2.classList.remove('hidden'); div.classList.remove('hidden');
            const currentModel = this.state.editors[1].getModel();
            if (currentModel) this.state.editors[2].setModel(currentModel);
            this.focusGroup(2);
        } else {
            g2.classList.add('hidden'); div.classList.add('hidden');
            this.focusGroup(1);
        }
    },
    setupProviders() {
        const langs = ['python', 'javascript', 'typescript', 'html', 'css', 'json', 'yaml', 'markdown', 'c', 'cpp', 'java', 'go', 'rust', 'shell', 'php', 'ruby'];
        langs.forEach(lang => {
            monaco.languages.registerCompletionItemProvider(lang, {
                provideCompletionItems: (model, position) => {
                    const word = model.getWordUntilPosition(position);
                    const range = { startLineNumber: position.lineNumber, endLineNumber: position.lineNumber, startColumn: word.startColumn, endColumn: word.endColumn };
                    return { suggestions: [
                        { label: 'log', kind: monaco.languages.CompletionItemKind.Snippet, documentation: 'Log Snippet', insertText: (lang==='python' ? 'print($1)' : 'console.log($1);'), insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet, range }
                    ]};
                }
            });
            
            monaco.languages.registerHoverProvider(lang, {
                provideHover: (model, position) => {
                    const word = model.getWordAtPosition(position);
                    if (word && word.word.length > 3) {
                        return { contents: [ { value: `**${word.word}**` }, { value: `Length: ${word.word.length} chars` } ] };
                    }
                }
            });
        });

        const validate = (model, langId) => {
            const markers = [];
            const text = model.getValue();
            const lines = text.split('\n');
            lines.forEach((line, i) => {
                const ln = i + 1;
                if (langId === 'python' && line.match(/^(def|class|if|else|elif|try|except|for|while).*[^:]\s*$/)) {
                    markers.push({ severity: monaco.MarkerSeverity.Error, startLineNumber: ln, startColumn: 1, endLineNumber: ln, endColumn: line.length + 1, message: "Missing colon ':'" });
                }
            });
            monaco.editor.setModelMarkers(model, "linting", markers);
            this.updateErrorStatus(markers.length, 0);
        };

        this.state.editors[1].onDidChangeModelContent(() => { const m = this.state.editors[1].getModel(); if(m) validate(m, m.getLanguageId()); });
        this.state.editors[2].onDidChangeModelContent(() => { const m = this.state.editors[2].getModel(); if(m) validate(m, m.getLanguageId()); });
    },

    setupKeybindings() {
        const bind = (editor) => {
            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => this.executeCommand('save'));
            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyP, () => this.showCommandPalette('>'));
            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyP, () => this.showCommandPalette(''));
            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Backslash, () => this.toggleSplit());
            editor.addCommand(monaco.KeyMod.Shift | monaco.KeyMod.Alt | monaco.KeyCode.KeyF, () => this.executeCommand('format'));
        };
        bind(this.state.editors[1]); bind(this.state.editors[2]);
        
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'p') { e.preventDefault(); this.showCommandPalette(''); }
            if (e.ctrlKey && e.shiftKey && e.key === 'P') { e.preventDefault(); this.showCommandPalette('>'); }
            if (e.ctrlKey && e.key === '\\') { e.preventDefault(); this.toggleSplit(); }
            if (e.ctrlKey && e.key === 's') { e.preventDefault(); this.executeCommand('save'); }
        });
    },

    async executeCommand(cmd) {
        if (cmd === 'save') {
           const path = this.state.activeTab;
           if (!path || !this.state.models[path]) return;
           const content = this.state.models[path].monacoModel.getValue();
           const res = await this.api('/api/file/save', 'POST', { filepath: path, content });
           if (res) {
               this.state.models[path].dirty = false;
               this.renderTabs();
               this.toast("File saved");
               await App.refreshStatus();
           }
        } else if (cmd === 'format') {
           const path = this.state.activeTab;
           if (!path || !this.state.models[path]) return;
           this.toast("Formatting code (Browser-native)...");
           const editor = this.state.editors[this.state.activeGroup];
           if (editor) {
               editor.getAction('editor.action.formatDocument').run().then(() => {
                   this.toast("Formatting applied!");
               });
           }
        }
    },

    handleContentChange(_) {
        const path = this.state.activeTab;
        if (!path || !this.state.models[path]) return;
        this.state.models[path].dirty = true;
        this.renderTabs();
        
        clearTimeout(this.state.debounceSaveTimer);
        this.state.debounceSaveTimer = setTimeout(() => { this.executeCommand('save'); }, 1000);
    },

    updateCursorStatus(pos) {
        const cursorEl = document.getElementById('editor-status-cursor');
        if (cursorEl && pos) { cursorEl.innerText = `Ln ${pos.lineNumber}, Col ${pos.column}`; }
        const model = this.state.editors[this.state.activeGroup]?.getModel();
        if (model) {
            const langEl = document.getElementById('editor-status-lang');
            if (langEl) langEl.innerText = model.getLanguageId();
        }
    },
    
    updateErrorStatus(errors, warnings) {
        const el = document.getElementById('editor-status-errors');
        if (el) {
            if (errors === 0 && warnings === 0) el.classList.add('hidden');
            else {
                el.classList.remove('hidden');
                const eEl = document.getElementById('editor-status-error-count');
                const wEl = document.getElementById('editor-status-warn-count');
                if(eEl) eEl.innerText = errors;
                if(wEl) wEl.innerText = warnings;
            }
        }
    },

    showCommandPalette(prefix = '>', selectAll = false) {
        const pal = document.getElementById('editor-command-palette');
        if(!pal) return;
        pal.classList.remove('hidden');
        const input = document.getElementById('editor-cmd-input');
        input.value = prefix;
        input.focus();
        if (selectAll) input.select();
        this.filterCommandPalette();

        input.oninput = () => this.filterCommandPalette();
        input.onkeydown = (e) => {
            if (e.key === 'Escape') { pal.classList.add('hidden'); } 
            else if (e.key === 'Enter') {
                const active = document.querySelector('.editor-cmd-item.bg-cyan-600');
                if (active) active.click();
            } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                const items = Array.from(document.querySelectorAll('.editor-cmd-item'));
                if (!items.length) return;
                let idx = items.findIndex(el => el.classList.contains('bg-cyan-600'));
                if (idx >= 0) items[idx].classList.remove('bg-cyan-600', 'text-white');
                idx = e.key === 'ArrowDown' ? (idx + 1) % items.length : (idx - 1 < 0 ? items.length - 1 : idx - 1);
                items[idx].classList.add('bg-cyan-600', 'text-white');
                items[idx].scrollIntoView({ block: 'nearest' });
            }
        };
    },

    filterCommandPalette() {
        const input = document.getElementById('editor-cmd-input').value;
        const resEl = document.getElementById('editor-cmd-results');
        
        let html = '';
        if (input.startsWith('Rename:')) {
             html = '<div class="px-3 py-1 text-slate-400 text-xs">Press Enter to rename (Mock)</div>';
        } else if (input.startsWith('>')) {
            const query = input.slice(1).trim().toLowerCase();
            const commands = [
                { label: 'File: Save', cmd: () => this.executeCommand('save') },
                { label: 'File: New File', cmd: () => this.newFile() },
                { label: 'File: New Folder', cmd: () => this.newFolder() },
                { label: 'Format Document', cmd: () => this.executeCommand('format') },
                { label: 'View: Toggle Split Editor', cmd: () => this.toggleSplit() },
                { label: 'View: Explorer', cmd: () => this.toggleSidebar('explorer') },
                { label: 'View: Search', cmd: () => this.toggleSidebar('search') }
            ];
            
            const filtered = commands.filter(c => c.label.toLowerCase().includes(query));
            html = filtered.map((c, i) => `
                <div class="editor-cmd-item cursor-pointer px-3 py-[6px] flex items-center ${i === 0 ? 'bg-cyan-600 text-white' : 'hover:bg-slate-800/50'}"
                     onclick="document.getElementById('editor-command-palette').classList.add('hidden'); EditorApp.executeCommandObj(${i})">
                    ${c.label}
                </div>
            `).join('');
            this._cmdRefs = filtered;
        } else {
            const query = input.trim().toLowerCase();
            const files = [];
            const collect = (node, path) => {
                if (node._type === 'dir') { for(let k in node.children) collect(node.children[k], node.children[k].path || `${path}/${k}`); }
                else files.push(node.path || path);
            };
            for(let k in this.state.trees) collect(this.state.trees[k], this.state.trees[k].path || k);
            
            const filtered = files.filter(f => f.toLowerCase().includes(query)).slice(0, 50);
            html = filtered.map((f, i) => `
                <div class="editor-cmd-item cursor-pointer px-3 py-[6px] flex items-center ${i === 0 ? 'bg-cyan-600 text-white' : 'hover:bg-slate-800/50'}"
                     onclick="document.getElementById('editor-command-palette').classList.add('hidden'); EditorApp.openFile('${f}')">
                    <i class="${this.getFileIcon(f)} w-5 text-center mr-2 text-[12px]"></i>
                    ${f.split('/').pop()} <span class="text-[10px] text-slate-500 ml-2">${f}</span>
                </div>
            `).join('');
        }
        resEl.innerHTML = html || '<div class="px-3 py-1 text-slate-500 text-xs">No matching results</div>';
    },

    executeCommandObj(idx) {
        if (this._cmdRefs && this._cmdRefs[idx]) this._cmdRefs[idx].cmd();
    },

    updateOutline() {
        const path = this.state.activeTab;
        if (!path || !this.state.models[path]) return;
        const model = this.state.models[path].monacoModel;
        const text = model.getValue();
        const lang = model.getLanguageId();
        
        let regex = null;
        if (lang === 'python') regex = /^(def|class)\s+([a-zA-Z0-9_]+)/gm;
        if (lang === 'javascript' || lang === 'typescript') regex = /(function|class)\s+([a-zA-Z0-9_]+)/gm;
        if (lang === 'java' || lang === 'php') regex = /(class|interface|function)\s+([a-zA-Z0-9_]+)/gm;
        
        const outlineEl = document.getElementById('editor-outline-tree');
        if (!outlineEl) return;
        
        if (!regex) {
           outlineEl.innerHTML = '<div class="text-slate-500 p-2 text-xs">Outline not supported for this language.</div>';
           return;
        }
        
        let match;
        let html = '';
        while ((match = regex.exec(text)) !== null) {
            const type = match[1];
            const name = match[2];
            const icon = (type === 'class' || type === 'interface') ? 'fa-solid fa-cubes text-[#e2c08d]' : 'fa-solid fa-cube text-[#b180d7]';
            const pos = model.getPositionAt(match.index);
            html += `
                <div class="cursor-pointer hover:bg-slate-800/50 py-[2px] px-4 flex items-center truncate text-slate-300" 
                     onclick="EditorApp.state.editors[EditorApp.state.activeGroup].revealPositionInCenter({lineNumber: ${pos.lineNumber}, column: ${pos.column}}); EditorApp.state.editors[EditorApp.state.activeGroup].setPosition({lineNumber: ${pos.lineNumber}, column: ${pos.column}});">
                    <i class="${icon} w-5 text-center text-[10px] mr-1"></i> ${name}
                </div>
            `;
        }
        
        outlineEl.innerHTML = html || '<div class="text-slate-500 p-2 text-xs">No symbols found</div>';
    },

    showContextMenu(e, path, type) {
        e.preventDefault(); e.stopPropagation();
        const menu = document.getElementById('editor-context-menu');
        menu.style.left = `${e.pageX}px`; menu.style.top = `${e.pageY}px`;
        menu.classList.remove('hidden');
        menu.innerHTML = `
            <div class="hover:bg-cyan-600 hover:text-white px-6 py-1 cursor-pointer transition-colors" onclick="EditorApp.newFile('${path}')">New File</div>
            <div class="hover:bg-cyan-600 hover:text-white px-6 py-1 cursor-pointer transition-colors" onclick="EditorApp.newFolder('${path}')">New Folder</div>
            <div class="h-[1px] bg-slate-700 my-1"></div>
            <div class="hover:bg-cyan-600 hover:text-white px-6 py-1 cursor-pointer transition-colors" onclick="EditorApp.showCommandPalette('Rename: ${path}')">Rename</div>
            <div class="hover:bg-[#f14c4c] hover:text-white px-6 py-1 cursor-pointer text-[#f14c4c] transition-colors" onclick="EditorApp.deletePath('${path}')">Delete</div>
            <div class="h-[1px] bg-slate-700 my-1"></div>
            <div class="hover:bg-cyan-600 hover:text-white px-6 py-1 cursor-pointer transition-colors" onclick="navigator.clipboard.writeText('${path}'); EditorApp.toast('Copied path')">Copy Path</div>
        `;
    },

    async deletePath(path) {
        document.getElementById('editor-context-menu').classList.add('hidden');
        if(confirm(`Are you sure you want to delete ${path}?`)) this.toast(`Mock Delete: ${path}`);
    },
    
    async newFile(basePath = '') {
        document.getElementById('editor-context-menu').classList.add('hidden');
        const name = prompt("File Name:");
        if (name) {
            const path = (basePath ? basePath + '/' : '') + name;
            const res = await this.api('/api/item/create', 'POST', { path, type: 'file' });
            if (res) {
                await this.loadTree();
                this.openFile(path);
            }
        }
    },
    async newFolder(basePath = '') {
        document.getElementById('editor-context-menu').classList.add('hidden');
        const name = prompt("Folder Name:");
        if (name) {
            const path = (basePath ? basePath + '/' : '') + name;
            const res = await this.api('/api/item/create', 'POST', { path, type: 'folder' });
            if (res) await this.loadTree();
        }
    },

    setupDragDrop() {
        let isResizing = false;
        const divider = document.getElementById('editor-split-divider');
        const g1 = document.getElementById('editor-group-1');
        
        if (divider && g1) {
            divider.onmousedown = (e) => { isResizing = true; };
            document.onmousemove = (e) => {
                if (!isResizing) return;
                const newWidth = e.clientX - 300; 
                if(newWidth > 100) g1.style.flex = `0 0 ${newWidth}px`;
            };
            document.onmouseup = () => { if(isResizing) { isResizing = false; this.state.editors[1].layout(); this.state.editors[2].layout(); } };
        }
        setInterval(() => this.updateOutline(), 3000);
    }
};
