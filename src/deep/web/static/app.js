/* Deep Platform — app.js (Entry Point) */

document.addEventListener('DOMContentLoaded', async () => {
    console.log("Deep Platform Initializing...");
    
    // 1. Initial Data Load
    try {
        await Promise.all([
            API.loadRefs(),
            API.loadWork()
        ]);
        UI.renderBranches();
    } catch (e) {
        console.error("Initialization failed:", e);
    }
    
    // 2. Setup Navigation
    document.querySelectorAll('.nav-item, .tab-btn').forEach(item => {
        item.addEventListener('click', () => {
            const tab = item.dataset.tab;
            if (tab) UI.switchTab(tab);
        });
    });

    // 3. Global Actions
    window.saveFile = async () => {
        if (!state.selectedFile || !state.monacoInstance) return;
        const content = state.monacoInstance.getValue();
        try {
            await API.saveFile(state.selectedFile, content);
            state.fileContent = content;
            state.isDirty = false;
            UI.updateCommitPanel();
            UI.showToast("File saved", "success");
        } catch (e) {}
    };

    window.commitChanges = async () => {
        const msgInput = document.getElementById('commit-msg');
        const message = msgInput.value || "IDE update";
        try {
            await API.commit(message);
            msgInput.value = '';
            state.isDirty = false;
            UI.updateCommitPanel();
            UI.showToast("Changes committed", "success");
            UI.loadTree(); // Refresh tree
        } catch (e) {}
    };

    // 4. Keyboard Shortcuts
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            window.saveFile();
        }
    });

    // 5. Initial Render
    UI.switchTab(state.activeTab);
});
