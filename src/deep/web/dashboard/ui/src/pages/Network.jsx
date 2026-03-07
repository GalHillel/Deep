import React, { useState, useEffect, useRef } from 'react';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { motion } from 'framer-motion';
import { Network, Globe, Radio, Server, Activity } from 'lucide-react';

const P2PNetwork = () => {
    const [nodes, setNodes] = useState([]);
    const [presence, setPresence] = useState({});
    const [loading, setLoading] = useState(true);
    const containerRef = useRef();

    useEffect(() => {
        const fetchData = () => {
            Promise.all([
                client.get('/api/p2p/nodes'),
                client.get('/api/p2p/presence')
            ]).then(([nodesRes, presenceRes]) => {
                setNodes(nodesRes.data);
                setPresence(presenceRes.data);
                setLoading(false);
            }).catch(() => setLoading(false));
        };

        fetchData();
        const interval = setInterval(fetchData, 10000);
        return () => clearInterval(interval);
    }, []);

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex items-end justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">P2P Network</h2>
                    <p className="text-[#8b949e]">Real-time visualization of the distributed DeepGit node network.</p>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono text-[#8b949e]">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-success" />
                        <span>{nodes.length} Nodes Active</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <Radio size={14} className="text-accent" />
                        <span>Discovering Peers...</span>
                    </div>
                </div>
            </div>

            <div className="flex-1 card relative overflow-hidden bg-[#0a0d11]">
                {/* Animated Background Grid */}
                <div className="absolute inset-0 opacity-10 pointer-events-none"
                    style={{ backgroundImage: 'radial-gradient(#30363d 1px, transparent 1px)', backgroundSize: '24px 24px' }} />

                {loading ? (
                    <div className="absolute inset-0 flex items-center justify-center">
                        <div className="w-12 h-12 border-4 border-accent border-t-transparent rounded-full animate-spin" />
                    </div>
                ) : (
                    <div className="absolute inset-0 flex items-center justify-center p-12">
                        <div className="relative w-full h-full max-w-4xl max-h-[600px] flex items-center justify-center">
                            {/* Central Node */}
                            <motion.div
                                animate={{ scale: [1, 1.05, 1], rotate: [0, 5, -5, 0] }}
                                transition={{ repeat: Infinity, duration: 4 }}
                                className="w-24 h-24 rounded-3xl bg-gradient-to-br from-accent to-purple flex items-center justify-center shadow-2xl shadow-accent/40 z-10 border border-white/20"
                            >
                                <Server size={32} className="text-white" />
                            </motion.div>

                            {/* Peer Nodes */}
                            {nodes.map((node, i) => {
                                const angle = (i / nodes.length) * Math.PI * 2;
                                const radius = 250;
                                const x = Math.cos(angle) * radius;
                                const y = Math.sin(angle) * radius;

                                return (
                                    <React.Fragment key={node.node_id || i}>
                                        {/* Connection Line */}
                                        <motion.div
                                            initial={{ pathLength: 0, opacity: 0 }}
                                            animate={{ pathLength: 1, opacity: 0.2 }}
                                            className="absolute w-[2px] bg-gradient-to-r from-accent to-transparent origin-left"
                                            style={{
                                                left: '50%', top: '50%',
                                                width: radius,
                                                transform: `rotate(${angle}rad) translateX(12px)`,
                                            }}
                                        />

                                        {/* Node */}
                                        <motion.div
                                            initial={{ scale: 0, opacity: 0 }}
                                            animate={{ scale: 1, opacity: 1 }}
                                            transition={{ delay: i * 0.1 }}
                                            className="absolute group"
                                            style={{ left: `calc(50% + ${x}px - 24px)`, top: `calc(50% + ${y}px - 24px)` }}
                                        >
                                            <div className="w-12 h-12 rounded-xl glass flex items-center justify-center hover:border-accent/60 hover:scale-110 transition-all cursor-pointer relative">
                                                <Globe size={20} className="text-[#8b949e] group-hover:text-accent" />
                                                {/* Status Bit */}
                                                <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-success border-2 border-[#0a0d11]" />
                                            </div>
                                            <div className="absolute top-14 left-1/2 -translate-x-1/2 whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity">
                                                <div className="px-2 py-1 rounded bg-surface border border-border text-[10px] text-white font-mono shadow-xl">
                                                    {node.node_id?.slice(0, 12)}...
                                                </div>
                                            </div>
                                        </motion.div>
                                    </React.Fragment>
                                );
                            })}

                            {/* Pulsing Aura */}
                            <motion.div
                                animate={{ scale: [1, 3], opacity: [0.5, 0] }}
                                transition={{ repeat: Infinity, duration: 2 }}
                                className="absolute w-24 h-24 rounded-full border border-accent/30"
                            />
                        </div>
                    </div>
                )}

                <div className="absolute bottom-6 left-6 flex gap-6">
                    <div className="space-y-1">
                        <span className="text-[10px] text-[#8b949e] uppercase font-bold tracking-wider">Inbound Traffic</span>
                        <div className="flex items-center gap-2 text-white font-mono font-bold">
                            <Activity size={14} className="text-success" />
                            <span>12.4 MB/s</span>
                        </div>
                    </div>
                    <div className="space-y-1">
                        <span className="text-[10px] text-[#8b949e] uppercase font-bold tracking-wider">Outbound Traffic</span>
                        <div className="flex items-center gap-2 text-white font-mono font-bold">
                            <Activity size={14} className="text-accent" />
                            <span>4.8 MB/s</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default P2PNetwork;
