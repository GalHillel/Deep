import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import client from '../api/client';
import { motion } from 'framer-motion';
import { Box3, Layers, Box } from 'lucide-react';

const Dag3D = () => {
    const containerRef = useRef();
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!containerRef.current) return;

        // Scene Setup
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x0a0d11);

        const camera = new THREE.PerspectiveCamera(75, containerRef.current.clientWidth / containerRef.current.clientHeight, 0.1, 1000);
        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
        containerRef.current.appendChild(renderer.domElement);

        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;

        // Lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
        scene.add(ambientLight);
        const pointLight = new THREE.PointLight(0x58a6ff, 1);
        pointLight.position.set(10, 10, 10);
        scene.add(pointLight);

        // Fetch Data
        client.get('/api/dag-3d').then(res => {
            const nodes = res.data;
            const nodeMap = {};

            // Create Nodes
            const geometry = new THREE.BoxGeometry(2, 2, 2);
            nodes.forEach((node, i) => {
                const material = new THREE.MeshPhongMaterial({
                    color: node.sha === nodes[0].sha ? 0x58a6ff : 0x30363d,
                    emissive: node.sha === nodes[0].sha ? 0x1d2d3d : 0x000000
                });
                const cube = new THREE.Mesh(geometry, material);
                cube.position.set(node.x, node.y, node.z);
                scene.add(cube);
                nodeMap[node.sha] = cube;
            });

            // Create Edges (simplified for this demo)
            // In a real scenario we'd draw lines between parents and children

            camera.position.z = 100;
            setLoading(false);
        }).catch(() => setLoading(false));

        // Animation Loop
        const animate = () => {
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
        };
        animate();

        const handleResize = () => {
            camera.aspect = containerRef.current.clientWidth / containerRef.current.clientHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(containerRef.current.clientWidth, containerRef.current.clientHeight);
        };
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (containerRef.current) containerRef.current.removeChild(renderer.domElement);
        };
    }, []);

    return (
        <div className="h-full flex flex-col gap-6">
            <div className="flex items-end justify-between">
                <div>
                    <h2 className="text-3xl font-bold text-white tracking-tight">3D Commit DAG</h2>
                    <p className="text-[#8b949e]">Spatial visualization of repository history using Three.js.</p>
                </div>
            </div>

            <div className="flex-1 card relative overflow-hidden bg-[#0d1117] cursor-move">
                <div ref={containerRef} className="absolute inset-0" />
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-background/50 z-10">
                        <div className="w-12 h-12 border-4 border-accent border-t-transparent rounded-full animate-spin" />
                    </div>
                )}
                <div className="absolute bottom-6 right-6 p-4 glass border border-border rounded-xl space-y-2 text-[10px] text-[#8b949e] uppercase font-bold tracking-widest pointer-events-none">
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded bg-accent" />
                        <span>X: Time Sequence</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded bg-purple" />
                        <span>Y: Branch Index</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded bg-success" />
                        <span>Z: Dependency Depth</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Dag3D;
