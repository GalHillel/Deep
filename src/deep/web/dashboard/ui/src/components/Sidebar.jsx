import React from 'react';
import {
    LayoutDashboard,
    GitCommitHorizontal,
    Files,
    GitPullRequest,
    AlertCircle,
    BarChart3,
    Cpu,
    Network,
    Box,
    Settings,
    ChevronRight
} from 'lucide-react';
import { useRepoStore } from '../store/repoStore';
import { motion } from 'framer-motion';

const NavItem = ({ icon: Icon, label, id, active, onClick }) => (
    <button
        onClick={() => onClick(id)}
        className={`nav-item w-full ${active ? 'active' : ''}`}
    >
        <Icon size={18} />
        <span className="flex-1 text-left">{label}</span>
        {active && (
            <motion.div
                layoutId="active-indicator"
                className="w-1.5 h-1.5 rounded-full bg-accent"
            />
        )}
    </button>
);

const Sidebar = () => {
    const { activeView, setActiveView, currentRepo } = useRepoStore();

    const navGroups = [
        {
            label: 'Repository',
            items: [
                { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
                { id: 'commits', label: 'Commits', icon: GitCommitHorizontal },
                { id: 'files', label: 'Files', icon: Files },
            ]
        },
        {
            label: 'Collaboration',
            items: [
                { id: 'issues', label: 'Issues', icon: AlertCircle },
                { id: 'prs', label: 'Pull Requests', icon: GitPullRequest },
            ]
        },
        {
            label: 'Insights',
            items: [
                { id: 'ai', label: 'AI Review', icon: Cpu },
                { id: 'metrics', label: 'Metrics', icon: BarChart3 },
            ]
        },
        {
            label: 'Network',
            items: [
                { id: 'network', label: 'Node Network', icon: Network },
                { id: 'dag3d', label: '3D Graph', icon: Box },
            ]
        }
    ];

    return (
        <aside className="w-64 glass h-screen flex flex-col border-r border-border shrink-0 z-20">
            <div className="p-6 border-bottom border-border flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-lg shadow-accent/20">
                    <GitCommitHorizontal className="text-white" size={20} />
                </div>
                <h1 className="text-lg font-bold tracking-tight text-white">
                    Deep<span className="text-accent">Git</span>
                </h1>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-6 space-y-8">
                {navGroups.map((group) => (
                    <div key={group.label} className="space-y-1">
                        <h3 className="px-3 text-[10px] uppercase tracking-[0.1em] font-semibold text-[#8b949e] mb-2">
                            {group.label}
                        </h3>
                        {group.items.map((item) => (
                            <NavItem
                                key={item.id}
                                {...item}
                                active={activeView === item.id}
                                onClick={setActiveView}
                            />
                        ))}
                    </div>
                ))}
            </div>

            <div className="p-4 border-t border-border">
                <button className="nav-item w-full">
                    <Settings size={18} />
                    <span>Settings</span>
                </button>
            </div>
        </aside>
    );
};

export default Sidebar;
