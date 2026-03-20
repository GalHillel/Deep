/* Deep V3 — api.js (Strict Core) */

const API = {
    async request(path, opts = {}) {
        const requestId = Math.random().toString(36).substring(7);
        console.time(`API:${requestId}:${path}`);
        
        try {
            const r = await fetch(path, {
                ...opts,
                headers: {
                    'Content-Type': 'application/json',
                    ...opts.headers
                }
            });

            if (!r.ok && r.status !== 422 && r.status !== 404) {
                throw new Error(`HTTP Error: ${r.status} ${r.statusText}`);
            }

            const json = await r.json();
            
            // Strictly enforce { success, data, error }
            if (typeof json !== 'object' || json === null) {
                throw new Error('Malformed API response: Not an object');
            }

            if (json.success === true) {
                console.timeEnd(`API:${requestId}:${path}`);
                return json.data;
            } else {
                const errorMsg = json.error || 'Unknown server error';
                console.error(`API Failure [${path}]:`, errorMsg);
                throw new Error(errorMsg);
            }
        } catch (e) {
            console.timeEnd(`API:${requestId}:${path}`);
            console.error(`Network/API Crash [${path}]:`, e);
            
            // Bridge to Global Error Boundary / Toast
            if (window.App && window.App.handleError) {
                window.App.handleError(e, `API:${path}`);
            } else if (window.UI && window.UI.showToast) {
                window.UI.showToast(e.message, 'error');
            }
            
            throw e;
        }
    },

    async get(path) {
        return this.request(path, { method: 'GET' });
    },

    async post(path, body = {}) {
        return this.request(path, {
            method: 'POST',
            body: JSON.stringify({
                ...body,
                author: localStorage.getItem('deep_username') || 'WebIDE'
            }),
        });
    },

    // --- Optimized Endpoint Wrappers ---
    async health() { return this.get('/api/health'); },
    async getTree() { return this.get('/api/tree'); },
    async getFile(path) { return this.get(`/api/file?path=${encodeURIComponent(path)}`); },
    async saveFile(path, content) { return this.post('/api/file/save', { path, content }); },
    async deleteFile(path) { return this.post('/api/file/delete', { path }); },
    async getWork() { return this.get('/api/work'); },
    async getRefs() { return this.get('/api/refs'); },
    async getLog() { return this.get('/api/log'); },
    async commit(message) { return this.post('/api/commit', { message }); },
    async checkout(name) { return this.post('/api/branch/checkout', { name }); },
    async getIssues(type = '', status = '') {
        return this.get(`/api/issues?type=${type}&status=${status}`);
    },
    async getPRs(status = '') {
        return this.get(`/api/prs${status ? '?status=' + status : ''}`);
    }
};

window.API = API;
