import React, { useState, useEffect } from 'react';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, CheckCircle2, MessageSquare, Tag, Filter, Search, Plus } from 'lucide-react';

const Issues = () => {
    const [issues, setIssues] = useState([]);
    const [loading, setLoading] = useState(true);
    const { currentRepo } = useRepoStore();

    useEffect(() => {
        setLoading(true);
        client.get('/api/issues').then(res => {
            setIssues(Array.isArray(res.data) ? res.data : []);
            setLoading(false);
        }).catch(() => {
            setIssues([]);
            setLoading(false);
        });
    }, [currentRepo]);

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex items-end justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">Issues</h2>
                    <p className="text-[#8b949e]">Track bugs and feature requests for this project.</p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-success text-white text-sm font-medium shadow-lg shadow-success/20 hover:opacity-90 transition-all">
                    <Plus size={16} />
                    <span>New Issue</span>
                </button>
            </div>

            <div className="flex-1 card overflow-hidden flex flex-col">
                <div className="px-6 py-4 border-b border-border bg-surface/50 flex items-center justify-between">
                    <div className="flex items-center gap-6">
                        <div className="flex items-center gap-1.5 text-sm font-medium text-white cursor-pointer hover:text-accent transition-colors">
                            <AlertCircle size={16} className="text-[#8b949e]" />
                            <span>{issues.filter(i => i.status === 'open').length} Open</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-sm font-medium text-[#8b949e] cursor-pointer hover:text-[#c9d1d9] transition-colors">
                            <CheckCircle2 size={16} />
                            <span>{issues.filter(i => i.status === 'closed').length} Closed</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="text-[#8b949e] hover:text-[#c9d1d9] cursor-pointer text-sm">Sort <Filter size={14} className="inline ml-1" /></div>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                    {loading ? (
                        <div className="p-12 text-center text-[#8b949e]">
                            <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                            Loading issues...
                        </div>
                    ) : issues.length > 0 ? (
                        <div className="divide-y divide-border">
                            {issues.map((issue) => (
                                <motion.div
                                    key={issue.id}
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="px-6 py-4 flex gap-4 hover:bg-surface/30 group transition-colors cursor-pointer"
                                >
                                    <AlertCircle size={18} className="text-success mt-0.5" />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            <h4 className="text-sm font-bold text-white group-hover:text-accent transition-colors truncate">{issue.title}</h4>
                                            {issue.labels?.map(l => (
                                                <span key={l} className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-accent/10 text-accent border border-accent/20">{l}</span>
                                            ))}
                                        </div>
                                        <div className="flex items-center gap-3 text-xs text-[#8b949e]">
                                            <span>#{issue.id} opened {issue.created_at} by {issue.author}</span>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-1 text-[#8b949e]">
                                        <MessageSquare size={14} />
                                        <span className="text-xs">{issue.comments || 0}</span>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    ) : (
                        <div className="p-20 text-center space-y-4">
                            <div className="w-16 h-16 rounded-full bg-surface-subtle border border-border flex items-center justify-center mx-auto text-[#8b949e]">
                                <AlertCircle size={32} />
                            </div>
                            <div>
                                <h3 className="text-xl font-bold text-white">No issues found</h3>
                                <p className="text-[#8b949e] max-w-xs mx-auto">This repository doesn't have any open issues. Take a rest or start a new task.</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Issues;
