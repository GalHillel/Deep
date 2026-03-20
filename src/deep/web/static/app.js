/* Deep Platform — app.js (Entry Point) */

document.addEventListener('DOMContentLoaded', async () => {
    console.log("Deep Platform Initializing...");
    
    // 1. Initialize Reactive UI
    UI.init();
    
    // 2. Initial Data Load
    try {
        await Promise.all([
            UI.loadRefs(),
            UI.loadWork()
        ]);
    } catch (e) {
        console.error("Initialization failed:", e);
    }
    
    // 3. Setup Navigation
    document.querySelectorAll('.nav-item, .tab-btn').forEach(item => {
        item.addEventListener('click', () => {
            const tab = item.dataset.tab;
            if (tab) UI.switchTab(tab);
        });
    });

    // 4. Global Actions
    window.saveFile = async () => {
        const { selectedFile, monacoInstance, fileContent } = window.store.state;
        if (!selectedFile || !monacoInstance) return;
        
        const content = monacoInstance.getValue();
        try {
            await API.saveFile(selectedFile, content);
            window.store.set({ fileContent: content, isDirty: false });
            UI.showToast("File saved", "success");
        } catch (e) {}
    };

    window.commitChanges = async () => {
        const msgInput = document.getElementById('commit-msg');
        const message = msgInput.value || "IDE update";
        try {
            await API.commit(message);
            msgInput.value = '';
            window.store.set({ isDirty: false });
            UI.showToast("Changes committed", "success");
            UI.loadTree();
            UI.loadWork();
            UI.loadLog(); 
        } catch (e) {}
    };

    // 5. Keyboard Shortcuts
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            window.saveFile();
        }
    });

    // 6. Initial Render
    UI.switchTab(window.store.state.activeTab);
});
