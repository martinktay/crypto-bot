/** Advanced Signal Bot Dashboard - Hybrid RL+GA & UI Logic */

const signalList = document.getElementById('signal-list');
const statusPulse = document.getElementById('status-pulse');

function getMeta(name) {
    const el = document.querySelector(`meta[name="${name}"]`);
    return el ? el.getAttribute('content') : null;
}

const API_AUTH_ENABLED = (getMeta('api-auth-enabled') || 'false') === 'true';
const API_AUTH_HEADER = getMeta('api-auth-header') || 'X-API-Key';
const WS_AUTH_ENABLED = (getMeta('ws-auth-enabled') || 'false') === 'true';

function getApiKey() {
    return localStorage.getItem('API_AUTH_TOKEN') || '';
}

function getWsToken() {
    return localStorage.getItem('WS_AUTH_TOKEN') || '';
}

function ensureApiKeyIfRequired() {
    if (!API_AUTH_ENABLED) return;
    const key = getApiKey();
    if (key) return;
    const entered = window.prompt('Enter API key to use this dashboard (stored in browser localStorage as API_AUTH_TOKEN).');
    if (entered && entered.trim()) {
        localStorage.setItem('API_AUTH_TOKEN', entered.trim());
    }
}

function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (API_AUTH_ENABLED) {
        const key = getApiKey();
        if (key) headers.set(API_AUTH_HEADER, key);
    }
    return fetch(url, { ...options, headers });
}

// Optimization Elements
const optProgressContainer = document.getElementById('opt-progress-container');
const optProgressFill = document.getElementById('opt-progress-fill');
const optStatusText = document.getElementById('opt-status-text');
const optBtn = document.getElementById('btn-run-optimization');
const optResults = document.getElementById('opt-results');
const optBestParams = document.getElementById('opt-best-params');

// WebSocket Setup
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsBaseUrl = `${wsProtocol}//${window.location.host}/ws/dashboard`;

let socket;

function connectWebSocket() {
    let wsUrl = wsBaseUrl;
    if (WS_AUTH_ENABLED) {
        const token = getWsToken();
        if (!token) {
            const entered = window.prompt('Enter WebSocket token (stored in browser localStorage as WS_AUTH_TOKEN).');
            if (entered && entered.trim()) {
                localStorage.setItem('WS_AUTH_TOKEN', entered.trim());
            }
        }
        const finalToken = getWsToken();
        if (finalToken) {
            wsUrl = `${wsBaseUrl}?token=${encodeURIComponent(finalToken)}`;
        }
    }

    console.log("Deep-linking to Neural Engine via WebSocket:", wsUrl);
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("Neural bridge established.");
        statusPulse.classList.add('connected');
    };

    socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        console.log("Broadcast received:", payload.event);
        
        switch(payload.event) {
            case 'signal':
                handleNewSignal(payload.data);
                break;
            case 'optimization_progress':
                handleOptimizationProgress(payload.data);
                break;
            case 'optimization_complete':
                handleOptimizationComplete(payload.data);
                break;
            case 'approval_needed':
                handleApprovalNeeded(payload.data);
                break;
            case 'status_update':
                updateStatus(payload.data);
                break;
        }
    };

    socket.onclose = () => {
        console.log("Bridge connection lost. Re-initializing in 5s...");
        statusPulse.classList.remove('connected');
        setTimeout(connectWebSocket, 5000);
    };
}

function handleNewSignal(signal) {
    const card = document.createElement('div');
    const dirClass = signal.signal.toLowerCase();
    card.className = `card signal-card fade-in ${dirClass}`;
    
    const arrow = signal.signal === 'LONG' ? '▲ ' : (signal.signal === 'SHORT' ? '▼ ' : '');
    const dirIndicator = signal.signal !== 'HOLD' ? `<span class="dir-indicator ${dirClass}"> - ${signal.signal}</span>` : '';
    
    card.innerHTML = `
        <div class="signal-header">
            <div class="signal-dir ${dirClass}">${arrow}${signal.signal}</div>
            ${signal.success ? `<div class="outcome-tag success">▲ ${signal.growth_pct}%</div>` : (signal.signal !== 'HOLD' ? `<div class="outcome-tag draw">▼ ${signal.max_drawdown}%</div>` : '')}
        </div>
        <div class="signal-info">
            <h3>${signal.symbol}${dirIndicator} <span>${signal.timeframe}</span></h3>
            
            <div class="trade-metrics-grid">
                <div class="metric-box">
                    <span class="metric-label">ENTRY</span>
                    <span class="metric-value">${signal.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">TYPE</span>
                    <span class="metric-value">${signal.order_type || 'LIMIT'}</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">CONFIDENCE</span>
                    <span class="metric-value">${signal.confidence.toFixed(1)}%</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">TAKE PROFIT</span>
                    <span class="metric-value success-text">${signal.take_profit.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">STOP LOSS</span>
                    <span class="metric-value draw-text">${signal.stop_loss.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                </div>
            </div>
        </div>
        <div class="signal-confidence" style="margin-top: 10px;">
            <div class="confidence-bar">
                <div class="confidence-fill" style="width: ${signal.confidence}%"></div>
            </div>
        </div>
    `;
    
    signalList.insertBefore(card, signalList.firstChild);
    if (signalList.children.length > 20) {
        signalList.removeChild(signalList.lastChild);
    }
}

function handleApprovalNeeded(approval) {
    const container = document.getElementById('pending-approvals');
    if (!container) return;

    const card = document.createElement('div');
    card.id = `approval-${approval.approval_id}`;
    card.className = 'card approval-card fade-in';
    
    // Check if it already exists
    if (document.getElementById(card.id)) return;

    card.innerHTML = `
        <div class="stat-label" style="color: var(--accent-gold)">Action Required: Pending Signal</div>
        <div class="signal-info">
            <h3 style="margin-bottom: 10px;">${approval.signal.symbol} <span>${approval.signal.timeframe}</span></h3>
            <div class="trade-metrics-grid" style="background: rgba(255, 204, 0, 0.05); border-color: rgba(255, 204, 0, 0.2)">
                <div class="metric-box">
                    <span class="metric-label">SIGNAL</span>
                    <span class="metric-value" style="color: ${approval.signal.signal === 'LONG' ? 'var(--accent-green)' : 'var(--accent-red)'}">${approval.signal.signal}</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">ENTRY</span>
                    <span class="metric-value">${approval.signal.entry_price.toFixed(2)}</span>
                </div>
                <div class="metric-box">
                    <span class="metric-label">CONFIDENCE</span>
                    <span class="metric-value">${approval.signal.confidence.toFixed(1)}%</span>
                </div>
            </div>
        </div>
        <div class="approval-actions">
            <button class="btn-reject" onclick="handleApprovalDecision('${approval.approval_id}', false)">Reject</button>
            <button class="btn-approve" onclick="handleApprovalDecision('${approval.approval_id}', true)">Approve Signal</button>
        </div>
    `;
    
    container.appendChild(card);
}

async function handleApprovalDecision(id, approved) {
    const btn = event.target;
    btn.disabled = true;
    btn.innerText = approved ? 'Approving...' : 'Rejecting...';

    try {
        const resp = await apiFetch(`/approvals/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approved })
        });
        const result = await resp.json();
        if (result.status === 'success' || result.result === 'ok') {
            const card = document.getElementById(`approval-${id}`);
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                setTimeout(() => card.remove(), 400);
            }
        }
    } catch (err) {
        console.error("Approval decision failed:", err);
        btn.disabled = false;
        btn.innerText = approved ? 'Approve Signal' : 'Reject';
    }
}

async function fetchApprovals() {
    try {
        const resp = await apiFetch('/approvals');
        const data = await resp.json();
        const container = document.getElementById('pending-approvals');
            data.forEach(app => handleApprovalNeeded({
                approval_id: app.approval_id,
                signal: app.signal
            }));
    } catch (err) {
        console.error("Approvals fetch failed:", err);
    }
}

function handleOptimizationProgress(data) {
    if (!optProgressContainer) return;
    optProgressContainer.style.display = 'block';
    optProgressFill.style.width = `${data.progress}%`;
    optStatusText.innerText = `Evolving Gen ${data.gen}/${data.total_gens} (${data.progress.toFixed(0)}%)`;
}

function handleOptimizationComplete(result) {
    console.log("Evolution Complete:", result);
    
    if (optResults && optBestParams) {
        optResults.style.display = 'block';
        
        let paramsHtml = `
            <div class="best-metric">
                🏆 OPTIMAL: Sharpe ${result.best_sharpe.toFixed(2)} | ROI ${result.best_return_pct.toFixed(1)}%
            </div>
            <div class="params-list">
        `;
        for (const [key, value] of Object.entries(result.best_params)) {
            paramsHtml += `<div><span>${key}:</span> <strong>${value}</strong></div>`;
        }
        paramsHtml += '</div>';
        optBestParams.innerHTML = paramsHtml;

        // Render Top Performers
        const performersEl = document.getElementById('opt-top-performers');
        if (performersEl && result.top_performers) {
            let perfHtml = '<div class="perf-title">Strategy Variants</div>';
            result.top_performers.slice(0, 3).forEach((p, i) => {
                perfHtml += `
                    <div class="perf-item">
                        <span>#${i+1} Variant</span>
                        <strong>${p.sharpe_ratio.toFixed(2)} SR</strong>
                    </div>
                `;
            });
            performersEl.innerHTML = perfHtml;
        }
    }
    
    if (optBtn) {
        optBtn.disabled = false;
        optBtn.classList.remove('loading');
        optBtn.innerHTML = `
            <div class="btn-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
            </div>
            <span>Sequence Complete</span>
        `;
    }
    
    // Refresh insights to show new lesson
    fetchInsights();
}

async function fetchStatus() {
    try {
        const resp = await apiFetch('/status');
        const data = await resp.json();
        updateStatusSummary(data);
    } catch (err) {
        console.error("Status fetch failed:", err);
    }
}

async function fetchInsights() {
    const lessonStream = document.getElementById('lesson-stream');
    try {
        const resp = await apiFetch('/insights');
        const data = await resp.json();
        
        if (lessonStream && data.recent_lessons) {
            if (data.recent_lessons.length === 0) {
                lessonStream.innerHTML = '<div class="terminal-loader">No lessons archived yet.</div>';
                return;
            }
            lessonStream.innerHTML = '';
            data.recent_lessons.forEach(lesson => {
                const item = document.createElement('div');
                item.className = 'lesson-item fade-in';
                item.innerHTML = `
                    <div class="lesson-header">
                        <span class="lesson-icon">🧠</span>
                        <span class="lesson-title">${lesson.title}</span>
                    </div>
                    <p class="lesson-text">${lesson.content}</p>
                `;
                lessonStream.appendChild(item);
            });
        }
    } catch (err) {
        console.error("Insights fetch failed:", err);
    }
}

function updateStatusSummary(data) {
    const mapping = {
        'stat-total-signals': data.total_signals,
        'stat-win-rate': `${data.signal_accuracy}%`,
        'stat-growth': `${data.avg_growth}%`,
        'stat-max-ae': `${data.max_ae}%`,
        'stat-success-count': Math.round((data.signal_accuracy / 100) * data.total_signals)
    };
    
    for (const [id, val] of Object.entries(mapping)) {
        const el = document.getElementById(id);
        if (el) {
            el.innerText = val;
            // Add visual feedback for updates
            el.classList.add('pulse');
            setTimeout(() => el.classList.remove('pulse'), 2000);
        }
    }
}

// Initial setup
ensureApiKeyIfRequired();

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    fetchStatus();
    fetchInsights();
    
    // Poll status every 30s
    setInterval(fetchStatus, 30000);
    fetchApprovals();
    
    // Command Center Listeners
    const btnPause = document.getElementById('btn-pause-resume');
    const txtPause = document.getElementById('txt-pause-resume');
    const btnRunAll = document.getElementById('btn-run-all');

    if (btnPause) {
        btnPause.addEventListener('click', async () => {
            const isPaused = btnPause.classList.contains('paused');
            const endpoint = isPaused ? '/resume' : '/pause';
            
            btnPause.disabled = true;
            try {
                const resp = await apiFetch(endpoint, { method: 'POST' });
                const data = await resp.json();
                
                if (data.paused) {
                    btnPause.className = 'btn-command paused';
                    txtPause.innerText = 'RESUME SESSION';
                } else {
                    btnPause.className = 'btn-command active';
                    txtPause.innerText = 'PAUSE SESSION';
                }
            } catch (err) {
                console.error("Action failed:", err);
            } finally {
                btnPause.disabled = false;
            }
        });
    }

    if (btnRunAll) {
        btnRunAll.addEventListener('click', async () => {
            btnRunAll.disabled = true;
            const originalText = btnRunAll.innerHTML;
            btnRunAll.innerHTML = '<span>SEQUENCING...</span>';
            
            try {
                await apiFetch('/signals/run', { method: 'POST' });
            } catch (err) {
                console.error("Run failed:", err);
            } finally {
                btnRunAll.disabled = false;
                btnRunAll.innerHTML = originalText;
            }
        });
    }

    const btnGlobalScan = document.getElementById('btn-global-scan');
    const scannerResults = document.getElementById('scanner-results');
    const scannerList = document.getElementById('scanner-list');

    if (btnGlobalScan) {
        btnGlobalScan.addEventListener('click', async () => {
            btnGlobalScan.disabled = true;
            const originalText = btnGlobalScan.innerHTML;
            btnGlobalScan.innerHTML = '<span>SCANNING...</span>';
            scannerResults.style.display = 'none';

            try {
                const resp = await apiFetch('/scanner/run', { method: 'POST' });
                const data = await resp.json();
                
                if (data.candidates && data.candidates.length > 0) {
                    scannerList.innerHTML = '';
                    data.candidates.forEach(sig => {
                        const card = document.createElement('div');
                        card.className = `card signal-card fade-in ${sig.signal.toLowerCase()}`;
                        card.innerHTML = `
                            <div class="signal-header">
                                <div class="signal-dir ${sig.signal.toLowerCase()}">
                                    ${sig.signal === 'LONG' ? '▲' : '▼'} ${sig.signal}
                                </div>
                                <div class="outcome-tag success">ALPHA</div>
                            </div>
                            <div class="signal-info">
                                <h3>${sig.symbol} <span class="dir-indicator ${sig.signal.toLowerCase()}"> - ${sig.signal}</span></h3>
                                <div class="trade-metrics-grid">
                                    <div class="metric-box">
                                        <span class="metric-label">ENTRY</span>
                                        <span class="metric-value">${sig.entry_price.toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
                                    </div>
                                    <div class="metric-box">
                                        <span class="metric-label">CONFIDENCE</span>
                                        <span class="metric-value">${sig.confidence.toFixed(1)}%</span>
                                    </div>
                                </div>
                            </div>
                        `;
                        scannerList.appendChild(card);
                    });
                    scannerResults.style.display = 'block';
                    scannerResults.scrollIntoView({ behavior: 'smooth' });
                } else {
                    alert("Scan complete. No high-confidence opportunities found in current market state.");
                }
            } catch (err) {
                console.error("Global scan failed:", err);
            } finally {
                btnGlobalScan.disabled = false;
                btnGlobalScan.innerHTML = originalText;
            }
        });
    }

    if (optBtn) {
        optBtn.addEventListener('click', async () => {
            optBtn.disabled = true;
            optBtn.innerText = "Initializing RL Seeds...";
            optResults.style.display = 'none';
            optProgressContainer.style.display = 'block';
            optProgressFill.style.width = '0%';
            
            try {
                const resp = await apiFetch('/optimize', { method: 'POST' });
                const result = await resp.json();
                handleOptimizationComplete(result);
            } catch (err) {
                console.error("Evolution failed:", err);
                optStatusText.innerText = "Error: Sequence Interrupted.";
                optBtn.disabled = false;
            }
        });
    }
});
