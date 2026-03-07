import React, { useState, useEffect } from 'react';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { motion } from 'framer-motion';
import { Cpu, Sparkles, AlertTriangle, Zap, BarChart3, ShieldCheck } from 'lucide-react';

const AIInsights = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const { currentRepo } = useRepoStore();

    useEffect(() => {
        setLoading(true);
        client.get('/api/ai/review').then(res => {
            setData(res.data);
            setLoading(false);
        }).catch(() => {
            setLoading(false);
        });
    }, [currentRepo]);

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex items-end justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">AI Insights</h2>
                    <p className="text-[#8b949e]">DeepGit AI analyzes your code for quality, security, and complexity.</p>
                </div>
                <button className="flex items-center gap-2 px-4 py-2 rounded-lg bg-surface border border-border text-sm font-medium hover:bg-surface-subtle transition-colors group">
                    <Zap size={16} className="group-hover:text-warning transition-colors" />
                    <span>Rerun Analysis</span>
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <div className="card p-8 bg-gradient-to-br from-surface to-[#1a1f26] border-accent/20 relative overflow-hidden">
                        <div className="absolute top-0 right-0 p-8 opacity-10">
                            <Sparkles size={120} className="text-accent" />
                        </div>
                        <div className="relative z-10 space-y-6">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center text-accent">
                                    <Cpu size={24} />
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-white">Latest Code Review</h3>
                                    <p className="text-sm text-[#8b949e]">Analysis based on the last 50 commits</p>
                                </div>
                            </div>

                            {loading ? (
                                <div className="space-y-4 animate-pulse">
                                    <div className="h-4 bg-surface-subtle rounded w-3/4" />
                                    <div className="h-4 bg-surface-subtle rounded w-5/6" />
                                    <div className="h-4 bg-surface-subtle rounded w-2/3" />
                                </div>
                            ) : data ? (
                                <div className="space-y-4">
                                    <div className="text-[#c9d1d9] leading-relaxed prose prose-invert max-w-none">
                                        {data.text || "No AI feedback available yet."}
                                    </div>
                                    <div className="grid grid-cols-2 gap-4 mt-6">
                                        <div className="p-4 rounded-xl bg-background/50 border border-border">
                                            <span className="text-[10px] uppercase tracking-wider font-bold text-[#8b949e]">AI Confidence</span>
                                            <div className="flex items-end gap-2 mt-1">
                                                <span className="text-2xl font-bold text-white">{data.confidence || 0}%</span>
                                            </div>
                                        </div>
                                        <div className="p-4 rounded-xl bg-background/50 border border-border">
                                            <span className="text-[10px] uppercase tracking-wider font-bold text-[#8b949e]">Processing Latency</span>
                                            <div className="flex items-end gap-2 mt-1">
                                                <span className="text-2xl font-bold text-white">{data.latency_ms || 0}ms</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="text-[#8b949e] italic">No AI data returned from backend.</div>
                            )}
                        </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <div className="card p-6 space-y-4">
                            <div className="flex items-center gap-2 text-warning">
                                <AlertTriangle size={18} />
                                <h4 className="font-bold">Risk Distribution</h4>
                            </div>
                            <div className="space-y-3">
                                {[
                                    { label: 'High Priority', val: 12, color: 'bg-error' },
                                    { label: 'Medium Priority', val: 28, color: 'bg-warning' },
                                    { label: 'Low Priority', val: 60, color: 'bg-success' },
                                ].map(i => (
                                    <div key={i.label} className="space-y-1">
                                        <div className="flex justify-between text-xs">
                                            <span className="text-[#8b949e]">{i.label}</span>
                                            <span className="text-white">{i.val}%</span>
                                        </div>
                                        <div className="h-1.5 w-full bg-surface-subtle rounded-full overflow-hidden">
                                            <div className={`${i.color} h-full`} style={{ width: `${i.val}%` }} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="card p-6 space-y-4">
                            <div className="flex items-center gap-2 text-accent">
                                <ShieldCheck size={18} />
                                <h4 className="font-bold">Security Score</h4>
                            </div>
                            <div className="flex items-center justify-center py-4">
                                <div className="relative w-24 h-24 flex items-center justify-center">
                                    <svg className="w-full h-full -rotate-90">
                                        <circle cx="48" cy="48" r="40" fill="transparent" stroke="#30363d" strokeWidth="8" />
                                        <circle cx="48" cy="48" r="40" fill="transparent" stroke="#58a6ff" strokeWidth="8" strokeDasharray="251.2" strokeDashoffset="50.24" />
                                    </svg>
                                    <span className="absolute text-xl font-bold text-white">80</span>
                                </div>
                            </div>
                            <p className="text-center text-xs text-[#8b949e]">8/10 Vulnerabilities Mitigated</p>
                        </div>
                    </div>
                </div>

                <div className="space-y-6">
                    <div className="card p-6 space-y-4">
                        <h4 className="font-bold text-white">Complexity Heatmap</h4>
                        <div className="grid grid-cols-10 gap-1 opacity-80">
                            {Array.from({ length: 50 }).map((_, i) => (
                                <div
                                    key={i}
                                    className={`aspect-square rounded-sm border border-black/20 ${i % 7 === 0 ? 'bg-error/80' :
                                            i % 5 === 0 ? 'bg-warning/80' :
                                                'bg-success/80'
                                        }`}
                                />
                            ))}
                        </div>
                        <div className="flex justify-between text-[10px] text-[#8b949e] uppercase tracking-wider font-bold pt-2 border-t border-border">
                            <span>Less Complex</span>
                            <span>Highly Complex</span>
                        </div>
                    </div>

                    <div className="card p-6 space-y-4">
                        <h4 className="font-bold text-white">AI Suggestions</h4>
                        <div className="space-y-4">
                            {[
                                "Refactor redundant tree traversal in storage.py",
                                "Add type hints to network/client.py",
                                "Optimize memory usage during large blob reads"
                            ].map((s, i) => (
                                <div key={i} className="flex gap-3 text-sm">
                                    <div className="w-5 h-5 rounded bg-accent/10 border border-accent/20 flex items-center justify-center text-accent shrink-0">
                                        {i + 1}
                                    </div>
                                    <p className="text-[#c9d1d9] leading-snug">{s}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AIInsights;
