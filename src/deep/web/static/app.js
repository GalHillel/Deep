/* Deep Platform — app.js (Restored Dashboard Event Handling) */

document.addEventListener('DOMContentLoaded', async () => {
    console.log("Deep Platform Restored UI Initializing...");
    
    // 1. Initialize UI
    UI.init();
    
    // 2. Setup Navigation
    document.querySelectorAll('.nav-item, .tab-btn').forEach(item => {
        item.addEventListener('click', () => {
            const tab = item.dataset.tab;
            if (tab) UI.switchTab(tab);
        });
    });

    // 3. Global Actions
    window.saveFile = async () => {
        const { selectedFile, monacoInstance, fileContent } = window.store.state;
        if (!selectedFile || !monacoInstance) return;
        
        const content = monacoInstance.getValue();
        try {
            await API.saveFile(selectedFile, content);
            window.store.set({ fileContent: content, isDirty: false });
            UI.showToast("File saved", "success");
        } catch (e) {
            UI.showToast("Save failed", "error");
        }
    };

    window.commitChanges = async () => {
        const msgInput = document.getElementById('commit-msg');
        const message = msgInput.value.trim() || "Update from IDE";
        try {
            await API.commit(message);
            msgInput.value = '';
            UI.showToast("Changes committed", "success");
            UI.loadWork();
            UI.loadTree();
        } catch (e) {
            UI.showToast("Commit failed", "error");
        }
    };

    // 4. Keyboard Shortcuts
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            window.saveFile();
        }
    });

    // 5. Initial Render
    UI.switchTab(window.store.state.activeTab);
});
