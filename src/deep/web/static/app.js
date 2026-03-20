/* Deep V3 — app.js (Strict Lifecycle & Error Boundary) */

const App = {
    async boot() {
        console.log("⚓ Deep V3 Booting...");
        this.setupErrorBoundaries();
        
        try {
            await this.loadConfig();
            await this.initEditor();
            await this.loadState();
            this.setupEventListeners();
            this.renderUI();
            console.log("⚓ Deep V3 Ready.");
        } catch (e) {
            this.handleError(e, "BootSequence");
        }
    },

    setupErrorBoundaries() {
        window.onerror = (msg, url, line, col, error) => {
            this.handleError(error || msg, "RuntimeError");
            return false;
        };
        window.onunhandledrejection = (event) => {
            this.handleError(event.reason, "AsyncPromiseRejection");
        };
    },

    async loadConfig() {
        // Future proofing for local config/theme
        this.config = {
            theme: 'vs-dark',
            refreshInterval: 10000
        };
    },

    async initEditor() {
        // Monaco is loaded via AMD in index.html, no pre-init needed for now
    },

    async loadState() {
        if (window.UI && window.UI.loadInitialData) {
            await window.UI.loadInitialData();
        }
    },

    setupEventListeners() {
        // Delegate to UI for consistency
        if (window.UI && window.UI.setupListeners) {
            window.UI.setupListeners();
        }
    },

    renderUI() {
        if (window.UI && window.UI.init) {
            window.UI.init();
        }
    },

    handleError(error, context = "General") {
        console.error(`[${context}]`, error);
        const msg = typeof error === 'string' ? error : (error.message || "Unknown error occurred");
        
        if (window.UI && window.UI.showToast) {
            window.UI.showToast(`Error: ${msg}`, 'error');
        } else {
            alert(`⚓ Deep Critical Error: ${msg}`);
        }
    }
};

window.App = App;

document.addEventListener('DOMContentLoaded', () => {
    App.boot();
});
