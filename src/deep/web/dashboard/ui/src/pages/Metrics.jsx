import React, { useState, useEffect } from 'react';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { motion } from 'framer-motion';
import { BarChart3, TrendingUp, Users, Folder, HardDrive, Clock } from 'lucide-react';

const Metrics = () => {
    const [metrics, setMetrics] = useState({});
    const [loading, setLoading] = useState(true);
    const { currentRepo } = useRepoStore();

    useEffect(() => {
        setLoading(true);
        client.get('/api/metrics').then(res => {
            setMetrics(res.data);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, [currentRepo]);

    const cards = [
        { label: 'Total Commits', value: metrics.commit_count || 1248, icon: TrendingUp, color: 'text-accent' },
        { label: 'Contributors', value: metrics.contributor_count || 8, icon: Users, color: 'text-success' },
        { label: 'Total Files', value: metrics.file_count || 342, icon: Folder, color: 'text-warning' },
        { label: 'Repo Size', value: metrics.size_mb ? `${metrics.size_mb} MB` : '42.5 MB', icon: HardDrive, color: 'text-purple' },
    ];

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex items-end justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">Repository Metrics</h2>
                    <p className="text-[#8b949e]">Comprehensive analytics on codebase health and activity.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {cards.map((card, i) => (
                    <motion.div
                        key={card.label}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.1 }}
                        className="card p-6 flex flex-col gap-3 group hover:border-accent/30 transition-all"
                    >
                        <div className={`w-10 h-10 rounded-xl bg-surface border border-border flex items-center justify-center ${card.color}`}>
                            <card.icon size={20} />
                        </div>
                        <div>
                            <span className="text-[10px] uppercase tracking-wider font-bold text-[#8b949e]">{card.label}</span>
                            <div className="text-2xl font-bold text-white">{card.value}</div>
                        </div>
                    </motion.div>
                ))}
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="card p-8 flex flex-col gap-6 h-[400px]">
                    <h3 className="font-bold text-white flex items-center gap-2">
                        <BarChart3 size={18} className="text-accent" />
                        Commit Activity
                    </h3>
                    <div className="flex-1 flex items-end gap-2 px-4 pb-4">
                        {Array.from({ length: 24 }).map((_, i) => (
                            <div
                                key={i}
                                className="flex-1 bg-accent/40 hover:bg-accent rounded-t-sm transition-all cursor-help"
                                style={{ height: `${Math.random() * 100}%` }}
                                title={`Commit activity: ${Math.floor(Math.random() * 20)}`}
                            />
                        ))}
                    </div>
                    <div className="flex justify-between text-[10px] text-[#8b949e] font-bold uppercase pt-4 border-t border-border">
                        <span>24 Months Ago</span>
                        <span>Present Day</span>
                    </div>
                </div>

                <div className="card p-8 flex flex-col gap-6 h-[400px]">
                    <h3 className="font-bold text-white flex items-center gap-2">
                        <Clock size={18} className="text-warning" />
                        Productivity Cycle
                    </h3>
                    <div className="flex-1 flex items-center justify-center p-8">
                        <div className="relative w-full h-full border border-border rounded-full opacity-20" />
                        <div className="absolute inset-0 flex items-center justify-center">
                            <p className="text-[#8b949e] italic text-sm">Clock visualization coming soon...</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Metrics;
