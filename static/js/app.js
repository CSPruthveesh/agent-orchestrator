/**
 * Master Observability Dashboard UI Controller
 * Binds REST API agent launcher, AutoReconnectingWebSocket stream subscriber,
 * DAGRenderer visualization, and Step Inspector panel.
 */
document.addEventListener('DOMContentLoaded', () => {
    class DashboardController {
        constructor() {
            this.activeWs = null;
            this.globalWs = null;
            this.currentAgentId = null;
            this.agentStreams = new Set();
            this.globalTokensAcc = 0;
            this.globalCostAcc = 0.0;
            this.eventCount = 0;
            this.lastStepId = null;
            this.activeToolStepId = null;

            this.initDOM();
            this.initDAG();
            this.bindEvents();
            this.connectGlobalStream();
        }

        initDOM() {
            this.form = document.getElementById('agent-launch-form');
            this.btnLaunch = document.getElementById('btn-launch-agent');
            this.btnCancel = document.getElementById('btn-cancel-agent');
            this.selectActiveAgent = document.getElementById('select-active-agent');

            this.statActiveAgents = document.getElementById('stat-active-agents');
            this.statTotalTokens = document.getElementById('stat-total-tokens');
            this.statTotalCost = document.getElementById('stat-total-cost');
            this.feedCount = document.getElementById('feed-count');
            this.traceFeedList = document.getElementById('trace-feed-list');

            this.inspectEmpty = document.getElementById('inspector-empty');
            this.inspectDetails = document.getElementById('inspector-details');
            this.inspectStepId = document.getElementById('inspect-step-id');
            this.inspectNodeType = document.getElementById('inspect-node-type');
            this.inspectTokens = document.getElementById('inspect-tokens');
            this.inspectCost = document.getElementById('inspect-cost');
            this.inspectDuration = document.getElementById('inspect-duration');
            this.inspectInput = document.getElementById('inspect-input');
            this.inspectOutput = document.getElementById('inspect-output');
        }

        initDAG() {
            this.dagRenderer = new window.DAGRenderer('dag-svg', {
                onNodeSelect: (nodeData) => this.populateInspector(nodeData)
            });
        }

        bindEvents() {
            if (this.form) {
                this.form.addEventListener('submit', (e) => this.handleLaunchAgent(e));
            }

            if (this.btnCancel) {
                this.btnCancel.addEventListener('click', () => this.handleCancelAgent());
            }

            if (this.selectActiveAgent) {
                this.selectActiveAgent.addEventListener('change', (e) => {
                    const agentId = e.target.value;
                    if (agentId) this.subscribeToAgentStream(agentId);
                });
            }
        }

        connectGlobalStream() {
            const wsUrl = `/ws/traces/global`;
            this.globalWs = new window.AutoReconnectingWebSocket(wsUrl);
            
            this.globalWs.on('WS_CONNECTED', (evt) => {
                this.appendLog('STARTED', 'Connected to global platform event stream.');
            });

            this.globalWs.on('BUDGET_UPDATE', (evt) => {
                const data = evt.data;
                if (data.turn_tokens) {
                    this.globalTokensAcc += data.turn_tokens;
                    this.statTotalTokens.textContent = this.globalTokensAcc.toLocaleString();
                }
                if (data.turn_cost_usd) {
                    this.globalCostAcc += data.turn_cost_usd;
                    this.statTotalCost.textContent = `$${this.globalCostAcc.toFixed(4)}`;
                }
            });

            this.globalWs.connect();
        }

        async handleLaunchAgent(e) {
            e.preventDefault();

            const goal = document.getElementById('input-goal').value;
            const model = document.getElementById('select-model').value;
            const budget = parseFloat(document.getElementById('input-budget').value) || 1.00;

            const availableTools = [];
            if (document.getElementById('tool-cpp-sandbox').checked) availableTools.push('cpp_sandbox');
            if (document.getElementById('tool-http-fetch').checked) availableTools.push('http_tool');

            const payload = {
                goal: goal,
                model: model,
                max_budget_usd: budget,
                available_tools: availableTools
            };

            this.appendLog('STARTED', `Submitting new agent task via REST API...`);

            try {
                const response = await fetch('/api/v1/agents/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    throw new Error(`API Error ${response.status}: ${await response.text()}`);
                }

                const data = await response.json();
                const agentId = data.agent_id;
                this.appendLog('STARTED', `Agent task created successfully! ID: ${agentId}`);

                this.agentStreams.add(agentId);
                this.updateActiveAgentDropdown(agentId);
                this.subscribeToAgentStream(agentId);

            } catch (err) {
                console.error('[Dashboard] Launch error:', err);
                this.appendLog('FAILED', `Failed to launch agent task: ${err.message}`);
            }
        }

        async handleCancelAgent() {
            if (!this.currentAgentId) return;

            this.appendLog('STARTED', `Attempting cancellation for agent '${this.currentAgentId}'...`);

            try {
                const response = await fetch(`/api/v1/agents/${this.currentAgentId}/cancel`, {
                    method: 'POST'
                });

                if (response.ok) {
                    const data = await response.json();
                    this.appendLog('FAILED', `Agent task cancelled successfully.`);
                    this.btnCancel.disabled = true;
                } else {
                    const errData = await response.json();
                    this.appendLog('FAILED', `Cancellation notice: ${errData.detail || 'Task is not actively running.'}`);
                }
            } catch (err) {
                console.error('[Dashboard] Cancellation error:', err);
                this.appendLog('FAILED', `Cancellation failed: ${err.message}`);
            }
        }

        subscribeToAgentStream(agentId) {
            if (this.activeWs) {
                this.activeWs.close();
            }

            this.currentAgentId = agentId;
            this.lastStepId = null;
            this.activeToolStepId = null;
            this.dagRenderer.clear();
            this.btnCancel.disabled = false;
            this.statActiveAgents.textContent = this.agentStreams.size;

            const wsUrl = `/ws/traces/${agentId}`;
            this.activeWs = new window.AutoReconnectingWebSocket(wsUrl);

            this.activeWs.on('WS_CONNECTED', (evt) => {
                this.appendLog('STARTED', evt.message);
            });

            this.activeWs.on('STEP_EXECUTION_STARTED', (evt) => {
                const data = evt.data;
                this.lastStepId = data.step_id;
                this.dagRenderer.addNode({
                    step_id: data.step_id,
                    label: data.node_type || 'Reasoning Step',
                    node_type: data.node_type,
                    status: 'RUNNING',
                    prompt_tokens: data.prompt_tokens
                });
                this.appendLog('STARTED', `Step started [${data.node_type}] -> Step ID: ${data.step_id}`);
            });

            this.activeWs.on('TOOL_CALL_DISPATCHED', (evt) => {
                const data = evt.data;
                this.activeToolStepId = `tool-${data.tool_name}-${Date.now()}`;
                this.dagRenderer.addNode({
                    step_id: this.activeToolStepId,
                    parent_step_id: this.lastStepId,
                    label: `Tool: ${data.tool_name}`,
                    node_type: 'TOOL_EXECUTION',
                    status: 'WAITING_FOR_TOOL',
                    input_payload: data.params
                });
                this.appendLog('TOOL', `Invoking tool '${data.tool_name}' with params: ${JSON.stringify(data.params)}`);
            });

            this.activeWs.on('TOOL_CALL_COMPLETED', (evt) => {
                const data = evt.data;
                if (this.activeToolStepId) {
                    this.dagRenderer.updateNodeStatus(this.activeToolStepId, 'COMPLETED', {
                        output: data.output
                    });
                }
                this.appendLog('COMPLETED', `Tool '${data.tool_name}' executed successfully.`);
            });

            this.activeWs.on('AGENT_STATE_CHANGE', (evt) => {
                const data = evt.data;
                this.appendLog('STARTED', `Agent state changed -> ${data.state}`);
            });

            this.activeWs.on('EXECUTION_TERMINATED', (evt) => {
                const data = evt.data;
                this.btnCancel.disabled = true;

                if (data.status === 'COMPLETED') {
                    this.dagRenderer.nodes.forEach(node => {
                        if (node.status === 'RUNNING' || node.status === 'WAITING_FOR_TOOL') {
                            node.status = 'COMPLETED';
                        }
                    });
                    this.dagRenderer.render();
                    this.appendLog('COMPLETED', `Agent task completed in ${data.duration_ms}ms! Trace ID: ${data.final_trace_id}`);
                } else if (data.status === 'SUSPENDED' || data.status === 'CANCELLED') {
                    this.dagRenderer.nodes.forEach(node => {
                        if (node.status === 'RUNNING' || node.status === 'WAITING_FOR_TOOL') {
                            node.status = 'FAILED';
                        }
                    });
                    this.dagRenderer.render();
                    this.appendLog('FAILED', `Agent task cancelled/suspended.`);
                } else {
                    this.dagRenderer.nodes.forEach(node => {
                        if (node.status === 'RUNNING' || node.status === 'WAITING_FOR_TOOL') {
                            node.status = data.status;
                        }
                    });
                    this.dagRenderer.render();
                    this.appendLog('FAILED', `Agent task terminated -> Status: ${data.status}`);
                }
            });

            this.activeWs.connect();
        }

        updateActiveAgentDropdown(selectedId) {
            this.selectActiveAgent.innerHTML = '<option value="">-- Select Active Agent Stream --</option>';
            this.agentStreams.forEach(id => {
                const opt = document.createElement('option');
                opt.value = id;
                opt.textContent = `Agent ${id.substring(0, 12)}...`;
                if (id === selectedId) opt.selected = true;
                this.selectActiveAgent.appendChild(opt);
            });
        }

        populateInspector(node) {
            if (!node) return;

            this.inspectEmpty.classList.add('hidden');
            this.inspectDetails.classList.remove('hidden');

            this.inspectStepId.textContent = node.id;
            this.inspectNodeType.textContent = node.nodeType;
            this.inspectTokens.textContent = `${node.promptTokens} / ${node.completionTokens}`;
            this.inspectCost.textContent = `$${(node.stepCostUsd || 0).toFixed(4)}`;
            this.inspectDuration.textContent = `${node.durationMs || 0} ms`;

            this.inspectInput.textContent = JSON.stringify(node.inputPayload || {}, null, 2);
            this.inspectOutput.textContent = JSON.stringify(node.outputPayload || {}, null, 2);
        }

        appendLog(type, message) {
            this.eventCount++;
            this.feedCount.textContent = `${this.eventCount} events`;

            const timeStr = new Date().toLocaleTimeString();
            const logEntry = document.createElement('div');
            logEntry.className = 'log-entry';
            logEntry.innerHTML = `
                <span class="log-time">[${timeStr}]</span>
                <span class="log-type ${type}">${type}</span>
                <span class="log-msg">${this.escapeHTML(message)}</span>
            `;

            this.traceFeedList.appendChild(logEntry);
            this.traceFeedList.scrollTop = this.traceFeedList.scrollHeight;
        }

        escapeHTML(str) {
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }
    }

    window.dashboardApp = new DashboardController();
});
