/**
 * Resilient Auto-Reconnecting WebSocket Client with Exponential Backoff and Event Emitter.
 */
class AutoReconnectingWebSocket {
    constructor(url, options = {}) {
        this.url = url;
        this.reconnectIntervalMs = options.reconnectIntervalMs || 1000;
        this.maxReconnectIntervalMs = options.maxReconnectIntervalMs || 16000;
        this.reconnectDecay = options.reconnectDecay || 2.0;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        this.heartbeatIntervalMs = options.heartbeatIntervalMs || 15000;

        this.ws = null;
        this.reconnectAttempts = 0;
        this.isClosedExplicitly = false;
        this.listeners = {};
        this.heartbeatTimer = null;
    }

    connect() {
        if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
            return;
        }

        this.isClosedExplicitly = false;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const fullUrl = this.url.startsWith('ws') ? this.url : `${protocol}//${host}${this.url}`;

        try {
            this.ws = new WebSocket(fullUrl);
            this.updateBadgeStatus('connecting');

            this.ws.onopen = () => {
                this.reconnectAttempts = 0;
                this.updateBadgeStatus('connected');
                this.startHeartbeat();
                this.emit('open');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'PONG') return;
                    
                    // Dispatch by event_type or generic message
                    if (data.event_type) {
                        this.emit(data.event_type, data);
                    }
                    this.emit('message', data);
                } catch (err) {
                    console.error('[WebSocket] Error parsing message payload:', err);
                }
            };

            this.ws.onerror = (error) => {
                console.warn('[WebSocket] Socket error observed:', error);
                this.emit('error', error);
            };

            this.ws.onclose = (event) => {
                this.stopHeartbeat();
                this.updateBadgeStatus('disconnected');
                this.emit('close', event);

                if (!this.isClosedExplicitly) {
                    this.scheduleReconnect();
                }
            };
        } catch (err) {
            console.error('[WebSocket] Connection setup failed:', err);
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WebSocket] Max reconnect attempts reached. Halting reconnects.');
            return;
        }

        this.reconnectAttempts++;
        const timeout = Math.min(
            this.reconnectIntervalMs * Math.pow(this.reconnectDecay, this.reconnectAttempts - 1),
            this.maxReconnectIntervalMs
        );

        console.log(`[WebSocket] Reconnecting in ${timeout}ms (Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        setTimeout(() => {
            if (!this.isClosedExplicitly) {
                this.connect();
            }
        }, timeout);
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            const payload = typeof data === 'string' ? data : JSON.stringify(data);
            this.ws.send(payload);
            return true;
        }
        console.warn('[WebSocket] Cannot send message, socket is not OPEN.');
        return false;
    }

    startHeartbeat() {
        this.stopHeartbeat();
        this.heartbeatTimer = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.send({ type: 'PING' });
            }
        }, this.heartbeatIntervalMs);
    }

    stopHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    close() {
        this.isClosedExplicitly = true;
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close();
        }
    }

    on(eventType, callback) {
        if (!this.listeners[eventType]) {
            this.listeners[eventType] = [];
        }
        this.listeners[eventType].push(callback);
    }

    off(eventType, callback) {
        if (!this.listeners[eventType]) return;
        this.listeners[eventType] = this.listeners[eventType].filter(cb => cb !== callback);
    }

    emit(eventType, data) {
        if (this.listeners[eventType]) {
            this.listeners[eventType].forEach(cb => {
                try {
                    cb(data);
                } catch (err) {
                    console.error(`[WebSocket] Listener callback error for '${eventType}':`, err);
                }
            });
        }
    }

    updateBadgeStatus(status) {
        const badge = document.getElementById('ws-connection-badge');
        const statusText = document.getElementById('ws-status-text');
        if (!badge || !statusText) return;

        badge.className = 'connection-status';
        if (status === 'connected') {
            badge.classList.add('connected');
            statusText.textContent = 'Live Connected';
        } else if (status === 'connecting') {
            badge.classList.add('disconnected');
            statusText.textContent = 'Connecting...';
        } else {
            badge.classList.add('disconnected');
            statusText.textContent = 'Disconnected';
        }
    }
}

// Make globally available
window.AutoReconnectingWebSocket = AutoReconnectingWebSocket;
