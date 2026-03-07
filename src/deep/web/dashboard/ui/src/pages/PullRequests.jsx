import React, { useState, useEffect } from 'react';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { motion } from 'framer-motion';
import { GitPullRequest, CheckCircle2, MessageSquare, GitBranch, GitMerge, FileText } from 'lucide-react';

const PullRequests = () => {
    const [prs, setPrs] = useState([]);
    const [loading, setLoading] = useState(true);
    const { currentRepo } = useRepoStore();

    useEffect(() => {
        setLoading(true);
        client.get('/api/prs').then(res => {
            setPrs(Array.isArray(res.data) ? res.data : []);
            setLoading(false);
        }).catch(() => {
            setPrs([]);
            setLoading(false);
        });
    }, [currentRepo]);

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex items-end justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">Pull Requests</h2>
                    <p className="text-[#8b949e]">Review and merge changes from other branches.</p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium shadow-lg shadow-accent/20 hover:opacity-90 transition-all">
                    <GitPullRequest size={16} />
                    <span>New Pull Request</span>
                </button>
            </div>

            <div className="flex-1 card overflow-hidden flex flex-col">
                <div className="px-6 py-4 border-b border-border bg-surface/50 flex items-center justify-between">
                    <div className="flex items-center gap-6">
                        <div className="flex items-center gap-1.5 text-sm font-medium text-white cursor-pointer hover:text-accent transition-colors">
                            <GitPullRequest size={16} className="text-[#8b949e]" />
                            <span>{prs.filter(p => p.status === 'open').length} Open</span>
                        </div>
                        <div className="flex items-center gap-1.5 text-sm font-medium text-[#8b949e] cursor-pointer hover:text-[#c9d1d9] transition-colors">
                            <CheckCircle2 size={16} />
                            <span>{prs.filter(p => p.status === 'merged').length} Merged</span>
                        </div>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto">
                    {loading ? (
                        <div className="p-12 text-center text-[#8b949e]">
                            <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                            Loading pull requests...
                        </div>
                    ) : prs.length > 0 ? (
                        <div className="divide-y divide-border">
                            {prs.map((pr) => (
                                <motion.div
                                    key={pr.id}
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="px-6 py-4 flex gap-4 hover:bg-surface/30 group transition-colors cursor-pointer"
                                >
                                    <GitPullRequest size={18} className="text-success mt-0.5" />
                                    <div className="flex-1 min-w-0">
                                        <h4 className="text-sm font-bold text-white group-hover:text-accent transition-colors truncate mb-1">{pr.title}</h4>
                                        <div className="flex items-center gap-3 text-xs text-[#8b949e]">
                                            <span>#{pr.id} opened {pr.created_at} by {pr.author}</span>
                                            <div className="flex items-center gap-1 bg-surface-subtle px-1.5 py-0.5 rounded border border-border">
                                                <GitBranch size={10} />
                                                <span>{pr.source_branch}</span>
                                                <ChevronRight size={10} />
                                                <span>{pr.target_branch}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4 text-[#8b949e]">
                                        <div className="flex items-center gap-1">
                                            <MessageSquare size={14} />
                                            <span className="text-xs">{pr.comments || 0}</span>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <FileText size={14} />
                                            <span className="text-xs">{pr.files_changed || 0}</span>
                                        </div>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    ) : (
                        <div className="p-20 text-center space-y-4">
                            <div className="w-16 h-16 rounded-full bg-surface-subtle border border-border flex items-center justify-center mx-auto text-[#8b949e]">
                                <GitPullRequest size={32} />
                            </div>
                            <div>
                                <h3 className="text-xl font-bold text-white">No pull requests found</h3>
                                <p className="text-[#8b949e] max-w-xs mx-auto">There are no open pull requests in this repository. Push some changes to start one.</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default PullRequests;
