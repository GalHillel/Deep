import React, { useState } from 'react';
import FileExplorer from '../components/FileExplorer';
import CodeViewer from '../components/CodeViewer';

const Files = () => {
    const [selectedFile, setSelectedFile] = useState(null);

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex flex-col gap-1">
                <h2 className="text-3xl font-bold text-white tracking-tight">Repository Files</h2>
                <p className="text-[#8b949e]">Browse and inspect the source code of the repository.</p>
            </div>

            <div className="flex-1 min-h-0 flex gap-0 rounded-xl border border-border overflow-hidden bg-background">
                <FileExplorer onFileSelect={setSelectedFile} />
                <div className="flex-1 min-w-0">
                    <CodeViewer path={selectedFile?.path} sha={selectedFile?.sha} />
                </div>
            </div>
        </div>
    );
};

export default Files;
