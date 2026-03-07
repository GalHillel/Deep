import Sidebar from './components/Sidebar'
import Topbar from './components/Topbar'
import CommandPalette from './components/CommandPalette'
import { useRepoStore } from './store/repoStore'
import { motion, AnimatePresence } from 'framer-motion'

// Page Imports
import Files from './pages/Files'
import CommitGraph from './components/CommitGraph'
import Issues from './pages/Issues'
import PullRequests from './pages/PullRequests'
import AIInsights from './pages/AIInsights'
import Network from './pages/Network'
import Dag3D from './pages/Dag3D'
import Metrics from './pages/Metrics'

// Placeholder Pages
const Dashboard = () => (
    <div className="space-y-6">
        <div className="flex items-end justify-between">
            <div>
                <h2 className="text-3xl font-bold text-white tracking-tight">Dashboard Overview</h2>
                <p className="text-[#8b949e]">Welcome back. Here's what's happening in your repositories.</p>
            </div>
            <div className="flex gap-3">
                <button className="px-4 py-2 rounded-lg bg-surface border border-border text-sm font-medium hover:bg-surface-subtle transition-colors">
                    Download Logs
                </button>
                <button className="px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium shadow-lg shadow-accent/20 hover:bg-accent-muted transition-colors">
                    Create New Repository
                </button>
            </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
                { label: 'Active Repos', value: '12', trend: '+2', color: 'accent' },
                { label: 'Open Issues', value: '43', trend: '-5', color: 'warning' },
                { label: 'Commits (24h)', value: '128', trend: '+14%', color: 'success' },
                { label: 'Network Nodes', value: '8', trend: 'Stable', color: 'purple' },
            ].map((stat) => (
                <div key={stat.label} className="card p-6 flex flex-col gap-2 hover:border-accent/30 transition-colors group">
                    <span className="text-[11px] uppercase tracking-wider font-bold text-[#8b949e]">{stat.label}</span>
                    <div className="flex items-end gap-2">
                        <span className="text-2xl font-bold text-white">{stat.value}</span>
                        <span className={`text-[10px] mb-1 font-medium text-${stat.color}`}>{stat.trend}</span>
                    </div>
                </div>
            ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 card p-6 min-h-[400px] flex items-center justify-center text-[#8b949e] italic">
                Activity Heatmap Visualization Coming Soon...
            </div>
            <div className="card p-6 flex flex-col gap-4">
                <h3 className="font-bold text-white">Recent Activity</h3>
                <div className="space-y-4">
                    {[1, 2, 3, 4, 5].map((i) => (
                        <div key={i} className="flex gap-3 items-start pb-4 border-b border-border last:border-0 last:pb-0">
                            <div className="w-8 h-8 rounded-full bg-surface-subtle border border-border shrink-0" />
                            <div className="text-sm">
                                <p className="text-[#c9d1d9]"><span className="font-bold text-white">galhillel</span> pushed to <span className="font-mono text-accent">main</span></p>
                                <p className="text-[#8b949e] text-xs">2 hours ago</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    </div>
);

function App() {
    const { activeView } = useRepoStore();

    const renderContent = () => {
        switch (activeView) {
            case 'dashboard': return <Dashboard />;
            case 'files': return <Files />;
            case 'commits': return <div className="h-full"><CommitGraph /></div>;
            case 'issues': return <Issues />;
            case 'prs': return <PullRequests />;
            case 'ai': return <AIInsights />;
            case 'network': return <Network />;
            case 'dag3d': return <Dag3D />;
            case 'metrics': return <Metrics />;
            default: return (
                <div className="h-full flex items-center justify-center text-[#8b949e]">
                    <div className="text-center space-y-2">
                        <h2 className="text-2xl font-bold text-white uppercase tracking-widest">{activeView}</h2>
                        <p>Phase Implementation in Progress...</p>
                    </div>
                </div>
            );
        }
    };

    return (
        <div className="flex h-screen bg-background overflow-hidden font-sans">
            <Sidebar />
            <div className="flex-1 flex flex-col min-w-0">
                <Topbar />
                <main className="flex-1 overflow-y-auto p-8 lg:p-12 custom-scrollbar">
                    <AnimatePresence mode="wait">
                        <motion.div
                            key={activeView}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            transition={{ duration: 0.2 }}
                            className="max-w-[1400px] mx-auto w-full h-full"
                        >
                            {renderContent()}
                        </motion.div>
                    </AnimatePresence>
                </main>
            </div>
            <CommandPalette />
        </div>
    );
}

export default App;
