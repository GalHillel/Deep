import React, { useState, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { motion } from 'framer-motion';
import { Download, Copy, History, Share2, Maximize2 } from 'lucide-react';

const CodeViewer = ({ path, sha, isDiff = false }) => {
    const [content, setContent] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!sha) return;
        setLoading(true);
        client.get(`/api/object/${sha}`).then(res => {
            setContent(res.data.content || '');
            setLoading(false);
        });
    }, [sha]);

    const getLanguage = (filename) => {
        const ext = filename?.split('.').pop();
        const map = {
            'js': 'javascript',
            'jsx': 'javascript',
            'ts': 'typescript',
            'tsx': 'typescript',
            'py': 'python',
            'md': 'markdown',
            'html': 'html',
            'css': 'css',
            'json': 'json',
        };
        return map[ext] || 'text';
    };

    return (
        <div className="flex flex-col h-full card">
            <div className="px-6 py-3 border-b border-border flex items-center justify-between bg-surface/50">
                <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-white">{path || 'Select a file'}</span>
                    {sha && <span className="text-[10px] font-mono text-[#8b949e] px-1.5 py-0.5 rounded bg-surface-subtle">{sha.slice(0, 7)}</span>}
                </div>
                <div className="flex items-center gap-2">
                    <button className="p-1.5 hover:bg-surface-subtle rounded transition-colors text-[#8b949e] hover:text-[#c9d1d9] tooltip" title="Copy Content">
                        <Copy size={16} />
                    </button>
                    <button className="p-1.5 hover:bg-surface-subtle rounded transition-colors text-[#8b949e] hover:text-[#c9d1d9]">
                        <Download size={16} />
                    </button>
                    <div className="w-[1px] h-4 bg-border mx-1" />
                    <button className="p-1.5 hover:bg-surface-subtle rounded transition-colors text-[#8b949e] hover:text-[#c9d1d9]">
                        <History size={16} />
                    </button>
                </div>
            </div>

            <div className="flex-1 min-h-0 relative">
                {loading && sha && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10 backdrop-blur-sm">
                        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                    </div>
                )}
                <Editor
                    height="100%"
                    language={getLanguage(path)}
                    theme="vs-dark"
                    value={content}
                    options={{
                        readOnly: true,
                        minimap: { enabled: true },
                        fontSize: 13,
                        fontFamily: "'JetBrains Mono', monospace",
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                        padding: { top: 16, bottom: 16 },
                        backgroundColor: '#0d1117'
                    }}
                    beforeMount={(monaco) => {
                        monaco.editor.defineTheme('github-dark', {
                            base: 'vs-dark',
                            inherit: true,
                            rules: [],
                            colors: {
                                'editor.background': '#0d1117',
                            }
                        });
                    }}
                    onMount={(editor, monaco) => {
                        monaco.editor.setTheme('github-dark');
                    }}
                />
            </div>
        </div>
    );
};

export default CodeViewer;
