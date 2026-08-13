/**
 * Interactive SVG Directed Acyclic Graph (DAG) Renderer
 * Dynamically computes hierarchical tree layouts, renders animated connecting paths,
 * and handles node selection callbacks for the Inspector Panel.
 */
class DAGRenderer {
    constructor(svgId, options = {}) {
        this.svg = document.getElementById(svgId);
        this.onNodeSelect = options.onNodeSelect || (() => {});
        
        this.nodes = new Map(); // step_id -> NodeData
        this.edges = [];        // { source: step_id, target: step_id }
        
        this.selectedNodeId = null;
        this.nodeWidth = 180;
        this.nodeHeight = 54;
        this.levelSpacingY = 90;
        this.nodeSpacingX = 220;

        this.initSVG();
    }

    initSVG() {
        if (!this.svg) return;
        this.svg.innerHTML = `
            <defs>
                <marker id="arrowhead" viewBox="0 0 10 10" refX="8" refY="5"
                    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
                </marker>
                <filter id="glow-running" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
            </defs>
            <g id="dag-edges-layer"></g>
            <g id="dag-nodes-layer"></g>
        `;
    }

    clear() {
        this.nodes.clear();
        this.edges = [];
        this.selectedNodeId = null;
        const edgesLayer = document.getElementById('dag-edges-layer');
        const nodesLayer = document.getElementById('dag-nodes-layer');
        if (edgesLayer) edgesLayer.innerHTML = '';
        if (nodesLayer) nodesLayer.innerHTML = '';
        
        const placeholder = document.getElementById('dag-empty-placeholder');
        if (placeholder) placeholder.style.display = 'block';
    }

    addNode(nodeData) {
        const placeholder = document.getElementById('dag-empty-placeholder');
        if (placeholder) placeholder.style.display = 'none';

        const stepId = nodeData.step_id || nodeData.id;
        if (this.nodes.has(stepId)) {
            // Update existing
            const existing = this.nodes.get(stepId);
            Object.assign(existing, nodeData);
        } else {
            this.nodes.set(stepId, {
                id: stepId,
                label: nodeData.label || nodeData.node_type || 'Execution Step',
                nodeType: nodeData.node_type || 'SUPERVISOR_PROMPT',
                status: nodeData.status || 'RUNNING',
                parentStepId: nodeData.parent_step_id || null,
                promptTokens: nodeData.prompt_tokens || 0,
                completionTokens: nodeData.completion_tokens || 0,
                stepCostUsd: nodeData.step_cost_usd || 0.0,
                durationMs: nodeData.duration_ms || 0,
                inputPayload: nodeData.input_payload || {},
                outputPayload: nodeData.output_payload || {},
                x: 0,
                y: 0,
                depth: 0
            });

            if (nodeData.parent_step_id && this.nodes.has(nodeData.parent_step_id)) {
                this.addEdge(nodeData.parent_step_id, stepId);
            }
        }

        this.layoutAndRender();
    }

    addEdge(sourceId, targetId) {
        const exists = this.edges.some(e => e.source === sourceId && e.target === targetId);
        if (!exists) {
            this.edges.push({ source: sourceId, target: targetId });
        }
    }

    updateNodeStatus(stepId, status, payload = {}) {
        const node = this.nodes.get(stepId);
        if (node) {
            node.status = status;
            if (payload.output) node.outputPayload = payload.output;
            if (payload.duration_ms) node.durationMs = payload.duration_ms;
            if (payload.step_cost_usd) node.stepCostUsd = payload.step_cost_usd;
            this.render();
        }
    }

    calculateTopologicalLayout() {
        if (this.nodes.size === 0) return;

        // Group nodes by depth
        const levels = new Map(); // depth -> Node[]
        
        this.nodes.forEach(node => {
            let depth = 0;
            let curr = node;
            while (curr && curr.parentStepId && this.nodes.has(curr.parentStepId)) {
                depth++;
                curr = this.nodes.get(curr.parentStepId);
            }
            node.depth = depth;

            if (!levels.has(depth)) {
                levels.set(depth, []);
            }
            levels.get(depth).push(node);
        });

        // Compute SVG center layout coordinates
        const svgWidth = this.svg.clientWidth || 800;
        const startY = 60;

        levels.forEach((nodeList, depth) => {
            const levelY = startY + depth * this.levelSpacingY;
            const totalWidth = (nodeList.length - 1) * this.nodeSpacingX;
            const startX = Math.max(80, (svgWidth - totalWidth) / 2);

            nodeList.forEach((node, index) => {
                node.x = startX + index * this.nodeSpacingX;
                node.y = levelY;
            });
        });
    }

    layoutAndRender() {
        this.calculateTopologicalLayout();
        this.render();
    }

    render() {
        const edgesLayer = document.getElementById('dag-edges-layer');
        const nodesLayer = document.getElementById('dag-nodes-layer');
        if (!edgesLayer || !nodesLayer) return;

        // Render Edges
        let edgesHTML = '';
        this.edges.forEach(edge => {
            const src = this.nodes.get(edge.source);
            const tgt = this.nodes.get(edge.target);
            if (src && tgt) {
                const x1 = src.x;
                const y1 = src.y + this.nodeHeight / 2;
                const x2 = tgt.x;
                const y2 = tgt.y - this.nodeHeight / 2;

                // Bezier curve connector
                const pathD = `M ${x1} ${y1} C ${x1} ${y1 + 40}, ${x2} ${y2 - 40}, ${x2} ${y2}`;
                edgesHTML += `<path d="${pathD}" stroke="#475569" stroke-width="2" fill="none" marker-end="url(#arrowhead)" />`;
            }
        });
        edgesLayer.innerHTML = edgesHTML;

        // Render Nodes
        let nodesHTML = '';
        this.nodes.forEach(node => {
            const isSelected = this.selectedNodeId === node.id;
            const nodeClass = this.getNodeStatusClass(node.status);
            const badgeColor = this.getNodeTypeColor(node.nodeType);

            const rectX = node.x - this.nodeWidth / 2;
            const rectY = node.y - this.nodeHeight / 2;

            nodesHTML += `
                <g class="dag-node-group ${isSelected ? 'selected' : ''}" data-id="${node.id}" transform="translate(${rectX}, ${rectY})" style="cursor: pointer;">
                    <rect width="${this.nodeWidth}" height="${this.nodeHeight}" rx="8" ry="8"
                        fill="#1e293b" stroke="${isSelected ? '#3b82f6' : nodeClass.stroke}" stroke-width="${isSelected ? '3' : '1.5'}" />
                    
                    <circle cx="16" cy="18" r="6" fill="${badgeColor}" />
                    
                    <text x="30" y="22" fill="#f8fafc" font-size="11" font-weight="600" font-family="Inter">${this.truncateText(node.label, 18)}</text>
                    <text x="30" y="38" fill="#94a3b8" font-size="10" font-family="Fira Code">${node.status}</text>
                </g>
            `;
        });
        nodesLayer.innerHTML = nodesHTML;

        // Attach click listeners to rendered nodes
        nodesLayer.querySelectorAll('.dag-node-group').forEach(group => {
            group.addEventListener('click', (e) => {
                const nodeId = group.getAttribute('data-id');
                this.selectedNodeId = nodeId;
                const nodeData = this.nodes.get(nodeId);
                this.onNodeSelect(nodeData);
                this.render(); // Redraw selection outline
            });
        });
    }

    getNodeStatusClass(status) {
        switch (status) {
            case 'COMPLETED': return { stroke: '#10b981' };
            case 'WAITING_FOR_TOOL': return { stroke: '#f59e0b' };
            case 'FAILED': return { stroke: '#ef4444' };
            case 'BUDGET_EXCEEDED': return { stroke: '#ef4444' };
            default: return { stroke: '#3b82f6' };
        }
    }

    getNodeTypeColor(nodeType) {
        if (nodeType.includes('SUPERVISOR')) return '#8b5cf6'; // Purple
        if (nodeType.includes('TOOL')) return '#f59e0b';       // Amber
        if (nodeType.includes('WORKER')) return '#06b6d4';     // Cyan
        return '#3b82f6';                                      // Blue
    }

    truncateText(str, maxLen) {
        if (!str) return '';
        return str.length > maxLen ? str.substring(0, maxLen - 3) + '...' : str;
    }
}

// Make globally available
window.DAGRenderer = DAGRenderer;
