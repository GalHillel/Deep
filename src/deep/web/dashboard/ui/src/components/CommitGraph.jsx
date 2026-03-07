import React, { useEffect, useRef, useState } from 'react';
import * as d3 from 'd3';
import { useRepoStore } from '../store/repoStore';
import client from '../api/client';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Filter, Maximize2, Minimize2 } from 'lucide-react';

const CommitGraph = () => {
    const svgRef = useRef();
    const containerRef = useRef();
    const { currentRepo, selectedCommit, setSelectedCommit } = useRepoStore();
    const [commits, setCommits] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        client.get('/api/log').then(res => {
            setCommits(res.data);
            setLoading(false);
        });
    }, [currentRepo]);

    useEffect(() => {
        if (!svgRef.current || commits.length === 0) return;

        const svg = d3.select(svgRef.current);
        svg.selectAll('*').remove();

        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;
        const margin = { top: 40, right: 40, bottom: 40, left: 100 };

        const g = svg.append('g');

        // Zoom behavior
        const zoom = d3.zoom()
            .scaleExtent([0.1, 4])
            .on('zoom', (event) => g.attr('transform', event.transform));

        svg.call(zoom);

        // X scale depends on commit index (time)
        // Y scale depends on "branching" depth (simplified for now)
        const xScale = d3.scaleLinear()
            .domain([0, commits.length])
            .range([margin.left, commits.length * 150]);

        // Create links (edges)
        const links = [];
        commits.forEach((d, i) => {
            d.parents?.forEach(pSha => {
                const parent = commits.find(c => c.sha === pSha);
                if (parent) {
                    links.push({ source: d, target: parent });
                }
            });
        });

        // Draw links
        g.selectAll('.link')
            .data(links)
            .enter()
            .append('path')
            .attr('class', 'link')
            .attr('d', d => {
                const x1 = xScale(commits.indexOf(d.source));
                const y1 = 100; // Simplified y
                const x2 = xScale(commits.indexOf(d.target));
                const y2 = 100;
                return `M${x1},${y1} L${x2},${y2}`;
            })
            .attr('stroke', '#30363d')
            .attr('stroke-width', 2)
            .attr('fill', 'none');

        // Draw nodes
        const nodes = g.selectAll('.node')
            .data(commits)
            .enter()
            .append('g')
            .attr('class', 'node')
            .attr('transform', (d, i) => `translate(${xScale(i)}, 100)`)
            .style('cursor', 'pointer')
            .on('click', (event, d) => setSelectedCommit(d.sha));

        nodes.append('circle')
            .attr('r', 6)
            .attr('fill', d => d.sha === selectedCommit ? '#58a6ff' : '#161b22')
            .attr('stroke', d => d.sha === selectedCommit ? '#fff' : '#58a6ff')
            .attr('stroke-width', 2);

        nodes.append('text')
            .attr('dy', 25)
            .attr('text-anchor', 'middle')
            .attr('fill', '#8b949e')
            .style('font-size', '10px')
            .text(d => d.sha.slice(0, 7));

        nodes.append('text')
            .attr('dy', -15)
            .attr('text-anchor', 'middle')
            .attr('fill', '#c9d1d9')
            .style('font-size', '12px')
            .text(d => d.message.split('\n')[0].slice(0, 20) + (d.message.length > 20 ? '...' : ''));

    }, [commits, selectedCommit, setSelectedCommit]);

    return (
        <div className="flex flex-col h-full gap-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <h2 className="text-xl font-bold text-white">Commit Graph</h2>
                    <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-xs text-[#8b949e]">
                        <Filter size={12} />
                        <span>All Branches</span>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button className="p-2 hover:bg-surface rounded-lg transition-colors text-[#8b949e]">
                        <Maximize2 size={18} />
                    </button>
                </div>
            </div>

            <div ref={containerRef} className="flex-1 card bg-background/50 relative overflow-hidden">
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/80 z-10">
                        <motion.div
                            animate={{ rotate: 360 }}
                            transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                            className="w-10 h-10 border-4 border-accent border-t-transparent rounded-full"
                        />
                    </div>
                )}
                <svg ref={svgRef} className="w-full h-full" />
            </div>
        </div>
    );
};

export default CommitGraph;
