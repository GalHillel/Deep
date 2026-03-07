import React, { useState, useEffect } from 'react';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { Folder, File, ChevronRight, ChevronDown, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const FileEntry = ({ entry, depth, onSelect, selectedPath }) => {
    const [isOpen, setIsOpen] = useState(false);
    const isFolder = entry.mode === '40000';
    const paddingLeft = depth * 16 + 12;

    return (
        <div>
            <div
                onClick={() => {
                    if (isFolder) setIsOpen(!isOpen);
                    else onSelect(entry);
                }}
                className={`flex items-center gap-2 py-1.5 px-3 cursor-pointer hover:bg-surface-subtle rounded-md transition-colors group ${selectedPath === entry.path ? 'bg-surface-subtle text-white' : 'text-[#8b949e]'}`}
                style={{ paddingLeft }}
            >
                <span className="text-[#30363d] group-hover:text-[#8b949e] transition-colors">
                    {isFolder ? (isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />) : <span className="w-[14px]" />}
                </span>
                {isFolder ? <Folder size={16} className="text-accent" /> : <File size={16} />}
                <span className="text-sm truncate">{entry.name}</span>
            </div>

            {isFolder && isOpen && entry.children && (
                <div>
                    {entry.children.map(child => (
                        <FileEntry
                            key={child.path}
                            entry={child}
                            depth={depth + 1}
                            onSelect={onSelect}
                            selectedPath={selectedPath}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

const FileExplorer = ({ onFileSelect }) => {
    const { currentRepo } = useRepoStore();
    const [tree, setTree] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedPath, setSelectedPath] = useState(null);

    useEffect(() => {
        setLoading(true);
        // Fetch objects and build tree for HEAD
        client.get('/api/refs').then(res => {
            const head = res.data.head;
            if (head) {
                client.get(`/api/object/${head}`).then(res => {
                    const treeSha = res.data.tree_sha;
                    fetchTree(treeSha).then(data => {
                        setTree(data);
                        setLoading(false);
                    });
                });
            }
        });
    }, [currentRepo]);

    const fetchTree = async (sha, path = '') => {
        const res = await client.get(`/api/object/${sha}`);
        const entries = res.data.entries || [];

        // Proactively fetch subtrees for small repositories or lazy load for large ones
        // For now, let's just return top level or recursive for small sets
        return entries.map(e => ({
            ...e,
            path: path ? `${path}/${e.name}` : e.name
        }));
    };

    return (
        <div className="flex flex-col h-full bg-surface border-r border-border w-80 shrink-0">
            <div className="p-4 border-b border-border">
                <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 text-[#8b949e]" size={14} />
                    <input
                        type="text"
                        placeholder="Filter files..."
                        className="w-full bg-background border border-border rounded-md pl-9 pr-3 py-1.5 text-xs focus:ring-1 focus:ring-accent focus:border-accent outline-none"
                    />
                </div>
            </div>

            <div className="flex-1 overflow-y-auto py-2 custom-scrollbar">
                {loading ? (
                    <div className="px-6 py-4 space-y-2">
                        {[1, 2, 3, 4, 5, 6].map(i => <div key={i} className="h-4 bg-surface-subtle animate-pulse rounded" />)}
                    </div>
                ) : (
                    tree.map(entry => (
                        <FileEntry
                            key={entry.path}
                            entry={entry}
                            depth={0}
                            onSelect={(e) => {
                                setSelectedPath(e.path);
                                onFileSelect(e);
                            }}
                            selectedPath={selectedPath}
                        />
                    ))
                )}
            </div>
        </div>
    );
};

export default FileExplorer;
