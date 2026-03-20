/* Deep Platform — app.js (3-Pane Resinizable Edition) */

document.addEventListener('DOMContentLoaded', async () => {
    console.log("Deep Platform Mega UI Initializing...");
    
    // 1. Initialize UI
    UI.init();
    
    // 2. Setup Global Keydown
    document.addEventListener('keydown', (e) => {
        // Ctrl+S: Save
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            window.saveFile();
        }
        // Ctrl+Enter: Commit
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            if (document.activeElement.id === 'commit-msg-input') {
                window.commitChanges();
            }
        }
        // Ctrl+E: Explorer
        if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
            e.preventDefault();
            const explorerBtn = document.querySelector('[data-tool="explorer"]');
            if (explorerBtn) explorerBtn.click();
        }
    });

    // 3. Global Action Handlers
    window.saveFile = async () => {
        const { selectedFile, monacoInstance, fileContent } = window.store.state;
        if (!selectedFile || !monacoInstance) return;
        
        const content = monacoInstance.getValue();
        try {
            await API.saveFile(selectedFile, content);
            window.store.set({ fileContent: content, isDirty: false });
            UI.showToast("File saved successfully", "success");
        } catch (e) {
            UI.showToast("Failed to save file", "error");
        }
    };

    window.commitChanges = async () => {
        const msgInput = document.getElementById('commit-msg-input');
        const message = msgInput.value.trim();
        if (!message) {
            UI.showToast("Please enter a commit message", "error");
            return;
        }

        try {
            await API.commit(message);
            msgInput.value = '';
            UI.showToast("Changes committed!", "success");
            UI.loadWork();
            UI.loadTree();
        } catch (e) {
            UI.showToast("Commit failed", "error");
        }
    };

    // 4. Initial Tool Selection
    const defaultTool = document.querySelector('[data-tool="explorer"]');
    if (defaultTool) defaultTool.click();
});
