import React, { useEffect } from 'react';
import { Search, Command, ChevronDown, Bell } from 'lucide-react';
import { useRepoStore } from '../store/repoStore';
import client, { setRepo } from '../api/client';

const Topbar = () => {
    const { currentRepo, setCurrentRepo, repos, setRepos } = useRepoStore();

    useEffect(() => {
        client.get('/repos').then(res => setRepos(res.data));
    }, [setRepos]);

    const handleRepoChange = (e) => {
        const repo = e.target.value;
        setCurrentRepo(repo);
        setRepo(repo);
    };

    return (
        <header className="h-16 glass border-b border-border flex items-center justify-between px-8 z-10">
            <div className="flex items-center gap-6 flex-1">
                <div className="relative flex items-center group max-w-xs w-full">
                    <Search className="absolute left-3 text-[#8b949e] group-focus-within:text-accent transition-colors" size={16} />
                    <input
                        type="text"
                        placeholder="Search or jump to..."
                        className="w-full bg-surface-subtle border border-border rounded-lg pl-10 pr-12 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-all"
                        onClick={() => { /* Toggle Search Palette */ }}
                    />
                    <div className="absolute right-3 flex items-center gap-1 px-1.5 py-0.5 rounded border border-border bg-surface text-[10px] text-[#8b949e] font-mono">
                        <Command size={10} />
                        <span>K</span>
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface border border-border hover:border-surface-hover transition-colors cursor-pointer">
                    <div className="w-5 h-5 rounded-md bg-purple/20 flex items-center justify-center">
                        <div className="w-2 h-2 rounded-full bg-purple" />
                    </div>
                    <select
                        value={currentRepo || ''}
                        onChange={handleRepoChange}
                        className="bg-transparent text-sm font-medium focus:outline-none cursor-pointer pr-2"
                    >
                        <option value="">Platform Root</option>
                        {repos.map(r => (
                            <option key={r.name} value={r.name}>{r.name}</option>
                        ))}
                    </select>
                </div>

                <button className="p-2 text-[#8b949e] hover:text-[#c9d1d9] hover:bg-surface-subtle rounded-lg transition-colors relative">
                    <Bell size={18} />
                    <span className="absolute top-2 right-2 w-2 h-2 bg-accent rounded-full border-2 border-background" />
                </button>

                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-accent/40 to-purple/40 border border-border flex items-center justify-center text-[10px] font-bold">
                    GH
                </div>
            </div>
        </header>
    );
};

export default Topbar;
