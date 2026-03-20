/* Deep Platform — api.js */

const API = {
  async request(path, opts = {}) {
    try {
      const r = await fetch(path, opts);
      const json = await r.json();
      if (!json.success) throw new Error(json.error || 'Unknown error');
      return json.data;
    } catch (e) {
      console.error(`API Error [${path}]:`, e);
      if (window.showToast) window.showToast(e.message, 'error');
      throw e;
    }
  },

  async get(path) {
    return this.request(path);
  },

  async post(path, body = {}) {
    return this.request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...body,
        author: localStorage.getItem('deep_username') || 'WebIDE'
      }),
    });
  },

  // Specific Actions
  async loadTree() { return this.get('/api/tree'); },
  async loadFile(path) { return this.get(`/api/file?path=${encodeURIComponent(path)}`); },
  async saveFile(path, content) { return this.post('/api/file/save', { path, content }); },
  async addFile(path) { return this.post('/api/file/add', { path }); },
  async commit(message) { return this.post('/api/commit', { message }); },
  
  async loadPRs(status = '') { return this.get(`/api/prs${status ? '?status=' + status : ''}`); },
  async loadPR(id) { return this.get(`/api/pr/${id}`); },
  async prAction(id, action, extra = {}) { return this.post(`/api/pr/${id}/${action}`, extra); },
  
  async loadIssues(type = '', status = '') {
    let url = '/api/issues?';
    if (type) url += `type=${type}&`;
    if (status) url += `status=${status}`;
    return this.get(url);
  },
  async createIssue(title, description, type) { return this.post('/api/issues', { title, description, type }); },
  async closeIssue(id) { return this.post(`/api/issues/${id}/close`); },
  
  async loadWork() { return this.get('/api/work'); },
  async loadRefs() { return this.get('/api/refs'); },
  async loadLog() { return this.get('/api/log'); },
  
  async createBranch(name) { return this.post('/api/branch/create', { name }); },
  async checkoutBranch(name) { return this.post('/api/branch/checkout', { name }); }
};

window.API = API;
