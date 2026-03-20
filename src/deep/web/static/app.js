/* ⚓ Deep V3 — app.js (Stability Handoff) */

const App = {
    async boot() {
        console.log("⚓ Deep V3 Starting...");
        this.setupErrorBoundaries();
        
        try {
            await this.initMonaco();
            console.log("⚓ Monaco Loaded");
            
            await this.loadInitialData();
            console.log("⚓ Data Synchronized");
            
            this.setupListeners();
            this.renderUI();
            console.log("⚓ Deep V3 Ready.");
        } catch (e) {
            console.error("⚓ FATAL BOOT ERROR:", e);
            if (window.UI && window.UI.showToast) {
                window.UI.showToast(`Boot Failed: ${e.message}`, 'error');
            } else {
                alert("⚓ Deep Critical Error: " + e.message);
            }
        }
    },

    setupErrorBoundaries() {
        window.onerror = (msg, url, line, col, error) => {
            console.error(`[RuntimeError] ${msg} at ${url}:${line}`);
            return false;
        };
        window.onunhandledrejection = (event) => {
            console.error(`[AsyncError]`, event.reason);
        };
    },

    initMonaco() {
        return new Promise((resolve, reject) => {
            if (typeof require === 'undefined') {
                return reject(new Error("Monaco loader.js not found in index.html"));
            }
            
            require.config({
                paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.36.1/min/vs' }
            });

            require(['vs/editor/editor.main'], () => {
                // Pre-create editor if container exists
                const container = document.getElementById('monaco-container');
                if (container) {
                    window.editor = monaco.editor.create(container, {
                        value: "// ⚓ Deep IDE — Ready for code.\n",
                        language: "javascript",
                        theme: "vs-dark",
                        automaticLayout: true,
                        fontSize: 13,
                        minimap: { enabled: false }
                    });
                    
                    // Sync with window.store if available
                    if (window.store) {
                        window.store.set({ monacoInstance: window.editor });
                        window.editor.onDidChangeModelContent(() => {
                            window.store.set({ isDirty: window.editor.getValue() !== window.store.state.fileContent });
                        });
                    }
                }
                resolve();
            });
        });
    },

    async loadInitialData() {
        if (window.UI && window.UI.loadInitialData) {
            await window.UI.loadInitialData();
        }
    },

    setupListeners() {
        if (window.UI && window.UI.setupListeners) {
            window.UI.setupListeners();
        }
    },

    renderUI() {
        if (window.UI && window.UI.init) {
            window.UI.init();
        }
    }
};

window.App = App;

window.onload = () => {
    App.boot();
};
