/* Deep Platform Dashboard — app.js */

// ── State Manager ──────────────────────────────────────────────────
const state = {
  activeTab: 'graph',
  selectedPR: null,
  selectedIssue: null,
  selectedCommit: null,
  selectedFile: null,
  commits: [],
  refs: {},
  prs: [],
  issues: [],
  work: {},
  activity: [],
  tree: null,
  expandedFolders: new Set(['']),
  graphLoaded: false,
  networkInstance: null,
  monacoInstance: null,
  fileOriginalContent: '',
};

// ── API Layer ──────────────────────────────────────────────────────
async function api(path, opts = {}) {
  try {
    const r = await fetch(path, opts);
    const json = await r.json();
    if (!json.success) throw new Error(json.error || 'Unknown error');
    return json.data;
  } catch (e) {
    console.error('API error:', path, e);
    throw e;
  }
}

async function apiPost(path, body = {}) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ── Toast System ───────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut .3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ── Tab Switching ──────────────────────────────────────────────────
function switchTab(tab) {
  state.activeTab = tab;
  
  // Hide all tabs by default, then show the active one via hidden class
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
  document.querySelectorAll('.nav-item[data-tab]').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
  
  const el = document.getElementById('tab-' + tab);
  if (el) el.classList.remove('hidden');

  // Update URL
  const url = new URL(window.location);
  url.searchParams.set('tab', tab);
  if (tab !== 'prs') url.searchParams.delete('pr');
  if (tab !== 'issues') url.searchParams.delete('issue');
  history.replaceState(null, '', url);

  // Load data for tab
  if (tab === 'graph' && !state.graphLoaded) loadGraph();
  if (tab === 'code') initCodeTab();
  if (tab === 'prs') loadPRs();
  if (tab === 'issues') loadIssues();
  if (tab === 'work') { loadWork(); loadActivity(); }

  closeDetail();
}

// ── Deep Linking ───────────────────────────────────────────────────
function parseDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get('tab') || 'graph';
  switchTab(tab);
  const prId = params.get('pr');
  if (prId && tab === 'prs') setTimeout(() => selectPR(parseInt(prId)), 500);
  const issueId = params.get('issue');
  if (issueId && tab === 'issues') setTimeout(() => selectIssue(parseInt(issueId)), 500);
}

// ── Skeleton Loader ────────────────────────────────────────────────
function showSkeleton(containerId, count = 4) {
  const c = document.getElementById(containerId);
  c.innerHTML = Array(count).fill('<div class="skeleton"></div>').join('');
}

function showEmpty(containerId, icon, message) {
  document.getElementById(containerId).innerHTML =
    `<div class="empty-state"><div class="empty-icon">${icon}</div><p>${message}</p></div>`;
}

// ── Graph ──────────────────────────────────────────────────────────
async function loadGraph(force = false) {
  if (force) {
    state.graphLoaded = false;
    if (state.networkInstance) {
      state.networkInstance.destroy();
      state.networkInstance = null;
    }
  }

  if (state.graphLoaded) return;
  
  const loadingEl = document.getElementById('loading-graph');
  loadingEl.classList.remove('hidden');
  
  try {
    const [commits, refs] = await Promise.all([api('/api/log'), api('/api/refs')]);
    state.commits = commits;
    state.refs = refs;
    renderBranches();
    
    // Convert commits to Vis.js DataSet
    const nodes = new vis.DataSet();
    const edges = new vis.DataSet();
    
    const branchTips = {};
    for (const [name, sha] of Object.entries(refs.branches || {})) branchTips[sha] = name;

    commits.forEach((c, idx) => {
      let label = c.message.split('\n')[0];
      if (branchTips[c.sha]) {
        label = `[${branchTips[c.sha]}]\n${label}`;
      }
      
      nodes.add({
        id: c.sha,
        label: label,
        title: `${c.sha.slice(0, 7)} - ${c.author}`,
        shape: 'box',
        color: {
          background: c.sha === state.selectedCommit ? '#58a6ff12' : '#161b22',
          border: c.sha === state.selectedCommit ? '#58a6ff' : '#30363d',
          highlight: { background: '#58a6ff22', border: '#58a6ff' }
        },
        font: { color: '#c9d1d9', face: 'Inter' },
        borderWidth: 1,
        level: idx // Basic linear approximation for hierarchy
      });

      (c.parents || []).forEach(p => {
        edges.add({
          from: c.sha,
          to: p,
          arrows: 'to',
          color: { color: '#30363d', highlight: '#58a6ff' },
          width: 2
        });
      });
    });

    const container = document.getElementById('dag');
    const data = { nodes, edges };
    const options = {
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'UD',
          sortMethod: 'directed',
          nodeSpacing: 150,
          levelSeparation: 80
        }
      },
      physics: {
        enabled: true,
        hierarchicalRepulsion: {
          nodeDistance: 150
        }
      },
      interaction: {
        hover: true,
        tooltipDelay: 100
      }
    };

    if (!state.networkInstance) {
      state.networkInstance = new vis.Network(container, data, options);
      
      // Stop physics after stabilization to prevent flickering
      state.networkInstance.on("stabilizationIterationsDone", function () {
        state.networkInstance.setOptions({ physics: false });
      });

      state.networkInstance.on("click", function (params) {
        if (params.nodes.length > 0) {
          selectCommit(params.nodes[0]);
        }
      });
    } else {
      state.networkInstance.setData(data);
    }
    
    state.graphLoaded = true;
    updateCounts();
  } catch (e) {
    showToast('Failed to load graph', 'error');
  } finally {
    loadingEl.classList.add('hidden');
  }
}

function renderBranches() {
  const list = document.getElementById('branch-list');
  const { refs } = state;
  if (!refs.branches) { list.innerHTML = ''; return; }
  let html = '';
  for (const [name, sha] of Object.entries(refs.branches)) {
    const isCurrent = name === refs.current_branch;
    html += `<div class="branch-item${isCurrent ? ' current' : ''}" onclick="checkoutBranch('${name}')" title="${name} → ${sha.slice(0, 7)}">
      ${isCurrent ? '●' : '○'} ${escHtml(name)} <span class="branch-sha">${sha.slice(0, 7)}</span>
    </div>`;
  }
  list.innerHTML = html;
}

async function createBranch() {
  const input = document.getElementById('new-branch-name');
  const name = input.value.trim();
  if (!name) return;
  const author = prompt('Enter author name for this branch action:', 'WebIDE') || 'WebIDE';
  
  try {
    input.disabled = true;
    const res = await apiPost('/api/branch/create', { name, author });
    showToast(res.message, 'success');
    input.value = '';
    loadGraph(true); // Force reload refs
    if (state.activeTab === 'code') loadTree();
  } catch(e) {
    showToast(e.message || 'Failed to create branch', 'error');
  } finally {
    input.disabled = false;
  }
}

async function checkoutBranch(name) {
  if (state.refs.current_branch === name) return; // already here
  const author = prompt('Enter author name for checkout:', 'WebIDE') || 'WebIDE';
  
  try {
    const res = await apiPost('/api/branch/checkout', { name, author });
    showToast(res.message, 'success');
    loadGraph(true); // Force reload refs
    if (state.activeTab === 'code') loadTree();
  } catch(e) {
    showToast(e.message || 'Failed to checkout branch. Do you have uncommitted changes?', 'error');
  }
}

async function selectCommit(sha) {
  state.selectedCommit = sha;
  try {
    const [detail, diff] = await Promise.all([api('/api/object/' + sha), api('/api/diff/' + sha)]);
    openDetail();
    document.getElementById('detail-header').innerHTML =
      `<h2>${escHtml(detail.message || sha)}</h2><div class="detail-subtitle">${sha}</div>`;
    let body = `<div class="detail-section"><h4>Author</h4><p>${escHtml(detail.author || '')}</p></div>`;
    body += `<div class="detail-section"><h4>Date</h4><p>${new Date((detail.timestamp || 0) * 1000).toLocaleString()}</p></div>`;
    if (detail.parents && detail.parents.length)
      body += `<div class="detail-section"><h4>Parents</h4><p style="font-family:monospace;font-size:12px">${detail.parents.map(p => p.slice(0, 7)).join(', ')}</p></div>`;
    if (diff && diff.length)
      body += `<div class="detail-section"><h4>Changes (${diff.length} files)</h4><pre>${diff.map(d => `${d.status.toUpperCase().padEnd(9)} ${d.path}`).join('\n')}</pre></div>`;
    document.getElementById('detail-body').innerHTML = body;
  } catch (e) { showToast('Failed to load commit details', 'error'); }
}

function copySHA(sha) {
  navigator.clipboard.writeText(sha).then(() => showToast('SHA copied: ' + sha.slice(0, 7), 'success'));
}

// ── Web IDE (Code Tab) ─────────────────────────────────────────────
async function initCodeTab() {
  // 1. Init Monaco Editor
  if (!state.monacoInstance) {
    if (window.require) {
      window.require(['vs/editor/editor.main'], function() {
        state.monacoInstance = monaco.editor.create(document.getElementById('monaco-container'), {
          value: '// Select a file from the workspace to start editing.',
          language: 'javascript',
          theme: 'vs-dark',
          automaticLayout: true,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "'JetBrains Mono', monospace",
        });
        
        state.monacoInstance.onDidChangeModelContent(() => {
          updateCommitBtn();
        });
      });
    } else {
      setTimeout(initCodeTab, 100); // Polling until require loads
      return;
    }
  }

  // 2. Load Tree
  await loadTree();
}

async function loadTree() {
  const treeContainer = document.getElementById('file-tree');
  try {
    const rawTree = await api('/api/tree');
    // rawTree is hierarchical from backend, but user requested buildTree logic.
    // If backend already hierarchical, we translate it or just use it.
    // The user's buildTree expects a flat list. I'll use the hierarchical data directly 
    // but adapt it to the user's renderTree logic.
    state.tree = rawTree;
    renderTreeLayout();
  } catch (e) {
    showToast('Failed to load workspace tree', 'error');
  }
}

function renderTreeLayout() {
  const container = document.getElementById('file-tree');
  if (!state.tree) return;
  
  // Use a simplified version of PART 3 logic that fits our hierarchical data
  container.innerHTML = '';
  renderTreeRecursive(state.tree.children, container);
}

function renderTreeRecursive(nodes, container) {
  nodes.forEach(item => {
    const el = document.createElement("div");
    const isFolder = item.type === 'folder';

    if (!isFolder) {
      el.className = `pl-4 py-1 cursor-pointer hover:bg-slate-800 hover:text-cyan-400 text-sm flex items-center gap-2 ${state.selectedFile === item.path ? 'bg-slate-800 text-cyan-400 border-l-2 border-cyan-400' : 'text-slate-400'}`;
      el.innerHTML = `<span class="opacity-70 text-xs">📄</span> <span class="truncate">${item.name}</span>`;
      el.onclick = () => openFile(item.path);
    } else {
      el.className = "pl-2 py-1 font-medium cursor-pointer hover:bg-slate-800 text-sm text-slate-300 flex items-center gap-2";
      const isExpanded = state.expandedFolders.has(item.path);
      el.innerHTML = `<span class="transition-transform duration-200 ${isExpanded ? 'rotate-90' : ''}">▶</span> <span>📁 ${item.name}</span>`;

      const childContainer = document.createElement("div");
      childContainer.className = `ml-3 border-l border-slate-700/50 ${isExpanded ? '' : 'hidden'}`;

      el.onclick = () => {
        if (state.expandedFolders.has(item.path)) {
          state.expandedFolders.delete(item.path);
        } else {
          state.expandedFolders.add(item.path);
        }
        renderTreeLayout();
      };

      renderTreeRecursive(item.children, childContainer);
      container.appendChild(el);
      container.appendChild(childContainer);
      return;
    }

    container.appendChild(el);
  });
}

async function openFile(path) {
  state.selectedFile = path;
  renderTreeLayout();
  
  const loadingOverlay = document.getElementById('editor-loading-overlay');
  if (loadingOverlay) loadingOverlay.classList.remove('hidden');
  
  if (state.monacoInstance) {
    state.monacoInstance.updateOptions({ readOnly: true });
  }

  try {
    const res = await api('/api/file?path=' + encodeURIComponent(path));
    // Backend returns { content, is_binary, is_new, path }
    
    if (state.monacoInstance) {
      if (res.is_binary) {
        state.monacoInstance.setValue("// " + (res.content || "Binary file cannot be displayed"));
        state.monacoInstance.updateOptions({ readOnly: true });
      } else {
        state.monacoInstance.setValue(res.content || "");
        state.fileOriginalContent = res.content || "";
        state.monacoInstance.updateOptions({ readOnly: false });
      }
      
      setLanguage(path);
      state.currentFile = path;
      updateCommitBtn();
    }
  } catch (e) {
    showToast(e.message || `Failed to load ${path}`, 'error');
    if (state.monacoInstance) {
      state.monacoInstance.setValue('// Error loading file: ' + e.message);
      state.monacoInstance.updateOptions({ readOnly: true });
    }
  } finally {
    if (loadingOverlay) loadingOverlay.classList.add('hidden');
  }
}

function setLanguage(path) {
  const ext = path.split('.').pop().toLowerCase();
  const map = {
    js: "javascript",
    py: "python",
    html: "html",
    css: "css",
    json: "json",
    md: "markdown",
    txt: "plaintext",
    sh: "shell",
    cpp: "cpp",
    c: "cpp",
    go: "go",
    ts: "typescript"
  };

  if (state.monacoInstance) {
    monaco.editor.setModelLanguage(state.monacoInstance.getModel(), map[ext] || "plaintext");
  }
}

function newFile() {
  const name = prompt("Enter file path:");
  if (!name) return;

  state.currentFile = name;
  state.selectedFile = name;
  if (state.monacoInstance) {
    state.monacoInstance.setValue("");
    state.monacoInstance.updateOptions({ readOnly: false });
    setLanguage(name);
  }
  renderTreeLayout();
}

async function createNewFilePrompt() {
  const name = prompt('Enter new file path (relative to root):');
  if (!name) return;
  const author = prompt('Your name:', 'WebIDE') || 'WebIDE';
  try {
    await apiPost('/api/file/create', { path: name, author });
    showToast(`File created: ${name}`, 'success');
    await loadTree();
    
    // Auto-select the new file by expanding its parent folders
    const parts = name.split('/');
    let currentPath = '';
    parts.slice(0, -1).forEach(part => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      state.expandedFolders.add(currentPath);
    });
    
    selectFile(name);
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function deleteFile(path) {
  if (!confirm(`Are you sure you want to delete ${path}?`)) return;
  const author = prompt('Your name:', 'WebIDE') || 'WebIDE';
  try {
    await apiPost('/api/file/delete', { path, author });
    showToast(`Deleted ${path}`, 'success');
    if (state.selectedFile === path) {
      state.selectedFile = null;
      if (state.monacoInstance) state.monacoInstance.setValue('');
    }
    await loadTree();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function renameFilePrompt(path) {
  const newPath = prompt('Enter new path:', path);
  if (!newPath || newPath === path) return;
  const author = prompt('Your name:', 'WebIDE') || 'WebIDE';
  try {
    await apiPost('/api/file/rename', { old_path: path, new_path: newPath, author });
    showToast(`Renamed ${path} to ${newPath}`, 'success');
    if (state.selectedFile === path) state.selectedFile = newPath;
    await loadTree();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

function updateCommitBtn() {
  const btn = document.getElementById('commit-btn');
  const msg = document.getElementById('commit-msg').value.trim();
  
  let hasChanges = false;
  if (state.monacoInstance && state.selectedFile) {
    hasChanges = state.monacoInstance.getValue() !== state.fileOriginalContent;
  }

  if (hasChanges && msg) {
    btn.classList.add('ready');
    btn.disabled = false;
  } else {
    btn.classList.remove('ready');
    btn.disabled = true;
  }
}

async function commitChanges() {
  if (!state.selectedFile || !state.monacoInstance) return;
  const btn = document.getElementById('commit-btn');
  const msgInput = document.getElementById('commit-msg');
  const message = msgInput.value.trim();
  const content = state.monacoInstance.getValue();
  const author = prompt('Enter your author name for this commit:', 'WebIDE') || 'WebIDE';

  if (!message) {
    showToast('Commit message required', 'error');
    return;
  }

  try {
    btn.disabled = true;
    btn.textContent = 'Committing...';
    
    const res = await apiPost('/api/commit', {
      path: state.selectedFile,
      content: content,
      message: message,
      author: author
    });
    
    showToast(res.message, 'success');
    state.fileOriginalContent = content; // Register as saved
    msgInput.value = '';
    updateCommitBtn();
    
    // Invalidate caches and reload tree/graph
    loadTree();
    loadGraph(true); // force reload
  } catch (e) {
    showToast(e.message || 'Failed to commit', 'error');
  } finally {
    btn.textContent = 'Commit Changes';
    updateCommitBtn();
  }
}


// ── Pull Requests ──────────────────────────────────────────────────
async function loadPRs() {
  showSkeleton('pr-list', 3);
  try {
    const statusF = document.getElementById('pr-status-filter')?.value || '';
    let url = '/api/prs';
    const params = [];
    if (statusF) params.push('status=' + statusF);
    if (params.length) url += '?' + params.join('&');
    state.prs = await api(url);
    renderPRs();
  } catch (e) { showEmpty('pr-list', '⑂', 'Failed to load pull requests'); }
}

function renderPRs() {
  const list = document.getElementById('pr-list');
  if (!state.prs.length) { showEmpty('pr-list', '⑂', 'No pull requests yet'); return; }

  list.innerHTML = state.prs.map(pr => {
    let statusClass, statusText;
    if (pr.status === 'merged') { statusClass = 'status-merged'; statusText = '✓ MERGED'; }
    else if (pr.status === 'closed') { statusClass = 'status-closed'; statusText = '✕ CLOSED'; }
    else if (pr.merge_ready) { statusClass = 'status-ready'; statusText = '✔ READY'; }
    else if (pr.changes_requested > 0) { statusClass = 'status-blocked'; statusText = '❌ BLOCKED'; }
    else { statusClass = 'status-pending'; statusText = '⏳ PENDING'; }

    const approvClass = pr.approvals >= pr.required ? 'ok' : 'warn';
    const threadClass = pr.unresolved_threads > 0 ? 'bad' : 'ok';
    const changesClass = pr.changes_requested > 0 ? 'bad' : 'ok';

    return `<div class="card" onclick="selectPR(${pr.id})">
      <div class="card-title">
        <span class="status-badge ${statusClass}">${statusText}</span>
        #${pr.id} ${escHtml(pr.title)}
      </div>
      <div class="card-meta">
        <span class="pr-flow">${escHtml(pr.head)} → ${escHtml(pr.base)}</span>
        <span>${escHtml(pr.author || '')}</span>
      </div>
      <div class="pr-stats">
        <span class="pr-stat ${approvClass}" title="Approvals">✔ ${pr.approvals}/${pr.required}</span>
        <span class="pr-stat ${changesClass}" title="Changes requested">⚠ ${pr.changes_requested}</span>
        <span class="pr-stat ${threadClass}" title="Unresolved threads">💬 ${pr.unresolved_threads}</span>
      </div>
    </div>`;
  }).join('');
}

async function selectPR(id) {
  state.selectedPR = id;
  openDetail();
  document.getElementById('detail-header').innerHTML = '<div class="skeleton" style="height:40px"></div>';
  document.getElementById('detail-body').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
  try {
    const pr = await api('/api/pr/' + id);
    renderPRDetail(pr);
    const url = new URL(window.location);
    url.searchParams.set('pr', id);
    history.replaceState(null, '', url);
  } catch (e) {
    document.getElementById('detail-body').innerHTML = `<div class="empty-state"><p>Failed to load PR #${id}</p></div>`;
    showToast('Failed to load PR details', 'error');
  }
}

function renderPRDetail(pr) {
  let statusClass, statusText;
  if (pr.status === 'merged') { statusClass = 'status-merged'; statusText = '✓ MERGED'; }
  else if (pr.status === 'closed') { statusClass = 'status-closed'; statusText = '✕ CLOSED'; }
  else if (pr.merge_ready) { statusClass = 'status-ready'; statusText = '✔ READY'; }
  else if (pr.changes_requested > 0) { statusClass = 'status-blocked'; statusText = '❌ BLOCKED'; }
  else { statusClass = 'status-pending'; statusText = '⏳ PENDING'; }

  document.getElementById('detail-header').innerHTML =
    `<h2><span class="status-badge ${statusClass}">${statusText}</span> #${pr.id} ${escHtml(pr.title)}</h2>
     <div class="detail-subtitle">${escHtml(pr.head)} → ${escHtml(pr.base)} · by ${escHtml(pr.author || '')}</div>`;

  let body = '';

  // Action buttons
  if (pr.status === 'open') {
    body += `<div class="action-bar">
      <button class="action-btn approve" onclick="prAction(${pr.id},'approve')" title="Approve this PR">✔ Approve</button>
      <button class="action-btn changes" onclick="prAction(${pr.id},'request_changes')" title="Request changes">⚠ Request Changes</button>
      <button class="action-btn merge${pr.merge_ready ? '' : '" disabled title="Not ready to merge'}" onclick="prAction(${pr.id},'merge')" title="${pr.merge_ready ? 'Merge this PR' : 'Not ready'}">⑂ Merge</button>
    </div>`;
  }

  // Stats
  body += `<div class="detail-section"><h4>Status</h4>
    <div class="pr-stats">
      <span class="pr-stat ${pr.approvals >= pr.required ? 'ok' : 'warn'}">✔ Approvals: ${pr.approvals}/${pr.required}</span>
      <span class="pr-stat ${pr.changes_requested > 0 ? 'bad' : 'ok'}">⚠ Changes: ${pr.changes_requested}</span>
      <span class="pr-stat ${pr.unresolved_threads > 0 ? 'bad' : 'ok'}">💬 Threads: ${pr.unresolved_threads}</span>
    </div></div>`;

  if (pr.body) body += `<div class="detail-section"><h4>Description</h4><pre>${escHtml(pr.body)}</pre></div>`;

  // Reviews
  const reviewEntries = Object.entries(pr.reviews || {});
  if (reviewEntries.length) {
    body += `<div class="detail-section"><h4>Reviews</h4>`;
    reviewEntries.forEach(([author, r]) => {
      body += `<div class="review-entry ${r.status}">
        <span class="review-author">${escHtml(author)}</span>
        <span class="status-badge status-${r.status === 'approved' ? 'open' : r.status === 'changes_requested' ? 'blocked' : 'pending'}">${r.status}</span>
        ${r.comment ? `<span style="color:var(--text-muted)">${escHtml(r.comment)}</span>` : ''}
      </div>`;
    });
    body += '</div>';
  }

  // Threads
  if (pr.threads && pr.threads.length) {
    body += `<div class="detail-section"><h4>Threads</h4>`;
    pr.threads.forEach(t => {
      body += `<div class="thread-entry${t.resolved ? ' resolved' : ''}">
        <div class="thread-header">${escHtml(t.author)} ${t.resolved ? '(resolved)' : ''}
          ${!t.resolved && pr.status === 'open' ? `<button class="action-btn resolve" style="padding:2px 8px;font-size:10px;margin-left:auto" onclick="resolveThread(${pr.id},${t.id})">Resolve</button>` : ''}
        </div>
        <div>${escHtml(t.text)}</div>`;
      (t.replies || []).forEach(r => {
        body += `<div class="thread-reply"><strong>${escHtml(r.author)}</strong>: ${escHtml(r.text)}</div>`;
      });
      body += '</div>';
    });
    body += '</div>';
  }

  // Commits
  if (pr.commits && pr.commits.length) {
    body += `<div class="detail-section"><h4>Commits (${pr.commits.length})</h4>
      <pre>${pr.commits.map(c => c.slice(0, 7)).join('\n')}</pre></div>`;
  }

  // Linked issue
  if (pr.linked_issue) {
    body += `<div class="detail-section"><h4>Linked Issue</h4>
      <div class="card" onclick="switchTab('issues');setTimeout(()=>selectIssue(${pr.linked_issue}),300)" style="cursor:pointer">
        <div class="card-title">#${pr.linked_issue}</div></div></div>`;
  }

  document.getElementById('detail-body').innerHTML = body;
}

async function prAction(prId, action) {
  const author = prompt('Enter your username:');
  if (!author) return;
  const body = { author };
  if (action === 'request_changes') {
    const comment = prompt('Comment (optional):') || '';
    body.comment = comment;
  }
  try {
    const result = await apiPost(`/api/pr/${prId}/${action}`, body);
    showToast(result.message || `${action} successful`, 'success');
    selectPR(prId);
    loadPRs();
  } catch (e) {
    showToast(e.message || `${action} failed`, 'error');
  }
}

async function resolveThread(prId, threadId) {
  try {
    const result = await apiPost(`/api/pr/${prId}/resolve_thread`, { thread_id: threadId });
    showToast(result.message || 'Thread resolved', 'success');
    selectPR(prId);
  } catch (e) {
    showToast(e.message || 'Failed to resolve thread', 'error');
  }
}

// ── Issues ─────────────────────────────────────────────────────────
async function loadIssues() {
  showSkeleton('issue-list', 3);
  try {
    const typeF = document.getElementById('issue-type-filter')?.value || '';
    const statusF = document.getElementById('issue-status-filter')?.value || '';
    let url = '/api/issues';
    const params = [];
    if (typeF) params.push('type=' + typeF);
    if (statusF) params.push('status=' + statusF);
    if (params.length) url += '?' + params.join('&');
    state.issues = await api(url);
    renderIssues();
  } catch (e) { showEmpty('issue-list', '◉', 'Failed to load issues'); }
}

function renderIssues() {
  const list = document.getElementById('issue-list');
  if (!state.issues.length) { showEmpty('issue-list', '◉', 'No issues yet'); return; }

  const typeIcons = { bug: '🐛', feature: '✨', task: '📋' };
  const typeClasses = { bug: 'type-bug', feature: 'type-feature', task: 'type-task' };

  list.innerHTML = state.issues.map(iss => {
    const statusClass = iss.status === 'open' ? 'status-open' : iss.status === 'closed' ? 'status-closed' : 'status-in-progress';
    return `<div class="card" onclick="selectIssue(${iss.id})">
      <div class="card-title">
        <span class="status-badge ${statusClass}">${iss.status}</span>
        <span class="status-badge ${typeClasses[iss.type] || ''}">${typeIcons[iss.type] || '●'} ${iss.type}</span>
        #${iss.id} ${escHtml(iss.title)}
      </div>
      <div class="card-meta">
        <span>${escHtml(iss.author || '')}</span>
        ${iss.labels.length ? iss.labels.map(l => `<span class="status-badge" style="background:var(--border);color:var(--text-muted)">${escHtml(l)}</span>`).join('') : ''}
      </div>
    </div>`;
  }).join('');
}

async function selectIssue(id) {
  state.selectedIssue = id;
  openDetail();
  document.getElementById('detail-header').innerHTML = '<div class="skeleton" style="height:40px"></div>';
  document.getElementById('detail-body').innerHTML = '<div class="skeleton"></div>';
  try {
    let iss = state.issues.find(i => i.id === id);
    if (!iss) {
      const all = await api('/api/issues');
      iss = all.find(i => i.id === id);
    }
    if (!iss) throw new Error('Issue not found');
    renderIssueDetail(iss);
    const url = new URL(window.location);
    url.searchParams.set('issue', id);
    history.replaceState(null, '', url);
  } catch (e) {
    document.getElementById('detail-body').innerHTML = `<div class="empty-state"><p>Failed to load issue #${id}</p></div>`;
  }
}

function renderIssueDetail(iss) {
  const typeIcons = { bug: '🐛', feature: '✨', task: '📋' };
  const statusClass = iss.status === 'open' ? 'status-open' : iss.status === 'closed' ? 'status-closed' : 'status-in-progress';

  document.getElementById('detail-header').innerHTML =
    `<h2><span class="status-badge ${statusClass}">${iss.status}</span> #${iss.id} ${escHtml(iss.title)}</h2>
     <div class="detail-subtitle">${typeIcons[iss.type] || ''} ${iss.type} · by ${escHtml(iss.author || '')}</div>`;

  let body = '';
  if (iss.description) body += `<div class="detail-section"><h4>Description</h4><pre>${escHtml(iss.description)}</pre></div>`;
  if (iss.assignee) body += `<div class="detail-section"><h4>Assignee</h4><p>${escHtml(iss.assignee)}</p></div>`;

  if (iss.linked_prs && iss.linked_prs.length) {
    body += `<div class="detail-section"><h4>Linked PRs</h4>`;
    iss.linked_prs.forEach(prId => {
      body += `<div class="card" onclick="switchTab('prs');setTimeout(()=>selectPR(${prId}),300)" style="cursor:pointer;margin-bottom:4px">
        <div class="card-title">PR #${prId}</div></div>`;
    });
    body += '</div>';
  }

  if (iss.timeline && iss.timeline.length) {
    body += `<div class="detail-section"><h4>Timeline</h4>`;
    iss.timeline.forEach(ev => {
      body += `<div class="activity-item" style="margin-bottom:4px">
        <div class="activity-icon ${ev.event?.includes('pr') ? 'pr' : 'review'}">●</div>
        <span>${escHtml(ev.event || '')} ${ev.author ? `by ${escHtml(ev.author)}` : ''}</span>
        <span class="activity-time">${ev.timestamp ? new Date(ev.timestamp).toLocaleString() : ''}</span>
      </div>`;
    });
    body += '</div>';
  }

  document.getElementById('detail-body').innerHTML = body;
}

// ── Work Dashboard ─────────────────────────────────────────────────
async function loadWork() {
  const dash = document.getElementById('work-dashboard');
  dash.innerHTML = '<div class="skeleton" style="height:100px"></div>';
  try {
    state.work = await api('/api/work');
    renderWork();
  } catch (e) { dash.innerHTML = '<div class="empty-state"><p>Failed to load work data</p></div>'; }
}

function renderWork() {
  const w = state.work;
  const dash = document.getElementById('work-dashboard');

  let html = `<div class="work-hero">
    <h2>You're working on:</h2>
    <div class="branch-name">${escHtml(w.current_branch || 'detached HEAD')}</div>
  </div>`;

  html += `<div class="work-stats">
    <div class="work-stat-card"><div class="stat-value">${w.open_prs || 0}</div><div class="stat-label">Open PRs</div></div>
    <div class="work-stat-card"><div class="stat-value">${w.open_issues || 0}</div><div class="stat-label">Open Issues</div></div>
  </div>`;

  if (w.active_pr) {
    const pr = w.active_pr;
    let statusClass = pr.merge_ready ? 'status-ready' : pr.changes_requested > 0 ? 'status-blocked' : 'status-pending';
    let statusText = pr.merge_ready ? '✔ READY' : pr.changes_requested > 0 ? '❌ BLOCKED' : '⏳ PENDING';
    html += `<div class="work-section"><h3>Active PR</h3>
      <div class="card" onclick="switchTab('prs');setTimeout(()=>selectPR(${pr.id}),300)">
        <div class="card-title"><span class="status-badge ${statusClass}">${statusText}</span> #${pr.id} ${escHtml(pr.title)}</div>
        <div class="card-meta"><span class="pr-flow">${escHtml(pr.head)} → ${escHtml(pr.base)}</span></div>
        <div class="pr-stats">
          <span class="pr-stat ${pr.approvals >= pr.required ? 'ok' : 'warn'}">✔ ${pr.approvals}/${pr.required}</span>
          <span class="pr-stat ${pr.changes_requested > 0 ? 'bad' : 'ok'}">⚠ ${pr.changes_requested}</span>
          <span class="pr-stat ${pr.unresolved_threads > 0 ? 'bad' : 'ok'}">💬 ${pr.unresolved_threads}</span>
        </div>
      </div></div>`;
  }

  if (w.related_issue) {
    const iss = w.related_issue;
    const typeIcons = { bug: '🐛', feature: '✨', task: '📋' };
    const statusClass = iss.status === 'open' ? 'status-open' : iss.status === 'closed' ? 'status-closed' : 'status-in-progress';
    html += `<div class="work-section"><h3>Related Issue</h3>
      <div class="card" onclick="switchTab('issues');setTimeout(()=>selectIssue(${iss.id}),300)">
        <div class="card-title"><span class="status-badge ${statusClass}">${iss.status}</span> ${typeIcons[iss.type] || ''} #${iss.id} ${escHtml(iss.title)}</div>
      </div></div>`;
  }

  dash.innerHTML = html;
}

// ── Activity Feed ──────────────────────────────────────────────────
async function loadActivity() {
  try {
    state.activity = await api('/api/activity');
    renderActivity();
  } catch (e) { /* silent */ }
}

function renderActivity() {
  const feed = document.getElementById('activity-feed');
  if (!state.activity.length) { showEmpty('activity-feed', '📋', 'No recent activity'); return; }

  const iconMap = {
    review_added: { cls: 'review', icon: '✔' },
    changes_requested: { cls: 'review', icon: '⚠' },
    merge_completed: { cls: 'merge', icon: '⑂' },
    thread_resolved: { cls: 'thread', icon: '💬' },
    pr_created: { cls: 'pr', icon: '+' },
  };

  feed.innerHTML = state.activity.map(a => {
    const def = iconMap[a.type] || { cls: 'review', icon: '●' };
    const timeAgo = formatTimeAgo(a.timestamp);
    return `<div class="activity-item">
      <div class="activity-icon ${def.cls}">${def.icon}</div>
      <span>${escHtml(a.message || a.type)}</span>
      <span class="activity-time">${timeAgo}</span>
    </div>`;
  }).join('');
}

// ── Detail Panel ───────────────────────────────────────────────────
function openDetail() { document.getElementById('detail-panel').classList.add('open'); }
function closeDetail() {
  document.getElementById('detail-panel').classList.remove('open');
  state.selectedPR = null;
  state.selectedIssue = null;
  state.selectedCommit = null;
}

// ── Counts ─────────────────────────────────────────────────────────
function updateCounts() {
  api('/api/health').then(h => {
    document.getElementById('pr-count').textContent = h.prs || 0;
    document.getElementById('issue-count').textContent = h.issues || 0;
    const badge = document.getElementById('health-status');
    badge.textContent = h.status === 'ok' ? '● OK' : '● DEGRADED';
    badge.style.color = h.status === 'ok' ? 'var(--green)' : 'var(--red)';
  }).catch(() => {});
}

// ── Keyboard Shortcuts ─────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (e.key === 'g') switchTab('graph');
  if (e.key === 'c') switchTab('code');
  if (e.key === 'p') switchTab('prs');
  if (e.key === 'i') switchTab('issues');
  if (e.key === 'w') switchTab('work');
  if (e.key === 'Escape') closeDetail();
});

// ── Auto-Refresh ───────────────────────────────────────────────────
setInterval(() => {
  // Do not auto-refresh Graph or Code editor aggressively to prevent jumping.
  if (state.activeTab === 'prs') {
    if (state.selectedPR) selectPR(state.selectedPR);
    else loadPRs();
  }
  if (state.activeTab === 'issues') loadIssues();
  if (state.activeTab === 'work') { loadWork(); loadActivity(); }
  updateCounts();
}, 3000);

// ── Utilities ──────────────────────────────────────────────────────
function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function formatTimeAgo(ts) {
  if (!ts) return '';
  const diff = (Date.now() / 1000) - ts;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

// ── Init ───────────────────────────────────────────────────────────
parseDeepLink();
if (!state.graphLoaded && state.activeTab === 'graph') loadGraph();
updateCounts();
