import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Command, File, GitCommit, Layout, Settings, AlertCircle, Sparkles } from 'lucide-react';
import { useRepoStore } from '../store/repoStore';

const CommandPalette = () => {
    const [isOpen, setIsOpen] = useState(false);
    const [query, setQuery] = useState('');
    const { setActiveView } = useRepoStore();

    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'k' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                setIsOpen(prev => !prev);
            }
            if (e.key === 'Escape') setIsOpen(false);
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

    const commands = [
        { id: 'dashboard', label: 'Go to Dashboard', icon: Layout, category: 'Navigation' },
        { id: 'commits', label: 'View Commits', icon: GitCommit, category: 'Navigation' },
        { id: 'files', label: 'Browse Files', icon: File, category: 'Navigation' },
        { id: 'ai', label: 'AI Review', icon: Sparkles, category: 'AI' },
        { id: 'issues', label: 'Issues', icon: AlertCircle, category: 'Collaboration' },
        { id: 'settings', label: 'Settings', icon: Settings, category: 'System' },
    ];

    const filteredCommands = commands.filter(cmd =>
        cmd.label.toLowerCase().includes(query.toLowerCase())
    );

    const handleSelect = (id) => {
        setActiveView(id);
        setIsOpen(false);
        setQuery('');
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={() => setIsOpen(false)}
                        className="fixed inset-0 bg-background/60 backdrop-blur-sm z-[100]"
                    />
                    <div className="fixed inset-0 flex items-start justify-center pt-[15vh] z-[101] pointer-events-none">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: -20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: -20 }}
                            className="w-full max-w-xl glass border border-border shadow-2xl rounded-2xl overflow-hidden pointer-events-auto"
                        >
                            <div className="flex items-center gap-3 px-4 py-4 border-b border-border bg-surface/50">
                                <Search className="text-[#8b949e]" size={20} />
                                <input
                                    autoFocus
                                    value={query}
                                    onChange={(e) => setQuery(e.target.value)}
                                    placeholder="Type a command or search..."
                                    className="flex-1 bg-transparent text-white text-lg focus:outline-none"
                                />
                                <div className="px-1.5 py-0.5 rounded border border-border bg-surface text-[10px] text-[#8b949e] font-mono">
                                    ESC
                                </div>
                            </div>

                            <div className="max-h-[60vh] overflow-y-auto p-2 custom-scrollbar">
                                {filteredCommands.length > 0 ? (
                                    <div className="space-y-4 py-2">
                                        {['Navigation', 'AI', 'Collaboration', 'System'].map(category => {
                                            const catCmds = filteredCommands.filter(c => c.category === category);
                                            if (catCmds.length === 0) return null;
                                            return (
                                                <div key={category}>
                                                    <h3 className="px-3 text-[10px] uppercase tracking-wider font-bold text-[#8b949e] mb-2">{category}</h3>
                                                    {catCmds.map(cmd => (
                                                        <button
                                                            key={cmd.id}
                                                            onClick={() => handleSelect(cmd.id)}
                                                            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-surface-subtle text-[#c9d1d9] hover:text-white transition-all group"
                                                        >
                                                            <div className="w-8 h-8 rounded-lg bg-surface border border-border flex items-center justify-center group-hover:border-accent/40 group-hover:bg-accent/10 transition-colors">
                                                                <cmd.icon size={18} className="group-hover:text-accent transition-colors" />
                                                            </div>
                                                            <span className="text-sm font-medium">{cmd.label}</span>
                                                            <ChevronRight size={14} className="ml-auto text-[#30363d] group-hover:text-[#8b949e]" />
                                                        </button>
                                                    ))}
                                                </div>
                                            )
                                        })}
                                    </div>
                                ) : (
                                    <div className="p-12 text-center">
                                        <p className="text-[#8b949e]">No results found for "{query}"</p>
                                    </div>
                                )}
                            </div>

                            <div className="px-4 py-3 border-t border-border bg-surface/30 flex items-center justify-between text-[11px] text-[#8b949e]">
                                <div className="flex gap-4">
                                    <span className="flex items-center gap-1"><Command size={10} /> <ChevronRight size={10} /> Move</span>
                                    <span className="flex items-center gap-1"><Command size={10} /> Enter Select</span>
                                </div>
                                <span>DeepGit AI Ready</span>
                            </div>
                        </motion.div>
                    </div>
                </>
            )}
        </AnimatePresence>
    );
};

export default CommandPalette;
