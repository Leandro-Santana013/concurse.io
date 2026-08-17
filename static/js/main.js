document.addEventListener('DOMContentLoaded', () => {
    // ===== TOAST SYSTEM =====
    const toastContainer = document.getElementById('toast-container');
    function showToast(message, type = 'info', duration = 4000) {
        const icons = { success: 'ph-check-circle', error: 'ph-x-circle', warning: 'ph-warning', info: 'ph-info' };
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.setProperty('--toast-duration', `${duration}ms`);
        toast.innerHTML = `
            <i class="ph ${icons[type] || icons.info}"></i>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.classList.add('toast-exit'); setTimeout(() => this.parentElement.remove(), 300);">&times;</button>
            <div class="toast-progress"></div>
        `;
        toastContainer.appendChild(toast);
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('toast-exit');
                setTimeout(() => toast.remove(), 300);
            }
        }, duration);
    }

    // ===== STATE =====
    let currentFolderId = null;
    let currentExamQuestions = [];
    let currentQuestionIndex = 0;
    let currentExamAnswers = {};
    let examSubjects = {};
    let flaggedQuestions = new Set();
    let examTimerInterval = null;
    let examStartTime = null;
    let activeFilters = ['all'];
    let currentExamId = null;

    // ===== DOM ELEMENTS =====
    const views = document.querySelectorAll('.view-section');
    const navItems = document.querySelectorAll('.nav-item');
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');
    const searchResults = document.getElementById('search-results');
    const foldersList = document.getElementById('folders-list');
    const examCardTemplate = document.getElementById('exam-card-template');

    let orchestratorInterval = null;
    const API_BASE = '/api';

    // ===== INIT =====
    checkApiKey();
    loadFolders();
    loadRecentSearches();
    initMobileSidebar();
    initFloatingNav();
    initFilterChips();
    initThemeToggle();
    // ===== MOBILE SIDEBAR =====
    function initMobileSidebar() {
        const toggle = document.getElementById('sidebar-toggle');
        const overlay = document.getElementById('sidebar-overlay');
        const sidebar = document.querySelector('.sidebar');
        if (toggle && overlay && sidebar) {
            toggle.addEventListener('click', () => {
                sidebar.classList.toggle('open');
                overlay.classList.toggle('active');
            });
            overlay.addEventListener('click', () => {
                sidebar.classList.remove('open');
                overlay.classList.remove('active');
            });
        }
    }

    // ===== FLOATING NAV LOGIC =====
    function initFloatingNav() {
        const sidebar = document.querySelector('.sidebar');
        if (!sidebar) return;
        
        const mainContent = document.querySelector('.main-content');
        if (!mainContent) return;

        let lastScrollY = mainContent.scrollTop;
        
        mainContent.addEventListener('scroll', () => {
            const currentScrollY = mainContent.scrollTop;
            if (currentScrollY > lastScrollY && currentScrollY > 60) {
                // Scrolling down
                if (!sidebar.matches(':hover')) {
                    sidebar.classList.add('nav-hidden');
                }
            } else {
                // Scrolling up
                sidebar.classList.remove('nav-hidden');
            }
            lastScrollY = currentScrollY;
        });

        sidebar.addEventListener('mouseleave', () => {
            if (mainContent.scrollTop > 60) {
                sidebar.classList.add('nav-hidden');
            }
        });
        
        sidebar.addEventListener('mouseenter', () => {
            sidebar.classList.remove('nav-hidden');
        });
    }

    // ===== THEME TOGGLE =====
    function initThemeToggle() {
        const btn = document.getElementById('theme-toggle-btn');
        if (!btn) return;
        const currentTheme = localStorage.getItem('theme') || 'light';
        if (currentTheme === 'light') {
            document.documentElement.setAttribute('data-theme', 'light');
            btn.innerHTML = '<i class="ph ph-moon"></i> <span>Modo Escuro</span>';
        } else {
            document.documentElement.removeAttribute('data-theme');
            btn.innerHTML = '<i class="ph ph-sun"></i> <span>Modo Claro</span>';
        }
        btn.addEventListener('click', () => {
            const isLight = document.documentElement.getAttribute('data-theme') === 'light';
            if (isLight) {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('theme', 'dark');
                btn.innerHTML = '<i class="ph ph-moon"></i> <span>Modo Escuro</span>';
            } else {
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('theme', 'light');
                btn.innerHTML = '<i class="ph ph-sun"></i> <span>Modo Claro</span>';
            }
        });
    }

    // ===== FILTER CHIPS =====
    function initFilterChips() {
        document.querySelectorAll('.filter-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                const source = chip.dataset.source;
                if (source === 'all') {
                    document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    activeFilters = ['all'];
                } else {
                    document.querySelector('.filter-chip[data-source="all"]').classList.remove('active');
                    chip.classList.toggle('active');
                    activeFilters = Array.from(document.querySelectorAll('.filter-chip.active')).map(c => c.dataset.source).filter(s => s !== 'all');
                    if (activeFilters.length === 0) {
                        document.querySelector('.filter-chip[data-source="all"]').classList.add('active');
                        activeFilters = ['all'];
                    }
                }
            });
        });
    }

    // ===== RECENT SEARCHES =====
    function loadRecentSearches() {
        const container = document.getElementById('recent-searches');
        if (!container) return;
        const searches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        container.innerHTML = '';
        searches.slice(0, 5).forEach(term => {
            const chip = document.createElement('button');
            chip.className = 'search-chip';
            chip.innerHTML = `<i class="ph ph-clock-counter-clockwise"></i>${term}`;
            chip.addEventListener('click', () => {
                searchInput.value = term;
                performSearch();
            });
            container.appendChild(chip);
        });
    }

    function saveRecentSearch(term) {
        if (!term || term.length < 3) return;
        let searches = JSON.parse(localStorage.getItem('recentSearches') || '[]');
        searches = searches.filter(s => s !== term);
        searches.unshift(term);
        if (searches.length > 5) searches = searches.slice(0, 5);
        localStorage.setItem('recentSearches', JSON.stringify(searches));
        loadRecentSearches();
    }

    // ===== API KEY MODAL =====
    async function checkApiKey() {
        try {
            const res = await fetch(`${API_BASE}/config/keys_status`);
            if (res.ok) {
                const data = await res.json();
                if (data.total === 0) {
                    document.getElementById('api-key-modal').style.display = 'flex';
                }
            }
        } catch (e) {
            console.error('Erro ao checar API Key:', e);
        }
    }

    document.getElementById('btn-save-api-key').addEventListener('click', async () => {
        const key1 = document.getElementById('api-key-input-1').value.trim();
        const key2 = document.getElementById('api-key-input-2').value.trim();
        const key3 = document.getElementById('api-key-input-3').value.trim();

        if (!key1) {
            showToast('Preencha pelo menos a primeira chave para continuar.', 'warning');
            return;
        }

        const keys = [key1, key2, key3].filter(k => k);

        try {
            const res = await fetch(`${API_BASE}/config/keys/bulk`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ keys: keys })
            });
            const data = await res.json();
            if (data.success) {
                document.getElementById('api-key-modal').style.display = 'none';
                showToast(`${keys.length} chave(s) configurada(s) com sucesso!`, 'success');
                if (typeof fetchKeysStatus === 'function') fetchKeysStatus();
            } else {
                showToast('Erro ao salvar chaves: ' + data.error, 'error');
            }
        } catch (e) {
            showToast('Erro de conexão ao salvar chave.', 'error');
        }
    });

    document.getElementById('btn-close-api-key').addEventListener('click', () => {
        document.getElementById('api-key-modal').style.display = 'none';
    });

    window.editApiKeys = function () {
        document.getElementById('api-key-modal').style.display = 'flex';
        document.getElementById('btn-close-api-key').style.display = 'block';
    };
    
    async function fetchKeysStatus() {
        const listEl = document.getElementById('apiKeysList');
        if (!listEl) return;
        try {
            const res = await fetch(`${API_BASE}/config/glm_key`);
            if (res.ok) {
                const data = await res.json();
                const rawKey = data.api_key || '';
                const keys = rawKey.split(',').map(k => k.trim()).filter(k => k);
                
                if (keys.length > 0) {
                    listEl.innerHTML = keys.map((k, i) => `
                        <div class="api-key-item" style="display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: rgba(255,255,255,0.03); border-radius: 8px; margin-bottom: 6px;">
                            <span>Chave ${i+1}: <code>${k.substring(0, 10)}...</code></span>
                            <button class="btn btn-secondary btn-sm" onclick="removeApiKey('${k}')"><i class="ph ph-trash"></i> Remover</button>
                        </div>
                    `).join('');
                } else {
                    listEl.innerHTML = `<p class="text-muted" style="color: var(--text-secondary); font-size: 0.9rem;">Nenhuma chave configurada.</p>`;
                }
            }
        } catch (e) {
            console.error('Erro ao buscar status de chaves:', e);
        }
    }
    
    window.removeApiKey = async (keyToRemove) => {
        if (!keyToRemove) return;
        if (!confirm('Deseja remover esta chave de API?')) return;
        try {
            const res = await fetch(`${API_BASE}/config/glm_key`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: keyToRemove, action: 'remove' })
            });
            const data = await res.json();
            if (data.success) {
                showToast('Chave removida com sucesso!', 'info');
                fetchKeysStatus();
            } else {
                showToast('Erro ao remover chave: ' + (data.error || 'Erro desconhecido'), 'error');
            }
        } catch (e) {
            showToast('Erro de conexão ao remover chave.', 'error');
        }
    };
    
    window.addApiKey = async () => {
        const key = prompt("Cole a nova chave da API (NVIDIA/GLM) para adicionar:");
        if (!key || !key.trim()) return;
        
        try {
            const res = await fetch(`${API_BASE}/config/glm_key`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: key.trim(), action: 'append' })
            });
            const data = await res.json();
            if (data.success) {
                showToast(`Chave adicionada com sucesso!`, 'success');
                fetchKeysStatus();
            } else {
                showToast('Erro ao salvar chave: ' + data.error, 'error');
            }
        } catch (e) {
            showToast('Erro de conexão ao salvar chave.', 'error');
        }
    };

    // ===== NAVIGATION =====
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const viewId = e.currentTarget.getAttribute('data-view');
            switchView(`view-${viewId}`);
            document.querySelectorAll('.sidebar .nav-item').forEach(a => a.classList.remove('active'));
            e.currentTarget.classList.add('active');
            // Close mobile sidebar
            document.querySelector('.sidebar')?.classList.remove('open');
            document.getElementById('sidebar-overlay')?.classList.remove('active');
        });
    });

    function switchView(viewId) {
        const targetEl = document.getElementById(viewId);
        if (!targetEl) return;
        document.querySelectorAll('.view-section').forEach(el => el.style.display = 'none');
        targetEl.style.display = 'block';
        if (viewId === 'view-manager') startOrchestratorPolling();
        else stopOrchestratorPolling();
        if (viewId !== 'view-exam') stopExamTimer();
        if (viewId === 'view-stats') loadGlobalStats();
        if (viewId === 'view-errors') loadErrorStats();
        if (viewId === 'view-ranking') loadRanking();
    }

    async function loadGlobalStats() {
        try {
            const res = await fetch(`${API_BASE}/stats`);
            const data = await res.json();
            document.getElementById('stat-total-exams').textContent = data.total_exams || 0;
            document.getElementById('stat-total-questions').textContent = data.total_questions || 0;
            document.getElementById('stat-accuracy').textContent = (data.global_accuracy || 0) + '%';
            document.getElementById('stat-streak').textContent = data.streak || 0;
            
            const timeEl = document.getElementById('stat-time');
            if (timeEl) timeEl.textContent = data.study_time || '0m';
            
            const rankEl = document.getElementById('stat-rank');
            if (rankEl) rankEl.textContent = data.rank || '-';
            
        } catch (e) { console.error('Erro ao carregar stats:', e); }
    }

    document.querySelector('.logo').addEventListener('click', () => {
        document.querySelectorAll('.sidebar .nav-item').forEach(el => el.classList.remove('active'));
        switchView('view-dashboard');
    });

    const userProfileBtn = document.getElementById('user-profile-btn');
    if (userProfileBtn) {
        userProfileBtn.addEventListener('click', (e) => {
            e.preventDefault();
            document.querySelectorAll('.sidebar .nav-item').forEach(el => el.classList.remove('active'));
            switchView('view-profile');
            document.querySelector('.sidebar')?.classList.remove('open');
            document.getElementById('sidebar-overlay')?.classList.remove('active');
        });
    }

    window.openManagerView = function() {
        document.querySelectorAll('.sidebar .nav-item').forEach(el => el.classList.remove('active'));
        switchView('view-manager');
    };

    async function loadRanking() {
        try {
            const res = await fetch(`${API_BASE}/ranking`);
            const data = await res.json();
            const list = document.getElementById('ranking-list');
            if (!list) return;
            if (data.length === 0) {
                list.innerHTML = `<tr><td colspan="4" style="text-align: center; padding: 20px; color: var(--text-muted);">Nenhum dado de ranking disponível.</td></tr>`;
                return;
            }
            list.innerHTML = data.map((user, index) => {
                let badge = `${index + 1}º`;
                if (index === 0) badge = `<span style="color: #fbbf24; font-weight: bold; font-size: 1.2rem;"><i class="ph ph-medal"></i> 1º</span>`;
                else if (index === 1) badge = `<span style="color: #94a3b8; font-weight: bold; font-size: 1.1rem;"><i class="ph ph-medal"></i> 2º</span>`;
                else if (index === 2) badge = `<span style="color: #b45309; font-weight: bold; font-size: 1.1rem;"><i class="ph ph-medal"></i> 3º</span>`;
                
                return `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s;">
                        <td style="padding: 16px 12px; font-weight: 600;">${badge}</td>
                        <td style="padding: 16px 12px; display: flex; align-items: center; gap: 12px;">
                            <img src="${user.picture}" alt="Profile" style="width: 32px; height: 32px; border-radius: 50%;">
                            <span style="font-weight: 500;">${user.name}</span>
                        </td>
                        <td style="padding: 16px 12px; font-weight: bold;">${user.total_questions}</td>
                        <td style="padding: 16px 12px; color: ${user.accuracy > 70 ? 'var(--success-color)' : (user.accuracy > 50 ? 'var(--warning-color)' : 'var(--danger-color)')}; font-weight: bold;">${user.accuracy}%</td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            console.error('Erro ao carregar ranking:', e);
            const list = document.getElementById('ranking-list');
            if(list) list.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--danger-color);">Erro ao carregar ranking.</td></tr>`;
        }
    }

    // ===== ORCHESTRATOR POLLING =====
    function startOrchestratorPolling() {
        if (orchestratorInterval) clearInterval(orchestratorInterval);
        fetchOrchestratorStatus();
        orchestratorInterval = setInterval(fetchOrchestratorStatus, 2000);
    }
    function stopOrchestratorPolling() {
        if (orchestratorInterval) clearInterval(orchestratorInterval);
    }

    async function fetchOrchestratorStatus() {
        try {
            const res = await fetch(`${API_BASE}/orchestrator/status`);
            const data = await res.json();
            const modelsList = document.getElementById('manager-models-list');
            if (modelsList) {
                modelsList.innerHTML = data.models_loaded.map(m => `
                    <li style="display: flex; align-items: center; gap: 8px; padding: 12px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                        <div style="width: 10px; height: 10px; border-radius: 50%; background: #10b981;"></div>
                        <span style="font-family: monospace; font-size: 0.9rem;">${m}</span>
                    </li>
                `).join('');
            }
            const queueCount = document.getElementById('manager-queue-count');
            const queueList = document.getElementById('manager-queue-list');
            if (queueCount) queueCount.textContent = `${data.queue_length} pendentes`;
            if (queueList) {
                if (data.queue_length === 0) {
                    queueList.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">Nenhuma tarefa na fila no momento.</div>`;
                } else {
                    queueList.innerHTML = data.queue.map(t => `
                        <div style="padding: 16px; border: 1px solid var(--border-color); border-radius: 8px; border-left: 4px solid ${t.status === 'rodando' ? '#3b82f6' : '#f59e0b'}; background: rgba(0,0,0,0.2);">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <strong style="font-size: 0.95rem;">${t.type === 'extract_questions' ? 'Extração de PDF' : 'Geração de Simulada'}</strong>
                                <span style="font-size: 0.8rem; background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 12px;">${t.status.toUpperCase()}</span>
                            </div>
                            <div style="font-size: 0.85rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 4px;">
                                <span><i class="ph ph-hash"></i> Tarefa: ${t.id.split('-')[0]}...</span>
                                <span><i class="ph ph-robot"></i> Modelo: ${t.model}</span>
                            </div>
                        </div>
                    `).join('');
                }
            }
        } catch (error) { console.error("Orchestrator polling failed", error); }
    }

    // Fetch keys status when manager view opens
    async function fetchKeysStatus() {
        try {
            const res = await fetch(`${API_BASE}/config/keys_status`);
            const data = await res.json();
            const container = document.getElementById('manager-keys-status');
            if (!container) return;
            if (!data.keys || data.keys.length === 0) {
                container.innerHTML = '<p style="color: var(--text-muted);">Nenhuma chave configurada.</p>';
                return;
            }
            container.innerHTML = data.keys.map(k => {
                const colors = { active: '#10b981', exhausted: '#ef4444', invalid: '#f59e0b' };
                const icons = { active: 'ph-check-circle', exhausted: 'ph-x-circle', invalid: 'ph-warning' };
                const rawParam = (k.raw || '').replace(/'/g, "\\'");
                return `
                    <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px; background: rgba(255,255,255,0.03); border-radius: 8px; border-left: 3px solid ${colors[k.status] || '#10b981'};">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <i class="ph ${icons[k.status] || 'ph-check-circle'}" style="color: ${colors[k.status] || '#10b981'}; font-size: 20px;"></i>
                            <div>
                                <span style="font-family: monospace; font-size: 0.9rem;">Chave ${k.index} (${k.suffix})</span><br>
                                <span style="font-size: 0.8rem; color: ${colors[k.status] || '#10b981'}; font-weight: 600;">${k.label}</span>
                            </div>
                        </div>
                        <button class="btn btn-secondary btn-sm" onclick="window.removeApiKey('${rawParam}')" style="padding: 4px 10px; font-size: 0.8rem; color: var(--danger-color);">
                            <i class="ph ph-trash"></i> Remover
                        </button>
                    </div>
                `;
            }).join('');
        } catch (e) { console.error('Erro ao buscar status das chaves:', e); }
    }

    // Keys status button
    const btnCheckKeys = document.getElementById('btn-check-keys');
    if (btnCheckKeys) {
        btnCheckKeys.addEventListener('click', async () => {
            btnCheckKeys.disabled = true;
            btnCheckKeys.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Verificando...';
            await fetchKeysStatus();
            btnCheckKeys.disabled = false;
            btnCheckKeys.innerHTML = '<i class="ph ph-arrows-clockwise"></i> Verificar';
        });
    }

    // ===== SEARCH =====
    searchBtn.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') performSearch(); });
    document.getElementById('back-to-folder-btn').addEventListener('click', () => switchView('view-folder'));

    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        saveRecentSearch(query);
        searchBtn.disabled = true;
        searchBtn.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Buscando...';

        // Show skeleton
        showSearchSkeleton();

        // Build sources param from filter chips
        let sourcesParam = '';
        if (!activeFilters.includes('all')) {
            sourcesParam = `&sources=${activeFilters.join(',')}`;
        }

        try {
            const response = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}${sourcesParam}`);
            const data = await response.json();
            renderSearchResults(data);
        } catch (error) {
            console.error("Search failed:", error);
            showToast('Erro ao buscar provas. Verifique sua conexão.', 'error');
            searchResults.innerHTML = `<div class="empty-state"><i class="ph ph-wifi-x"></i><p>Erro de conexão.</p></div>`;
        } finally {
            searchBtn.disabled = false;
            searchBtn.innerHTML = 'Buscar';
        }
    }

    function showSearchSkeleton() {
        let skeletonHtml = `<div class="search-status-text"><i class="ph ph-spinner ph-spin"></i>Consultando fontes de provas...</div>`;
        for (let i = 0; i < 6; i++) {
            skeletonHtml += `
                <div class="skeleton-card">
                    <div class="skeleton-line w40"></div>
                    <div class="skeleton-line h20 w80"></div>
                    <div class="skeleton-line w60"></div>
                    <div class="skeleton-actions">
                        <div class="skeleton-btn"></div>
                        <div class="skeleton-btn"></div>
                    </div>
                </div>
            `;
        }
        searchResults.innerHTML = skeletonHtml;
    }

    function detectSource(title, url) {
        const t = (title || '').toLowerCase();
        const u = (url || '').toLowerCase();
        if (t.startsWith('idcap') || u.includes('idcap') || u.includes('selecao.net.br')) return 'idcap';
        if (t.startsWith('pci') || u.includes('pciconcursos')) return 'pci';
        if (u.includes('qconcursos')) return 'qconcursos';
        if (t.startsWith('web -')) return 'web';
        if (u.includes('cesgranrio') || u.includes('cebraspe') || u.includes('fcc') || u.includes('vunesp')) return 'banco';
        return 'web';
    }

    function getSourceLabel(source) {
        const labels = {
            idcap: 'IDCAP', pci: 'PCI Concursos',
            web: 'Web', qconcursos: 'QConcursos', glm: 'GLM IA', banco: 'Banco Interno'
        };
        return labels[source] || 'Web';
    }

    function renderSearchResults(results) {
        searchResults.innerHTML = '';
        if (results.length === 0) {
            searchResults.innerHTML = `
                <div class="empty-state">
                    <i class="ph ph-x-circle"></i>
                    <p>Nenhuma prova encontrada para essa busca.</p>
                </div>
            `;
            return;
        }

        // Primeiro ordena do maior match para o menor
        results.sort((a, b) => (b.match_score || 0) - (a.match_score || 0));

        results.forEach(exam => {
            const source = detectSource(exam.title, exam.url);
            const clone = examCardTemplate.content.cloneNode(true);
            const card = clone.querySelector('.exam-card');

            // Clean title
            let cleanTitle = exam.title;
            if (cleanTitle.startsWith('Web - ')) cleanTitle = cleanTitle.substring(6);

            clone.querySelector('.exam-card-title').textContent = cleanTitle;

            // Source badge + full URL
            const sourceEl = clone.querySelector('.exam-source');

            try {
                sourceEl.innerHTML = `<span class="source-badge source-${source}">${getSourceLabel(source)}</span><div style="font-size: 0.8em; word-break: break-all; margin-top: 5px; color: var(--text-secondary);">${exam.url}</div>`;
            } catch {
                sourceEl.innerHTML = `<span class="source-badge source-${source}">${getSourceLabel(source)}</span>`;
            }

            const btnApprove = clone.querySelector('.btn-approve');
            const btnDeny = clone.querySelector('.btn-deny');

            btnApprove.addEventListener('click', () => {
                if (exam.url && exam.url.includes('pciconcursos.com.br')) {
                    openPciManualModal(exam.id, exam.url, card, btnApprove, btnDeny);
                } else {
                    btnApprove.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Baixando...';
                    btnApprove.disabled = true;
                    btnDeny.disabled = true;
                    handleTriage(exam.id, 'Aprovada', card);
                }
            });
            btnDeny.addEventListener('click', () => handleTriage(exam.id, 'Negada', card));

            searchResults.appendChild(clone);
        });
    }

    // ===== TRIAGE =====
    async function handleTriage(examId, status, cardElement) {
        let progressInterval = null;
        let progressBarContainer = null;

        function removeCard() {
            cardElement.style.opacity = '0';
            cardElement.style.transform = 'scale(0.9)';
            setTimeout(() => {
                cardElement.remove();
                if (searchResults.children.length === 0) {
                    searchResults.innerHTML = '<div class="empty-state"><i class="ph ph-check-circle"></i><p>Triagem concluída!</p></div>';
                }
            }, 300);
        }

        if (status === 'Aprovada') {
            progressBarContainer = document.createElement('div');
            progressBarContainer.className = 'progress-container';
            progressBarContainer.style.marginTop = '15px';
            progressBarContainer.innerHTML = `
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.85rem;">
                    <span class="progress-status" style="color: var(--text-color);">Iniciando...</span>
                    <span class="progress-pct" style="font-weight: bold;">0%</span>
                </div>
                <div style="width: 100%; height: 6px; background-color: var(--border-color); border-radius: 4px; overflow: hidden;">
                    <div class="progress-bar" style="width: 0%; height: 100%; background-color: var(--primary-color); transition: width 0.3s ease;"></div>
                </div>
            `;
            const buttonsDiv = cardElement.querySelector('.exam-actions');
            if (buttonsDiv) buttonsDiv.parentElement.insertBefore(progressBarContainer, buttonsDiv.nextSibling);
            else cardElement.appendChild(progressBarContainer);

            progressInterval = setInterval(async () => {
                try {
                    const res = await fetch(`${API_BASE}/exams/${examId}/progress`);
                    if (res.ok) {
                        const progData = await res.json();
                        const statusEl = progressBarContainer.querySelector('.progress-status');
                        const pctEl = progressBarContainer.querySelector('.progress-pct');
                        const barEl = progressBarContainer.querySelector('.progress-bar');
                        statusEl.innerText = progData.status;
                        pctEl.innerText = progData.progress + '%';
                        barEl.style.width = progData.progress + '%';
                        if (progData.status.includes('Cota') || progData.status.includes('Aguardando')) {
                            barEl.style.backgroundColor = '#f59e0b';
                        } else {
                            barEl.style.backgroundColor = 'var(--primary-color)';
                        }
                        if (progData.progress === 100 || progData.progress === -1) {
                            if (progressInterval) {
                                clearInterval(progressInterval);
                                progressInterval = null; // Prevent multiple executions
                                if (progData.progress === 100) {
                                    barEl.style.backgroundColor = '#10b981';
                                    barEl.classList.remove('progress-bar-processing');
                                    const ba = cardElement.querySelector('.btn-approve');
                                    if (ba) ba.innerHTML = '<i class="ph ph-check"></i> Processado';
                                    showToast('Prova processada com sucesso!', 'success');
                                    setTimeout(() => { removeCard(); loadFolders(); }, 1500);
                                } else {
                                    barEl.style.backgroundColor = '#ef4444';
                                    barEl.classList.remove('progress-bar-processing');
                                    const ba = cardElement.querySelector('.btn-approve');
                                    if (ba) { ba.innerHTML = '<i class="ph ph-warning"></i> Erro'; ba.classList.add('btn-danger'); ba.classList.remove('btn-success'); }
                                // Contextual error message
                                const errType = progData.error_type || 'unknown';
                                let errAction = '';
                                if (errType === 'quota_exceeded') {
                                    errAction = ' Aguarde 1 min ou adicione mais chaves no Manager.';
                                } else if (errType === 'download_blocked') {
                                    errAction = ' Tente colar o link direto do PDF.';
                                } else if (errType === 'timeout') {
                                    errAction = ' A prova é muito grande. Tente novamente.';
                                }
                                showToast(progData.status + errAction, 'error', 8000);
                            }
                            }
                        } else {
                            // Pulse animation during AI processing
                            if (progData.progress >= 35 && progData.progress < 90) {
                                barEl.classList.add('progress-bar-processing');
                            }
                        }
                    }
                } catch (e) { console.error("Erro ao ler progresso:", e); }
            }, 1000);
        }

        try {
            const response = await fetch(`${API_BASE}/exams/${examId}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status })
            });
            const data = await response.json();
            if (!data.success) {
                if (progressInterval) clearInterval(progressInterval);
                if (progressBarContainer) progressBarContainer.remove();
                showToast('Falha ao processar a prova: ' + (data.error || 'Erro desconhecido'), 'error', 6000);
                const ba = cardElement.querySelector('.btn-approve');
                const bd = cardElement.querySelector('.btn-deny');
                if (ba) { ba.disabled = false; ba.innerHTML = '<i class="ph ph-download-simple"></i> Baixar Prova'; }
                if (bd) bd.disabled = false;
                return;
            }
            if (status === 'Negada') {
                if (progressInterval) clearInterval(progressInterval);
                removeCard();
            }
        } catch (error) {
            if (progressInterval) clearInterval(progressInterval);
            if (progressBarContainer) progressBarContainer.remove();
            showToast('Erro de conexão ao triar a prova.', 'error');
            const ba = cardElement.querySelector('.btn-approve');
            const bd = cardElement.querySelector('.btn-deny');
            if (ba) { ba.disabled = false; ba.innerHTML = '<i class="ph ph-download-simple"></i> Baixar Prova'; }
            if (bd) bd.disabled = false;
        }
    }

    // ===== FOLDERS =====
    async function loadFolders() {
        try {
            const response = await fetch(`${API_BASE}/folders`);
            const folders = await response.json();
            renderFoldersMenu(folders);
        } catch (error) { console.error("Failed to load folders", error); }
    }

    function renderFoldersMenu(folders) {
        const foldersList = document.getElementById('folders-list');
        if (!foldersList) return;
        foldersList.innerHTML = '';
        if (folders.length === 0) {
            foldersList.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="ph ph-folder-open"></i>
                    <p style="margin-bottom: 16px;">Você ainda não possui provas baixadas.</p>
                    <button class="btn btn-primary" onclick="document.querySelector('.nav-item[data-view=\\'dashboard\\']').click();"><i class="ph ph-magnifying-glass"></i> Buscar Novas Provas</button>
                </div>
            `;
            return;
        }
        folders.forEach(folder => {
            const card = document.createElement('div');
            card.className = "card fade-in";
            card.style.cssText = "background: var(--bg-card); padding: 24px; border-radius: 12px; border: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 12px;";
            card.innerHTML = `
                <h3 style="font-size: 1.1rem; color: var(--text-primary);"><i class="ph ph-folder" style="color: var(--primary-color);"></i> ${folder.name}</h3>
                <p style="color: var(--text-secondary); font-size: 0.9rem;">${folder.exams.length} prova(s) disponíveis</p>
                <div style="margin-top: auto; padding-top: 16px;">
                    <button class="btn btn-primary" style="width: 100%; justify-content: center;"><i class="ph ph-folder-open"></i> Abrir Pasta</button>
                </div>
            `;
            const btn = card.querySelector('.btn-primary');
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                openFolder(folder);
            });
            foldersList.appendChild(card);
        });
    }

    function openFolder(folder) {
        currentFolderId = folder.id;
        document.getElementById('folder-title').textContent = folder.name;
        const examsList = document.getElementById('folder-exams');
        examsList.innerHTML = '';
        if (folder.exams.length === 0) {
            examsList.innerHTML = `
                <div class="empty-state">
                    <i class="ph ph-folder-open"></i>
                    <p style="margin-bottom: 16px;">Esta pasta está vazia.</p>
                    <button class="btn btn-primary" onclick="document.querySelector('.nav-item[data-view=\\'dashboard\\']').click();"><i class="ph ph-magnifying-glass"></i> Buscar Novas Provas</button>
                </div>
            `;
        } else {
            folder.exams.forEach(exam => {
                const card = document.createElement('div');
                card.className = 'exam-card fade-in';

                // Stats de tentativas
                let statsHtml = '';
                if (exam.attempt_count > 0) {
                    statsHtml = `
                        <div style="display: flex; gap: 12px; margin-top: 8px; margin-bottom: 12px; font-size: 0.8rem;">
                            <span style="color: var(--success-color);"><i class="ph ph-trophy"></i> Melhor: ${exam.best_score}%</span>
                            <span style="color: var(--text-secondary);"><i class="ph ph-clock-counter-clockwise"></i> Última: ${exam.last_score}%</span>
                            <span style="color: var(--text-secondary);"><i class="ph ph-repeat"></i> ${exam.attempt_count}x</span>
                        </div>
                    `;
                }

                card.innerHTML = `
                    <h3 class="exam-card-title">${exam.title}</h3>
                    ${statsHtml}
                    <div style="margin-top: ${exam.attempt_count > 0 ? '8' : '16'}px; display: flex; align-items: center; gap: 8px;">
                        <button class="btn btn-primary" onclick="window.startExam(${exam.id})"><i class="ph ph-play-circle"></i> Resolver Prova</button>
                        <button class="btn btn-danger" onclick="window.deleteExam(${exam.id}, this)"><i class="ph ph-trash"></i> Remover</button>
                    </div>
                `;
                examsList.appendChild(card);
            });
        }
        switchView('view-folder');
    }

    window.startExam = loadExam;
    window.deleteExam = async function (examId, btnElement) {
        const overlay = document.createElement('div');
        overlay.style.cssText = `position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 9999; display: flex; align-items: center; justify-content: center;`;
        overlay.innerHTML = `
            <div style="background: var(--bg-card, #1e2235); border: 1px solid var(--border-color, #333); border-radius: 16px; padding: 32px; max-width: 420px; width: 90%; text-align: center;">
                <h3 style="margin-bottom: 12px; font-size: 1.2rem; color: #fff;">Remover Prova?</h3>
                <p style="color: var(--text-muted, #aaa); margin-bottom: 24px;">Tem certeza que deseja remover esta prova da sua lista?</p>
                <div style="display: flex; gap: 12px; justify-content: center;">
                    <button id="del-cancel" class="btn btn-secondary">Cancelar</button>
                    <button id="del-confirm" class="btn btn-danger">Remover</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        document.getElementById('del-cancel').onclick = () => overlay.remove();
        document.getElementById('del-confirm').onclick = async () => {
            overlay.remove();
            btnElement.disabled = true;
            try {
                const response = await fetch(`${API_BASE}/exams/${examId}`, { method: 'DELETE' });
                if (response.ok) {
                    const card = btnElement.closest('.exam-card');
                    card.style.opacity = '0';
                    setTimeout(() => { card.remove(); loadFolders(); }, 300);
                    showToast('Prova removida com sucesso.', 'success');
                } else {
                    btnElement.disabled = false;
                    showToast('Erro ao remover a prova.', 'error');
                }
            } catch (error) {
                console.error("Failed to delete", error);
                btnElement.disabled = false;
            }
        };
    };

    // ===== EXAM TAKING =====
    async function loadExam(examId) {
        try {
            const response = await fetch(`${API_BASE}/exams/${examId}`);
            const exam = await response.json();
            document.getElementById('exam-title').textContent = exam.title;
            currentExamQuestions = exam.questions;
            currentExamId = examId;
            currentQuestionIndex = 0;
            currentExamAnswers = {};
            flaggedQuestions = new Set();

            if (currentExamQuestions && currentExamQuestions.length > 0) {
                buildNavigationGrid();
                renderCurrentQuestion();
                switchView('view-exam');
                startExamTimer();

                // Restore buttons visibility
                document.getElementById('prev-question').style.display = 'block';
                document.getElementById('next-question').style.display = 'block';
                document.getElementById('question-counter').style.display = 'block';
            } else {
                showToast('Esta prova não possui questões. O scraper pode ter falhado ao interpretar o PDF.', 'warning', 6000);
            }
        } catch (error) {
            console.error("Failed to load exam", error);
            showToast('Erro ao carregar a prova.', 'error');
        }
    }

    // ===== EXAM TIMER =====
    function startExamTimer() {
        stopExamTimer();
        examStartTime = Date.now();
        const timerEl = document.createElement('div');
        timerEl.className = 'exam-timer';
        timerEl.id = 'exam-timer-display';
        timerEl.innerHTML = '<i class="ph ph-timer"></i><span>00:00:00</span>';
        const header = document.querySelector('#view-exam .top-header');
        const existing = document.getElementById('exam-timer-display');
        if (existing) existing.remove();
        header.appendChild(timerEl);

        examTimerInterval = setInterval(() => {
            const elapsed = Math.floor((Date.now() - examStartTime) / 1000);
            const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
            const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
            const s = String(elapsed % 60).padStart(2, '0');
            timerEl.querySelector('span').textContent = `${h}:${m}:${s}`;
        }, 1000);
    }

    function stopExamTimer() {
        if (examTimerInterval) clearInterval(examTimerInterval);
        examTimerInterval = null;
    }

    // ===== NAVIGATION GRID =====
    function buildNavigationGrid() {
        const gridContainer = document.getElementById('exam-navigation-grid');
        gridContainer.innerHTML = '';
        examSubjects = {};
        currentExamQuestions.forEach((q, index) => {
            const subject = q.subject || 'Geral';
            if (!examSubjects[subject]) examSubjects[subject] = [];
            examSubjects[subject].push(index);
        });
        for (const [subject, indexes] of Object.entries(examSubjects)) {
            const groupDiv = document.createElement('div');
            groupDiv.className = 'subject-group';
            const title = document.createElement('div');
            title.className = 'subject-title';
            title.textContent = subject;
            groupDiv.appendChild(title);
            const grid = document.createElement('div');
            grid.className = 'nav-grid';
            indexes.forEach(idx => {
                const btn = document.createElement('button');
                btn.className = 'grid-btn';
                btn.id = `nav-btn-${idx}`;
                btn.textContent = idx + 1;
                btn.onclick = () => { currentQuestionIndex = idx; renderCurrentQuestion(); };
                grid.appendChild(btn);
            });
            groupDiv.appendChild(grid);
            gridContainer.appendChild(groupDiv);
        }
        document.getElementById('finish-exam-sidebar-btn').onclick = finishExam;
    }

    // ===== RENDER QUESTION =====
    function renderCurrentQuestion() {
        const q = currentExamQuestions[currentQuestionIndex];
        const container = document.getElementById('question-container');
        document.getElementById('current-subject-badge').textContent = q.subject || 'Geral';

        const givenAnswer = currentExamAnswers[currentQuestionIndex];
        const isImmediate = document.getElementById('immediate-feedback-toggle').checked;
        const alreadyAnswered = givenAnswer !== undefined;
        const isFlagged = flaggedQuestions.has(currentQuestionIndex);

        let optionsHtml = '';
        if (q.options) {
            const opts = Object.entries(q.options);
            optionsHtml = `<div class="options-list">`;
            opts.forEach(([key, text]) => {
                if (text === null || text === "null" || String(text).trim() === "") return;
                let btnStyle = '';
                let btnClass = '';
                if (alreadyAnswered) {
                    if (isImmediate) {
                        if (key === q.correct_answer) {
                            btnClass = 'feedback-correct';
                            btnStyle = 'background-color: rgba(16, 185, 129, 0.1); border-color: var(--success-color);';
                        } else if (givenAnswer === key) {
                            btnClass = 'feedback-wrong';
                            btnStyle = 'background-color: rgba(239, 68, 68, 0.1); border-color: var(--danger-color); opacity: 0.7;';
                        }
                    } else if (givenAnswer === key) {
                        btnStyle = 'background-color: var(--primary-color); color: white;';
                    }
                }
                optionsHtml += `
                    <button class="btn btn-option ${btnClass}" onclick="window.answerQuestion('${key}')" style="${btnStyle}" ${alreadyAnswered && isImmediate ? 'disabled' : ''}>
                        <strong>${key})</strong> ${text}
                    </button>
                `;
            });
            optionsHtml += `</div>`;
        } else {
            let styleCerto = '', styleErrado = '';
            if (alreadyAnswered) {
                if (isImmediate) {
                    if (q.correct_answer === 'Certo') {
                        styleCerto = 'background-color: rgba(16, 185, 129, 0.1); border-color: var(--success-color); color: var(--success-color);';
                        if (givenAnswer === 'Errado') styleErrado = 'background-color: rgba(239, 68, 68, 0.1); border-color: var(--danger-color); color: var(--danger-color); opacity: 0.7;';
                    } else {
                        styleErrado = 'background-color: rgba(16, 185, 129, 0.1); border-color: var(--success-color); color: var(--success-color);';
                        if (givenAnswer === 'Certo') styleCerto = 'background-color: rgba(239, 68, 68, 0.1); border-color: var(--danger-color); color: var(--danger-color); opacity: 0.7;';
                    }
                } else {
                    if (givenAnswer === 'Certo') styleCerto = 'background-color: #059669; color: white;';
                    if (givenAnswer === 'Errado') styleErrado = 'background-color: #dc2626; color: white;';
                }
            }
            optionsHtml = `
                <div class="answer-btns">
                    <button class="btn btn-success btn-option" onclick="window.answerQuestion('Certo')" style="${styleCerto}" ${alreadyAnswered && isImmediate ? 'disabled' : ''}><i class="ph ph-check"></i> Certo</button>
                    <button class="btn btn-danger btn-option" onclick="window.answerQuestion('Errado')" style="${styleErrado}" ${alreadyAnswered && isImmediate ? 'disabled' : ''}><i class="ph ph-x"></i> Errado</button>
                </div>
            `;
        }
        let recurrenceBadge = '';
        if (q.error_count > 1) {
            recurrenceBadge = `
                <div style="background: rgba(239, 68, 68, 0.1); color: var(--danger-color); padding: 8px 12px; border-radius: 8px; font-size: 0.85rem; font-weight: 500; margin-bottom: 16px; border-left: 3px solid var(--danger-color); display: inline-flex; align-items: center; gap: 8px;">
                    <i class="ph ph-warning-circle" style="font-size: 1.1rem;"></i>
                    Atenção: Você já errou essa questão ${q.error_count} vezes!
                </div>
            `;
        }

        let imagesHtml = '';
        if (q.images && q.images.length > 0) {
            imagesHtml = '<div style="margin-bottom: 24px; text-align: center;">';
            q.images.forEach(img => {
                imagesHtml += `<img src="${img}" style="max-width: 100%; border-radius: 8px; border: 1px solid var(--border-color); margin-bottom: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);" alt="Imagem da questão">`;
            });
            imagesHtml += '</div>';
        }

        container.innerHTML = `
            <div class="fade-in" style="width: 100%;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                    <span style="font-size: 0.85rem; color: var(--text-secondary);">Questão ${currentQuestionIndex + 1}</span>
                    <button class="btn-flag ${isFlagged ? 'flagged' : ''}" onclick="window.toggleFlag(${currentQuestionIndex})">
                        <i class="ph ${isFlagged ? 'ph-flag-fill' : 'ph-flag'}"></i> ${isFlagged ? 'Marcada' : 'Revisar'}
                    </button>
                </div>
                ${recurrenceBadge}
                <div style="margin-bottom: 24px; font-size: 1.1rem; line-height: 1.6;">
                    ${(() => {
                        const txt = q.statement || '';
                        let paragraphs = [];
                        if (txt.includes('\\n') || txt.includes('\n')) {
                            paragraphs = txt.split(/\\n|\n/).filter(p => p.trim() !== '');
                        } else {
                            // Separação artificial por regex: Ponto final seguido de espaço e letra Maiúscula.
                            let marked = txt.replace(/([a-z\)]\.)\s+([A-Z])/g, "$1|SPLIT|$2");
                            let sentences = marked.split('|SPLIT|');
                            let temp = [];
                            for (let i = 0; i < sentences.length; i++) {
                                temp.push(sentences[i]);
                                if (temp.length >= 2 || i === sentences.length - 1) {
                                    paragraphs.push(temp.join(' '));
                                    temp = [];
                                }
                            }
                        }
                        
                        let html = '';
                        let imageInserted = false;
                        const hasImages = q.images && q.images.length > 0;
                        
                        for (let i = 0; i < paragraphs.length; i++) {
                            html += `<p style="margin-bottom: 16px;">${paragraphs[i]}</p>`;
                            
                            if (hasImages && !imageInserted) {
                                let pLower = paragraphs[i].toLowerCase();
                                if (pLower.includes("texto seguinte") || 
                                    pLower.includes("texto abaixo") || 
                                    pLower.includes("leia o texto") ||
                                    pLower.includes("figura") ||
                                    pLower.includes("quadro") ||
                                    pLower.includes("charge") ||
                                    pLower.includes("tira") ||
                                    pLower.includes("analise")) {
                                    html += imagesHtml;
                                    imageInserted = true;
                                }
                            }
                        }
                        
                        if (hasImages && !imageInserted) {
                            // Default to top if no trigger words matched
                            html = imagesHtml + html;
                        }
                        
                        return html;
                    })()}
                </div>
                ${optionsHtml}
            </div>
        `;

        const total = currentExamQuestions.length;
        document.getElementById('question-counter').textContent = `${currentQuestionIndex + 1} / ${total}`;
        const pct = ((currentQuestionIndex + 1) / total) * 100;
        const progressFill = document.getElementById('exam-progress-fill');
        if (progressFill) progressFill.style.width = pct + '%';

        // Update Nav Grid UI
        document.querySelectorAll('.grid-btn').forEach(btn => btn.classList.remove('active'));
        const activeBtn = document.getElementById(`nav-btn-${currentQuestionIndex}`);
        if (activeBtn) activeBtn.classList.add('active');

        const btnPrev = document.getElementById('prev-question');
        const btnNext = document.getElementById('next-question');
        btnPrev.disabled = currentQuestionIndex === 0;

        if (currentQuestionIndex === currentExamQuestions.length - 1) {
            btnNext.textContent = 'Finalizar';
            btnNext.className = 'btn btn-primary';
            btnNext.onclick = finishExam;
        } else {
            btnNext.textContent = 'Próxima';
            btnNext.className = 'btn btn-secondary';
            btnNext.onclick = () => { currentQuestionIndex++; renderCurrentQuestion(); };
        }
        btnPrev.onclick = () => { currentQuestionIndex--; renderCurrentQuestion(); };
    }

    // ===== FLAG FOR REVIEW =====
    window.toggleFlag = function (idx) {
        if (flaggedQuestions.has(idx)) flaggedQuestions.delete(idx);
        else flaggedQuestions.add(idx);
        renderCurrentQuestion();
        const gridBtn = document.getElementById(`nav-btn-${idx}`);
        if (gridBtn) gridBtn.classList.toggle('flagged', flaggedQuestions.has(idx));
    };

    // ===== ANSWER QUESTION =====
    window.answerQuestion = function (answer) {
        currentExamAnswers[currentQuestionIndex] = answer;
        renderCurrentQuestion();
        const isImmediate = document.getElementById('immediate-feedback-toggle').checked;
        const q = currentExamQuestions[currentQuestionIndex];
        const gridBtn = document.getElementById(`nav-btn-${currentQuestionIndex}`);
        if (gridBtn) {
            gridBtn.classList.remove('answered', 'correct', 'wrong');
            if (isImmediate) {
                gridBtn.classList.add(answer === q.correct_answer ? 'correct' : 'wrong');
            } else {
                gridBtn.classList.add('answered');
            }
        }
        const isLast = currentQuestionIndex === currentExamQuestions.length - 1;
        if (!isLast && !isImmediate) {
            setTimeout(() => { currentQuestionIndex++; renderCurrentQuestion(); }, 800);
        }
    };

    // ===== KEYBOARD SHORTCUTS =====
    document.addEventListener('keydown', (e) => {
        const examView = document.getElementById('view-exam');
        if (!examView || examView.style.display === 'none') return;
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        const q = currentExamQuestions[currentQuestionIndex];
        if (!q) return;

        // Arrow keys
        if (e.key === 'ArrowRight' && currentQuestionIndex < currentExamQuestions.length - 1) {
            e.preventDefault(); currentQuestionIndex++; renderCurrentQuestion();
        } else if (e.key === 'ArrowLeft' && currentQuestionIndex > 0) {
            e.preventDefault(); currentQuestionIndex--; renderCurrentQuestion();
        }
        // Number keys for options
        else if (q.options && ['1', '2', '3', '4', '5'].includes(e.key)) {
            const opts = Object.keys(q.options);
            const idx = parseInt(e.key) - 1;
            if (idx < opts.length) window.answerQuestion(opts[idx]);
        }
        // Letter keys for options
        else if (q.options && ['a', 'b', 'c', 'd', 'e'].includes(e.key.toLowerCase())) {
            const key = e.key.toUpperCase();
            if (q.options[key]) window.answerQuestion(key);
        }
        // C/E for Certo/Errado
        else if (!q.options && e.key.toLowerCase() === 'c') window.answerQuestion('Certo');
        else if (!q.options && e.key.toLowerCase() === 'e') window.answerQuestion('Errado');
        // F for flag
        else if (e.key.toLowerCase() === 'f') window.toggleFlag(currentQuestionIndex);
        // Z for Zen mode
        else if (e.key.toLowerCase() === 'z' && !e.ctrlKey && !e.altKey) toggleZenMode();
        // ? for shortcuts help
        else if (e.key === '?') showShortcutsHelp();
    });

    function showShortcutsHelp() {
        const overlay = document.createElement('div');
        overlay.className = 'shortcuts-overlay';
        overlay.innerHTML = `
            <div class="shortcuts-card">
                <h3><i class="ph ph-keyboard"></i> Atalhos de Teclado</h3>
                <div class="shortcut-row"><span>Selecionar alternativa</span><span class="shortcut-key">1-5</span> ou <span class="shortcut-key">A-E</span></div>
                <div class="shortcut-row"><span>Questão anterior</span><span class="shortcut-key">←</span></div>
                <div class="shortcut-row"><span>Próxima questão</span><span class="shortcut-key">→</span></div>
                <div class="shortcut-row"><span>Marcar para revisão</span><span class="shortcut-key">F</span></div>
                <div class="shortcut-row"><span>Certo / Errado</span><span class="shortcut-key">C</span> / <span class="shortcut-key">E</span></div>
                <div class="shortcut-row"><span>Modo Zen</span><span class="shortcut-key">Z</span></div>
                <div class="shortcut-row"><span>Sair do Modo Zen</span><span class="shortcut-key">ESC</span></div>
                <div class="shortcut-row"><span>Mostrar atalhos</span><span class="shortcut-key">?</span></div>
                <button class="btn btn-primary" style="width: 100%; margin-top: 20px; justify-content: center;" onclick="this.closest('.shortcuts-overlay').remove()">Fechar</button>
            </div>
        `;
        document.body.appendChild(overlay);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    }

    // ===== FINISH EXAM =====
    function finishExam() {
        const overlay = document.createElement('div');
        overlay.style.cssText = `position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 9999; display: flex; align-items: center; justify-content: center;`;
        const unanswered = currentExamQuestions.length - Object.keys(currentExamAnswers).length;
        overlay.innerHTML = `
            <div style="background: var(--bg-card, #1e2235); border: 1px solid var(--border-color, #333); border-radius: 16px; padding: 32px; max-width: 420px; width: 90%; text-align: center;">
                <h3 style="margin-bottom: 12px; font-size: 1.2rem;">Finalizar Prova?</h3>
                <p style="color: var(--text-muted, #aaa); margin-bottom: 24px;">
                    ${unanswered > 0 ? `Você tem <strong style="color: #f59e0b;">${unanswered} questão(ões)</strong> sem resposta.` : 'Todas as questões foram respondidas!'}
                </p>
                <div style="display: flex; gap: 12px; justify-content: center;">
                    <button id="modal-cancel" class="btn btn-secondary">Revisar</button>
                    <button id="modal-confirm" class="btn btn-primary">Finalizar</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        document.getElementById('modal-cancel').onclick = () => overlay.remove();
        document.getElementById('modal-confirm').onclick = () => { overlay.remove(); _doFinishExam(); };
    }

    function _doFinishExam() {
        stopExamTimer();
        let correctCount = 0;
        const subjectStats = {};

        currentExamQuestions.forEach((q, index) => {
            const given = currentExamAnswers[index] || 'N/A';
            const correct = q.correct_answer || 'N/A';
            const isCorrect = given.trim().toUpperCase() === correct.trim().toUpperCase();
            if (isCorrect) correctCount++;

            const subj = q.subject || 'Geral';
            if (!subjectStats[subj]) subjectStats[subj] = { correct: 0, total: 0 };
            subjectStats[subj].total++;
            if (isCorrect) subjectStats[subj].correct++;
        });

        const totalQ = currentExamQuestions.length;
        const pctTotal = Math.round((correctCount / totalQ) * 100);

        // Elapsed time
        let elapsedSeconds = 0;
        let elapsedStr = '';
        if (examStartTime) {
            elapsedSeconds = Math.floor((Date.now() - examStartTime) / 1000);
            const h = Math.floor(elapsedSeconds / 3600);
            const m = Math.floor((elapsedSeconds % 3600) / 60);
            const s = elapsedSeconds % 60;
            elapsedStr = `${h > 0 ? h + 'h ' : ''}${m}m ${s}s`;
        }

        // Submit score to backend
        if (currentExamId) {
            fetch(`${API_BASE}/exams/${currentExamId}/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    score: correctCount,
                    total: totalQ,
                    percentage: pctTotal,
                    elapsed_seconds: elapsedSeconds,
                    answers: currentExamAnswers
                })
            }).catch(e => console.error('Erro ao salvar score:', e));
        }

        // Performance chart
        let chartHtml = '<div class="perf-chart">';
        for (const [subj, stats] of Object.entries(subjectStats)) {
            const pct = Math.round((stats.correct / stats.total) * 100);
            const cls = pct >= 70 ? 'good' : pct >= 40 ? 'mid' : 'bad';
            chartHtml += `
                <div class="perf-bar-row">
                    <div class="perf-label">${subj} (${stats.correct}/${stats.total})</div>
                    <div class="perf-bar-bg">
                        <div class="perf-bar-fill ${cls}" style="width: ${pct}%;">${pct}%</div>
                    </div>
                </div>
            `;
        }
        chartHtml += '</div>';

        // Result cards
        let cardsHtml = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; width: 100%;">';
        currentExamQuestions.forEach((q, index) => {
            const given = currentExamAnswers[index] || 'N/A';
            const correct = q.correct_answer || 'N/A';
            const isCorrect = given.trim().toUpperCase() === correct.trim().toUpperCase();
            const cardStyle = isCorrect ? 'background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.3);' : 'background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.3);';
            cardsHtml += `
                <div style="padding: 20px; border-radius: 12px; ${cardStyle} display: flex; flex-direction: column; transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='translateY(0)'">
                    <h4 style="font-weight: 700; margin-bottom: 12px; color: var(--text-primary); font-size: 1.1rem;">Questão ${index + 1}</h4>
                    <p style="font-size: 0.9rem; margin-bottom: 16px; color: var(--text-secondary); line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;">${q.statement}</p>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.95rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 12px; margin-top: auto;">
                        <span style="color: ${isCorrect ? 'var(--success-color)' : 'var(--danger-color)'}">Sua: <strong>${given}</strong></span>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="color: var(--success-color)">Correta: <strong>${correct}</strong></span>
                            ${!isCorrect ? `<button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.8rem; background: rgba(59, 130, 246, 0.1); color: var(--primary-color); border: 1px solid rgba(59, 130, 246, 0.3);" onclick="window.explainWithAI(${q.id}, '${given.replace(/'/g, "\\'")}')"><i class="ph ph-chalkboard-teacher"></i> IA</button>` : ''}
                        </div>
                    </div>
                </div>
            `;
        });
        cardsHtml += '</div>';

        // Check for wrong answers to offer retry
        const wrongIndexes = currentExamQuestions.map((q, i) => {
            const given = currentExamAnswers[i] || 'N/A';
            return given.trim().toUpperCase() !== (q.correct_answer || '').trim().toUpperCase() ? i : null;
        }).filter(i => i !== null);

        const retryBtn = wrongIndexes.length > 0 ? `<button class="btn btn-danger" onclick="window.retryWrongQuestions()" style="display: inline-flex; width: auto; margin: 0 8px;"><i class="ph ph-arrow-counter-clockwise"></i> Refazer ${wrongIndexes.length} Errada(s)</button>` : '';

        const resultHtml = `
            <div style="display: flex; flex-direction: column; width: 100%; gap: 16px;">
                <div class="fade-in" style="width: 100%; text-align: center; margin-bottom: 16px;">
                    <h2 style="font-size: 2.5rem; color: var(--primary-color); margin-bottom: 8px;">${correctCount} / ${totalQ}</h2>
                    <p style="color: var(--text-muted);">Questões corretas (${pctTotal}%)</p>
                    ${elapsedStr ? `<p style="color: var(--text-secondary); font-size: 0.85rem; margin-top: 4px;"><i class="ph ph-timer"></i> Tempo: ${elapsedStr}</p>` : ''}
                </div>
                ${chartHtml}
                <div class="fade-in" style="width: 100%; margin-top: 24px;"><h2 style="margin-bottom: 16px; text-align: center; color: var(--primary-color);">Gabarito da Prova</h2></div>
                ${cardsHtml}
                <div style="text-align: center; margin-top: 16px;">
                    <button class="btn btn-primary" onclick="document.getElementById('back-to-folder-btn').click();" style="display: inline-flex; width: auto; margin: 0 8px;"><i class="ph ph-folder"></i> Voltar para a Pasta</button>
                    ${retryBtn}
                </div>
            </div>
        `;

        document.getElementById('question-container').innerHTML = resultHtml;
        document.getElementById('prev-question').style.display = 'none';
        document.getElementById('next-question').style.display = 'none';
        document.getElementById('question-counter').style.display = 'none';
        const timerDisplay = document.getElementById('exam-timer-display');
        if (timerDisplay) timerDisplay.remove();
    }

    window.explainWithAI = async function (questionId, userAnswer) {
        showToast('Professor IA está analisando a questão...', 'info');

        try {
            const response = await fetch(`${API_BASE}/explain/${questionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_answer: userAnswer })
            });
            const data = await response.json();

            if (!response.ok) throw new Error(data.error || 'Erro na IA');

            // Show modal
            const overlay = document.createElement('div');
            overlay.style.cssText = `position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 9999; display: flex; align-items: center; justify-content: center;`;
            overlay.innerHTML = `
                <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 32px; max-width: 600px; width: 90%; max-height: 80vh; display: flex; flex-direction: column;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                        <h3 style="font-size: 1.3rem; color: var(--primary-color); display: flex; align-items: center; gap: 8px;"><i class="ph ph-chalkboard-teacher"></i> Professor IA</h3>
                        <button class="btn btn-ghost" id="ai-modal-close" style="padding: 8px;"><i class="ph ph-x"></i></button>
                    </div>
                    <div style="overflow-y: auto; color: var(--text-primary); font-size: 0.95rem; line-height: 1.7; padding-right: 12px; white-space: pre-wrap;">${data.explanation}</div>
                </div>
            `;
            document.body.appendChild(overlay);
            document.getElementById('ai-modal-close').onclick = () => overlay.remove();
        } catch (error) {
            console.error("AI Explain failed", error);
            showToast('Erro ao gerar explicação com IA.', 'error');
        }
    };

    window.loadErrorStats = async function () {
        const container = document.getElementById('error-stats-container');
        if (!container) return;

        try {
            const res = await fetch(`${API_BASE}/notebook/stats`);
            const stats = await res.json();

            if (!stats || stats.length === 0) {
                container.innerHTML = `
                    <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-muted);">
                        <i class="ph ph-check-circle" style="font-size: 3rem; color: var(--success-color); margin-bottom: 16px;"></i>
                        <h3 style="margin-bottom: 8px;">Parabéns!</h3>
                        <p>Você não possui erros registrados no momento. Continue estudando!</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = stats.map(s => `
                <div class="card stat-card" style="padding: 20px; border-left: 4px solid var(--danger-color); cursor: pointer; transition: transform 0.2s ease, box-shadow 0.2s ease;"
                     onclick="window.startErrorNotebook('${s.subject}')"
                     onmouseover="this.style.transform='translateY(-4px)'; this.style.boxShadow='0 8px 16px rgba(0,0,0,0.1)'"
                     onmouseout="this.style.transform='none'; this.style.boxShadow='var(--shadow)'">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                        <h3 style="font-size: 1.1rem; margin: 0; color: var(--text-primary);">${s.subject}</h3>
                        <span style="background: rgba(239, 68, 68, 0.1); color: var(--danger-color); padding: 4px 10px; border-radius: 20px; font-weight: 600; font-size: 0.9rem;">
                            ${s.count} Erro${s.count !== 1 ? 's' : ''}
                        </span>
                    </div>
                    <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 16px;">
                        Clique para gerar um caderno focado nesta matéria.
                    </p>
                    <div style="display: flex; align-items: center; color: var(--primary-color); font-weight: 500; font-size: 0.9rem;">
                        <span>Resolver Caderno</span>
                        <i class="ph ph-arrow-right" style="margin-left: 6px;"></i>
                    </div>
                </div>
            `).join('');

        } catch (e) {
            console.error(e);
            container.innerHTML = `<div style="grid-column: 1 / -1; color: var(--danger-color); padding: 20px;">Erro ao carregar estatísticas.</div>`;
        }
    };

    window.startErrorNotebook = async function (subject = null) {
        showToast('Carregando Caderno de Erros...', 'info');
        try {
            const url = subject ? `${API_BASE}/notebook?subject=${encodeURIComponent(subject)}` : `${API_BASE}/notebook`;
            const res = await fetch(url);
            const data = await res.json();
            if (!data.questions || data.questions.length === 0) {
                showToast('Seu caderno de erros está vazio para este filtro!', 'info');
                return;
            }
            openExamDirectly(data);
        } catch (e) {
            console.error(e);
            showToast('Erro ao carregar caderno de erros.', 'error');
        }
    };

    window.generateCustomExam = async function () {
        showToast('Gerando simulado...', 'info');
        try {
            const res = await fetch(`${API_BASE}/generate_exam`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ count: 20 })
            });
            const data = await res.json();
            if (!data.questions || data.questions.length === 0) {
                showToast('Não há questões suficientes no banco.', 'error');
                return;
            }
            openExamDirectly(data);
        } catch (e) {
            console.error(e);
            showToast('Erro ao gerar simulado.', 'error');
        }
    };

    function openExamDirectly(examData) {
        currentExamId = examData.id;
        currentExamQuestions = examData.questions;
        currentQuestionIndex = 0;
        currentExamAnswers = {};
        flaggedQuestions = new Set();

        document.getElementById('exam-title').textContent = examData.title;
        document.querySelectorAll('.view-section').forEach(el => el.style.display = 'none');
        document.getElementById('view-exam').style.display = 'block';

        const qContainer = document.getElementById('question-container');
        if (!qContainer) {
            // Need to reconstruct exam view if it was destroyed by finish exam
            const container = document.getElementById('exam-navigation-grid').parentElement;
            container.innerHTML = `
                <div id="question-counter" style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 16px; font-weight: 500;"></div>
                <div id="question-container" class="question-card fade-in"></div>
                <div style="display: flex; gap: 12px; margin-top: 24px; justify-content: space-between; align-items: center;">
                    <button id="prev-question" class="btn btn-secondary"><i class="ph ph-arrow-left"></i> Anterior</button>
                    <button id="flag-question" class="btn btn-ghost" style="color: #f59e0b;"><i class="ph ph-flag"></i> Marcar para Revisão</button>
                    <button id="next-question" class="btn btn-primary">Próxima <i class="ph ph-arrow-right"></i></button>
                </div>
            `;
            document.getElementById('prev-question').addEventListener('click', () => {
                if (currentQuestionIndex > 0) {
                    currentQuestionIndex--;
                    renderCurrentQuestion();
                }
            });
            document.getElementById('next-question').addEventListener('click', () => {
                if (currentQuestionIndex < currentExamQuestions.length - 1) {
                    currentQuestionIndex++;
                    renderCurrentQuestion();
                }
            });
            document.getElementById('flag-question').addEventListener('click', () => {
                if (flaggedQuestions.has(currentQuestionIndex)) {
                    flaggedQuestions.delete(currentQuestionIndex);
                } else {
                    flaggedQuestions.add(currentQuestionIndex);
                }
                renderCurrentQuestion();
                const gridBtn = document.getElementById(`nav-btn-${currentQuestionIndex}`);
                if (gridBtn) gridBtn.classList.toggle('flagged', flaggedQuestions.has(currentQuestionIndex));
            });
        } else {
            document.getElementById('prev-question').style.display = 'block';
            document.getElementById('next-question').style.display = 'block';
            document.getElementById('question-counter').style.display = 'block';
        }

        buildNavigationGrid();
        renderCurrentQuestion();
        startExamTimer();
    }

    // ===== RETRY WRONG QUESTIONS =====
    window.retryWrongQuestions = function () {
        const wrongIndexes = currentExamQuestions.map((q, i) => {
            const given = currentExamAnswers[i] || 'N/A';
            return given.trim().toUpperCase() !== (q.correct_answer || '').trim().toUpperCase() ? i : null;
        }).filter(i => i !== null);

        const wrongQuestions = wrongIndexes.map(i => currentExamQuestions[i]);
        currentExamQuestions = wrongQuestions;
        currentQuestionIndex = 0;
        currentExamAnswers = {};
        flaggedQuestions = new Set();

        document.getElementById('prev-question').style.display = 'block';
        document.getElementById('next-question').style.display = 'block';
        document.getElementById('question-counter').style.display = 'block';

        buildNavigationGrid();
        renderCurrentQuestion();
        startExamTimer();
        showToast(`Refazendo ${wrongQuestions.length} questão(ões) errada(s).`, 'info');
    };

    // ===== PCI MANUAL HANDLING =====
    const pciManualModal = document.getElementById('pci-manual-modal');
    const pciManualClose = document.getElementById('pci-manual-close');
    const pciManualLink = document.getElementById('pci-manual-link');
    const pciManualInput = document.getElementById('pci-manual-input');
    const btnSubmitPciManual = document.getElementById('btn-submit-pci-manual');
    let currentPciExamId = null;
    let currentPciCard = null;

    window.openPciManualModal = function (examId, url, cardElement) {
        currentPciExamId = examId;
        currentPciCard = cardElement;
        pciManualLink.href = url;
        pciManualInput.value = '';
        pciManualModal.style.display = 'flex';
    };

    if (pciManualClose) {
        pciManualClose.addEventListener('click', () => { pciManualModal.style.display = 'none'; });
    }

    if (btnSubmitPciManual) {
        btnSubmitPciManual.onclick = async () => {
            const pdfUrl = document.getElementById('pci-manual-input').value.trim();
            
            if (!pdfUrl) {
                showToast('Cole o link do PDF.', 'warning');
                return;
            }
            
            btnSubmitPciManual.disabled = true;
            btnSubmitPciManual.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Processando...';
            
            try {
                const formData = new FormData();
                if (pdfUrl) formData.append('pdf_url', pdfUrl);

                const res = await fetch(`${API_BASE}/exams/${currentPciExamId}/manual_pdf`, {
                    method: 'POST',
                    body: formData
                });
                
                const data = await res.json();
                if (!res.ok) {
                    showToast('Erro: ' + (data.error || 'Falha ao baixar o PDF.'), 'error', 6000);
                    btnSubmitPciManual.disabled = false;
                    btnSubmitPciManual.innerHTML = 'Baixar e Processar Prova';
                    return;
                }
                pciManualModal.style.display = 'none';
                btnSubmitPciManual.disabled = false;
                btnSubmitPciManual.innerHTML = 'Baixar e Processar Prova';
                if (currentPciCard) {
                    currentPciCard.style.opacity = '0';
                    currentPciCard.style.transform = 'scale(0.9)';
                    setTimeout(() => {
                        currentPciCard.remove();
                        if (searchResults && searchResults.children.length === 0) {
                            searchResults.innerHTML = '<div class="empty-state"><i class="ph ph-check-circle"></i><p>Triagem concluída!</p></div>';
                        }
                    }, 300);
                }
                showToast('Download concluído! A prova está sendo processada e aparecerá na pasta em breve.', 'success', 5000);
            } catch (error) {
                console.error(error);
                showToast('Erro de comunicação com o servidor.', 'error');
                btnSubmitPciManual.disabled = false;
                btnSubmitPciManual.innerHTML = 'Baixar e Processar Prova';
            }
        };
    }

    // ===== ZEN MODE =====
    let isZenMode = false;
    let zenTimerInterval = null;
    let zenSeconds = 0;

    function initZenMode() {
        const btn = document.getElementById('zen-mode-btn');
        if (btn) {
            btn.addEventListener('click', toggleZenMode);
        }

        // ESC to exit zen mode
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && isZenMode) {
                toggleZenMode();
            }
        });
    }

    function toggleZenMode() {
        isZenMode = !isZenMode;
        if (isZenMode) {
            document.body.classList.add('zen-mode');

            // Show hint
            const hint = document.createElement('div');
            hint.className = 'zen-hint';
            hint.innerHTML = '<i class="ph ph-info"></i> Pressione ESC para sair do Modo Zen';
            document.body.appendChild(hint);
            setTimeout(() => hint.remove(), 4500);

            // Add Timer & Counter
            const timer = document.createElement('div');
            timer.className = 'zen-timer';
            timer.id = 'zen-timer';
            timer.innerHTML = '<i class="ph ph-clock"></i> <span>00:00</span>';
            document.body.appendChild(timer);

            const counter = document.createElement('div');
            counter.className = 'zen-counter';
            counter.id = 'zen-counter';
            if (currentExamQuestions) {
                counter.textContent = `${currentQuestionIndex + 1} / ${currentExamQuestions.length}`;
            }
            document.body.appendChild(counter);

            zenSeconds = 0;
            zenTimerInterval = setInterval(() => {
                zenSeconds++;
                const m = String(Math.floor(zenSeconds / 60)).padStart(2, '0');
                const s = String(zenSeconds % 60).padStart(2, '0');
                const span = timer.querySelector('span');
                if (span) span.textContent = `${m}:${s}`;
            }, 1000);
        } else {
            document.body.classList.remove('zen-mode');
            const hint = document.querySelector('.zen-hint');
            if (hint) hint.remove();
            const timer = document.getElementById('zen-timer');
            if (timer) timer.remove();
            const counter = document.getElementById('zen-counter');
            if (counter) counter.remove();
            if (zenTimerInterval) clearInterval(zenTimerInterval);
        }
    }

    // Override renderCurrentQuestion to also update zen counter
    const _originalRenderQuestion = renderCurrentQuestion;
    renderCurrentQuestion = function () {
        _originalRenderQuestion();
        const zenCounter = document.getElementById('zen-counter');
        if (zenCounter && isZenMode && currentExamQuestions) {
            zenCounter.textContent = `${currentQuestionIndex + 1} / ${currentExamQuestions.length}`;
        }
    };

    initZenMode();

    // ===== GLOBAL DOWNLOAD LIST =====
    let globalDownloadsInterval = null;
    let globalActiveDownloads = 0;

    function initGlobalDownloads() {
        const btn = document.getElementById('global-download-btn');
        if (btn) btn.addEventListener('click', () => switchView('view-downloads'));

        if (globalDownloadsInterval) clearInterval(globalDownloadsInterval);
        globalDownloadsInterval = setInterval(pollGlobalDownloads, 2000);
        pollGlobalDownloads();
    }

    async function pollGlobalDownloads() {
        try {
            const res = await fetch(`/api/downloads`);
            if (res.ok) {
                const data = await res.json();
                const downloads = data;

                globalActiveDownloads = downloads.filter(d => d.progress >= 0 && d.progress < 100).length;

                const btn = document.getElementById('global-download-btn');
                const badge = document.getElementById('global-download-badge');
                if (btn && badge) {
                    // Botão sempre visível
                    btn.style.display = 'flex';

                    if (globalActiveDownloads > 0) {
                        badge.style.display = 'flex';
                        badge.textContent = globalActiveDownloads;
                    } else {
                        badge.style.display = 'none';
                    }
                }

                if (document.getElementById('view-downloads').style.display !== 'none') {
                    renderDownloadsViewData(downloads);
                }
            }
        } catch (e) {
            console.error('Error polling downloads:', e);
        }
    }

    function renderDownloadsViewData(downloads) {
        const container = document.getElementById('downloads-list');
        if (!container) return;

        if (downloads.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="ph ph-cloud-check"></i>
                    <p>Nenhum download ativo no momento.</p>
                </div>`;
            return;
        }

        container.innerHTML = downloads.map(d => {
            const isError = d.progress === -1;
            const isDone = d.progress === 100;
            const statusClass = isError ? 'status-error' : isDone ? 'status-done' : 'status-running';
            const statusIcon = isError ? 'ph-warning' : isDone ? 'ph-check-circle' : 'ph-spinner ph-spin';
            const pctText = isError ? 'Erro' : isDone ? 'OK' : d.progress + '%';

            const barWidth = isError ? 100 : (d.progress < 0 ? 0 : d.progress);
            const barColor = isError ? 'var(--danger-color)' : isDone ? 'var(--success-color)' : 'var(--primary-color)';

            return `
            <div class="download-card">
                <div class="download-card-header" style="align-items: flex-start;">
                    <div style="flex: 1; min-width: 0; padding-right: 12px;">
                        <h3 class="download-card-title">${d.title}</h3>
                        ${d.url ? `<div style="font-size: 0.75rem; color: var(--text-secondary); word-break: break-all; margin-top: 4px;" title="${d.url}">${d.url}</div>` : ''}
                    </div>
                    <span class="download-card-status ${statusClass}" style="flex-shrink: 0;"><i class="ph ${statusIcon}"></i> ${pctText}</span>
                </div>
                <div class="download-progress-container">
                    <div class="download-progress-bar" style="width: ${barWidth}%; background: ${barColor}"></div>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-secondary);">
                    <span>${d.status}</span>
                    ${isError && d.error_type ? `<span class="download-error-msg" style="display:block">Motivo: ${d.error_type}</span>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    initGlobalDownloads();
});
