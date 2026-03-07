import React, { useState, useEffect } from 'react';
import { DiffEditor } from '@monaco-editor/react';
import client from '../api/client';
import { motion } from 'framer-motion';
import { X, ChevronLeft, ChevronRight, FileCode } from 'lucide-react';

const DiffViewer = ({ commitSha, onSelectionChange }) => {
    const [files, setFiles] = useState([]);
    const [selectedFile, setSelectedFile] = useState(null);
    const [diffData, setDiffData] = useState({ original: '', modified: '' });
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!commitSha) return;
        client.get(`/api/diff/${commitSha}`).then(res => {
            setFiles(res.data);
            if (res.data.length > 0) setSelectedFile(res.data[0]);
        });
    }, [commitSha]);

    useEffect(() => {
        if (!selectedFile || !commitSha) return;
        setLoading(true);

        const fetchContent = async () => {
            try {
                const originalRes = selectedFile.old_sha
                    ? await client.get(`/api/object/${selectedFile.old_sha}`)
                    : { data: { content: '' } };
                const modifiedRes = selectedFile.new_sha
                    ? await client.get(`/api/object/${selectedFile.new_sha}`)
                    : { data: { content: '' } };

                setDiffData({
                    original: originalRes.data.content || '',
                    modified: modifiedRes.data.content || ''
                });
            } catch (err) {
                console.error("Error fetching diff content", err);
            } finally {
                setLoading(false);
            }
        };

        fetchContent();
    }, [selectedFile, commitSha]);

    return (
        <div className="flex flex-col h-full bg-background border border-border rounded-xl overflow-hidden shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 bg-surface/50 border-b border-border">
                <div className="flex items-center gap-4">
                    <h3 className="text-lg font-bold text-white">Changes in {commitSha?.slice(0, 7)}</h3>
                    <div className="flex items-center gap-2 border border-border rounded-lg bg-surface px-2 py-1">
                        <select
                            className="bg-transparent text-sm text-[#c9d1d9] focus:outline-none cursor-pointer"
                            value={selectedFile?.path || ''}
                            onChange={(e) => setSelectedFile(files.find(f => f.path === e.target.value))}
                        >
                            {files.map(f => (
                                <option key={f.path} value={f.path}>{f.status.toUpperCase()}: {f.path}</option>
                            ))}
                        </select>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-[#8b949e] mr-2">{files.length} files changed</span>
                </div>
            </div>

            <div className="flex-1 min-h-0 relative">
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 backdrop-blur-sm">
                        <div className="w-10 h-10 border-4 border-accent border-t-transparent rounded-full animate-spin" />
                    </div>
                )}
                <DiffEditor
                    height="100%"
                    original={diffData.original}
                    modified={diffData.modified}
                    language="javascript" // Should Ideally be dynamic based on file extension
                    theme="vs-dark"
                    options={{
                        readOnly: true,
                        renderSideBySide: true,
                        minimap: { enabled: false },
                        fontSize: 13,
                        fontFamily: "'JetBrains Mono', monospace",
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                        padding: { top: 16, bottom: 16 },
                        backgroundColor: '#0d1117'
                    }}
                    onMount={(editor, monaco) => {
                        monaco.editor.defineTheme('github-dark', {
                            base: 'vs-dark',
                            inherit: true,
                            rules: [],
                            colors: { 'editor.background': '#0d1117' }
                        });
                        monaco.editor.setTheme('github-dark');
                    }}
                />
            </div>
        </div>
    );
};

export default DiffViewer;
