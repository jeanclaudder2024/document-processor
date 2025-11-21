// Document Processor CMS - Clean Frontend
class DocumentCMS {
    constructor() {
        const origin = window.location.origin || '';
        const hostname = window.location.hostname || '';
        let apiBase = 'http://localhost:8000';

        if (window.__CMS_API_BASE__) {
            apiBase = window.__CMS_API_BASE__;
        } else if (hostname === 'localhost' || hostname === '127.0.0.1') {
            apiBase = 'http://localhost:8000';
        } else if (hostname === 'control.petrodealhub.com') {
            apiBase = 'https://petrodealhub.com/api';
        } else if (origin && origin.startsWith('http')) {
            apiBase = `${origin.replace(/\/$/, '')}/api`;
        }

        this.apiBaseUrl = apiBase;
        this.selectedFile = null;
        this.selectedCSV = null;
        this.templates = [];
        this.allTemplates = [];
        this.activeTemplateMetadata = null;
        this.isLoggedIn = false;
        this.dataInitialized = false;
        this.loginInProgress = false;
        this.init();
    }

    normalizeTemplateName(name) {
        if (!name) return '';
        const value = String(name).trim().toLowerCase();
        return value.endsWith('.docx') ? value : `${value}.docx`;
    }

    bindAuthEvents() {
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (event) => {
                event.preventDefault();
                this.handleLoginSubmit();
            });
        }

        const loginBtn = document.getElementById('loginBtn');
        if (loginBtn) {
            loginBtn.addEventListener('click', () => {
                this.showLoginOverlay();
                const usernameInput = document.getElementById('loginUsername');
                if (usernameInput) {
                    setTimeout(() => usernameInput.focus(), 50);
                }
            });
        }

        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.logout());
        }
    }

    showLoginOverlay() {
        const overlay = document.getElementById('loginOverlay');
        if (overlay) {
            overlay.classList.remove('d-none');
        }
        document.body.classList.add('overflow-hidden');
    }

    hideLoginOverlay() {
        const overlay = document.getElementById('loginOverlay');
        if (overlay) {
            overlay.classList.add('d-none');
        }
        document.body.classList.remove('overflow-hidden');
        const passwordInput = document.getElementById('loginPassword');
        if (passwordInput) {
            passwordInput.value = '';
        }
    }

    ensureAuthenticated(showMessage = true) {
        if (this.isLoggedIn) {
            return true;
        }
        if (showMessage) {
            this.showToast('error', 'Login Required', 'Please login to continue');
        }
        this.showLoginOverlay();
        return false;
    }

    bootstrapData(force = false) {
        if (!this.isLoggedIn) return;
        if (this.dataInitialized && !force) return;
        this.loadTemplates();
        this.loadDataSources();
        this.loadPlans().then(() => {
            // After plans are loaded, populate plan checkboxes in upload form
            this.populatePlanCheckboxes();
        });
        this.dataInitialized = true;
    }
    
    populatePlanCheckboxes() {
        const container = document.getElementById('planCheckboxes');
        if (!container) return;
        
        if (!this.allPlans || Object.keys(this.allPlans).length === 0) {
            container.innerHTML = '<div class="text-muted small">No plans available. Plans will be loaded automatically.</div>';
            return;
        }
        
        container.innerHTML = Object.entries(this.allPlans).map(([planId, plan]) => `
            <div class="form-check">
                <input type="checkbox" class="form-check-input" id="plan_${planId}" value="${planId}">
                <label class="form-check-label" for="plan_${planId}">
                    ${plan.name || planId}
                </label>
            </div>
        `).join('');
    }

    findTemplateByName(name) {
        if (!this.templates) return null;
        return this.templates.find(t => t.name === name);
    }

    viewPlaceholders(templateName) {
        const template = this.findTemplateByName(templateName);
        const modalEl = document.getElementById('placeholdersModal');
        const listEl = document.getElementById('placeholderList');
        const titleEl = document.getElementById('placeholderTemplateName');

        if (!modalEl || !listEl || !titleEl) {
            console.warn('Placeholder modal elements missing');
            return;
        }

        const placeholders = template?.placeholders || [];
        titleEl.textContent = template?.metadata?.display_name || template?.title || templateName;

        if (placeholders.length === 0) {
            listEl.innerHTML = '<div class="text-muted small">No placeholders detected in this template.</div>';
        } else {
            listEl.innerHTML = placeholders.map((ph, index) => `
                <div class="d-flex justify-content-between align-items-center border-bottom py-1">
                    <code>${ph}</code>
                    <span class="text-muted small">#${index + 1}</span>
                </div>
            `).join('');
        }

        const modal = new bootstrap.Modal(modalEl);
        modalEl.addEventListener('hidden.bs.modal', () => {
            this.activeTemplateMetadata = null;
        }, { once: true });
        modal.show();
    }

    openMetadataModal(templateName) {
        const template = this.findTemplateByName(templateName);
        if (!template) {
            this.showToast('error', 'Not Found', 'Template metadata could not be loaded');
            return;
        }

        this.activeTemplateMetadata = templateName;
        const meta = template.metadata || {};
        const modalEl = document.getElementById('templateMetaModal');
        const displayInput = document.getElementById('metaDisplayName');
        const descriptionInput = document.getElementById('metaDescription');
        const fontFamilyInput = document.getElementById('metaFontFamily');
        const fontSizeInput = document.getElementById('metaFontSize');

        if (displayInput) displayInput.value = meta.display_name || template.title || template.name;
        if (descriptionInput) descriptionInput.value = meta.description || template.description || '';
        if (fontFamilyInput) fontFamilyInput.value = meta.font_family || '';
        if (fontSizeInput) fontSizeInput.value = meta.font_size || '';
        
        // Set broker membership checkbox
        const requiresBrokerInput = document.getElementById('metaRequiresBroker');
        if (requiresBrokerInput) {
            const requiresBroker = meta.requires_broker_membership || template.requires_broker_membership || false;
            requiresBrokerInput.checked = requiresBroker;
        }

        // Load plan checkboxes for this template (async, will populate when ready)
        this.populateMetaPlanCheckboxes(template).catch(err => {
            console.error('[openMetadataModal] ❌ Error populating plan checkboxes:', err);
        });

        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    }

    async populateMetaPlanCheckboxes(template) {
        const container = document.getElementById('metaPlanCheckboxes');
        if (!container) return;
        
        // Ensure plans are loaded
        if (!this.allPlans || Object.keys(this.allPlans).length === 0) {
            container.innerHTML = '<div class="text-muted small">Loading plans...</div>';
            // Try to load plans if not loaded
            await this.loadPlans();
            // Recursively call after plans are loaded
            this.populateMetaPlanCheckboxes(template);
            return;
        }
        
        // CRITICAL: Fetch plan_ids from backend for this template
        // planId is plan_tier (basic, professional, etc.) but we need plan_id (UUID)
        // First, try to get plan_ids from template object
        let currentPlanIds = template.plan_ids || template.plan_ids_list || [];
        
        // If not available, try to fetch from backend
        if (!currentPlanIds || currentPlanIds.length === 0) {
            // Try to get plan info for this template from backend
            const templateName = template.name || template.file_name || '';
            if (templateName) {
                console.log('[populateMetaPlanCheckboxes] 🔄 Fetching plan info for template:', templateName);
                try {
                    // Fetch plan info for this template
                    const planInfo = await this.apiJson(`/templates/${encodeURIComponent(templateName)}/plan-info`);
                    if (planInfo && planInfo.success && planInfo.plans) {
                        // Get plan_tiers from plans
                        currentPlanIds = planInfo.plans.map(p => p.plan_tier).filter(t => t);
                        console.log('[populateMetaPlanCheckboxes] ✅ Got plan_tiers from backend:', currentPlanIds);
                    }
                } catch (e) {
                    console.warn('[populateMetaPlanCheckboxes] ⚠️ Could not fetch plan info:', e);
                }
            }
        }
        
        const currentPlanIdsSet = new Set(Array.isArray(currentPlanIds) ? currentPlanIds.map(id => String(id)) : []);
        console.log('[populateMetaPlanCheckboxes] 📋 Current plan IDs:', Array.from(currentPlanIdsSet));
        console.log('[populateMetaPlanCheckboxes] 📋 Available plans:', Object.keys(this.allPlans));
        
        container.innerHTML = Object.entries(this.allPlans).map(([planId, plan]) => {
            // planId is plan_tier (basic, professional, etc.)
            // Check if this plan_tier is in currentPlanIds
            const isChecked = currentPlanIdsSet.has(String(planId)) || currentPlanIdsSet.has(String(plan.plan_tier || planId));
            console.log('[populateMetaPlanCheckboxes] 📋 Plan:', planId, 'isChecked:', isChecked);
            return `
                <div class="form-check">
                    <input type="checkbox" class="form-check-input meta-plan-checkbox" id="meta_plan_${planId}" value="${planId}" ${isChecked ? 'checked' : ''}>
                    <label class="form-check-label" for="meta_plan_${planId}">
                        ${plan.name || plan.plan_name || planId}
                    </label>
                </div>
            `;
        }).join('');
    }

    async saveTemplateMetadata() {
        if (!this.ensureAuthenticated()) return;
        if (!this.activeTemplateMetadata) {
            this.showToast('error', 'Error', 'No template selected');
            return;
        }

        const displayInput = document.getElementById('metaDisplayName');
        const descriptionInput = document.getElementById('metaDescription');
        const fontFamilyInput = document.getElementById('metaFontFamily');
        const fontSizeInput = document.getElementById('metaFontSize');
        const requiresBrokerInput = document.getElementById('metaRequiresBroker');

        // CRITICAL: Query checkboxes from within modal to get correct selection
        const modalElement = document.getElementById('templateMetaModal');
        const planCheckboxes = modalElement ? 
            modalElement.querySelectorAll('#metaPlanCheckboxes input[type="checkbox"]:checked') :
            document.querySelectorAll('#metaPlanCheckboxes input[type="checkbox"]:checked');
        
        const selectedPlanIds = Array.from(planCheckboxes).map(cb => cb.value).filter(v => v);
        
        console.log('[saveTemplateMetadata] 📋 Saving template metadata:', this.activeTemplateMetadata);
        console.log('[saveTemplateMetadata] 📋 Selected plan IDs:', selectedPlanIds);
        console.log('[saveTemplateMetadata] 📋 Requires broker membership:', requiresBrokerInput ? requiresBrokerInput.checked : false);

        const payload = {
            display_name: displayInput ? displayInput.value : '',
            description: descriptionInput ? descriptionInput.value : '',
            font_family: fontFamilyInput ? fontFamilyInput.value : '',
            font_size: fontSizeInput ? fontSizeInput.value : '',
            plan_ids: selectedPlanIds,  // Send plan_ids even if empty (auto-connect if empty)
            requires_broker_membership: requiresBrokerInput ? requiresBrokerInput.checked : false
        };

        try {
            console.log('[saveTemplateMetadata] 💾 Sending payload:', JSON.stringify(payload, null, 2));
            const data = await this.apiJson(`/templates/${encodeURIComponent(this.activeTemplateMetadata)}/metadata`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            
            console.log('[saveTemplateMetadata] ✅ Response:', JSON.stringify(data, null, 2));

            if (data && data.success) {
                console.log('[saveTemplateMetadata] ✅ Metadata saved successfully');
                console.log('[saveTemplateMetadata] ✅ Response plan_ids:', data.plan_ids);
                
                const template = this.findTemplateByName(this.activeTemplateMetadata);
                if (template) {
                    template.metadata = template.metadata || {};
                    Object.assign(template.metadata, data.metadata || {});
                    // Store plan_ids in template object for future reference
                    if (data.plan_ids) {
                        template.plan_ids = data.plan_ids;
                    }
                    if (data.metadata?.display_name) {
                        template.title = data.metadata.display_name;
                    }
                    if (data.metadata?.description) {
                        template.description = data.metadata.description;
                    }
                }

                // Force reload templates and plans to get updated data from backend
                await this.loadTemplates();
                // CRITICAL: Also reload plans to reflect updated template permissions
                // Use setTimeout to ensure data is saved before reloading
                setTimeout(async () => {
                    await this.loadPlans(true);
                    // Also refresh the plans display
                    const plansList = document.getElementById('plansList');
                    if (plansList) {
                        plansList.style.opacity = '0.5';
                        setTimeout(() => {
                            plansList.style.opacity = '1';
                        }, 200);
                    }
                }, 500);
                this.showToast('success', 'Metadata Saved', 'Template details updated successfully. Plans will refresh automatically.');

                const modalEl = document.getElementById('templateMetaModal');
                if (modalEl) {
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }
            } else {
                console.error('[saveTemplateMetadata] ❌ Save failed - no success response:', data);
                this.showToast('error', 'Save Failed', 'Failed to save template metadata');
            }
        } catch (error) {
            this.showToast('error', 'Save Failed', error.message);
        } finally {
            this.activeTemplateMetadata = null;
        }
    }

    init() {
        this.bindAuthEvents();
        this.checkApiStatus();
        this.checkLoginStatus(true).then(isLoggedIn => {
            if (isLoggedIn) {
                this.bootstrapData(true);
            } else {
                this.showLoginOverlay();
            }
        });
    }

    // ========================================================================
    // API Helpers
    // ========================================================================

    async apiFetch(path, options = {}) {
        const opts = {
            ...options,
            credentials: 'include'
        };
        
        // Only set JSON headers if not sending FormData
        if (!(options.body instanceof FormData)) {
            opts.headers = {
                'Content-Type': 'application/json',
                ...options.headers
            };
        } else {
            // For FormData, let browser set Content-Type (including boundary)
            opts.headers = {
                ...options.headers
            };
        }
        
        try {
            const response = await fetch(`${this.apiBaseUrl}${path}`, opts);
            if (response.status === 401) {
                this.handleUnauthorized();
                return null;
            }
            return response;
        } catch (error) {
            this.showToast('error', 'API Error', `Failed to connect: ${error.message}`);
            return null;
        }
    }

    async apiJson(path, options = {}) {
        // Add error handling for API calls
        const response = await this.apiFetch(path, options);
        if (!response) return null;
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        return await response.json();
    }

    handleUnauthorized() {
        if (this.isLoggedIn) {
            this.showToast('error', 'Session Expired', 'Please login again');
        }
        this.updateLoginUI(false);
    }

    // ========================================================================
    // Authentication
    // ========================================================================

    async checkLoginStatus(silent = false) {
        try {
            const data = await this.apiJson('/auth/me');
            if (data && data.user) {
                this.updateLoginUI(true, data.user);
                return true;
            }
            this.updateLoginUI(false);
            if (!silent) {
                this.showLoginOverlay();
            }
            return false;
        } catch (error) {
            this.updateLoginUI(false);
            if (!silent) {
                this.showLoginOverlay();
                this.showToast('info', 'Login Required', 'Please login to continue');
            }
            return false;
        }
    }

    async login(username, password) {
        try {
            const response = await this.apiFetch('/auth/login', {
                method: 'POST',
                body: JSON.stringify({ username, password })
            });
            
            if (!response) {
                this.showToast('error', 'Login Failed', 'No response from server');
                return false;
            }
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
                throw new Error(errorData.detail || 'Login failed');
            }
            
            const data = await response.json();
            if (data && data.success) {
                this.dataInitialized = false;
                this.updateLoginUI(true, data.user);
                this.showToast('success', 'Login Success', `Welcome, ${data.user}!`);
                return true;
            } else {
                this.showToast('error', 'Login Failed', 'Invalid credentials');
                return false;
            }
        } catch (error) {
            console.error('Login error:', error);
            this.showToast('error', 'Login Failed', error.message);
            return false;
        }
    }

    async logout() {
        try {
            await this.apiFetch('/auth/logout', { method: 'POST' });
            this.dataInitialized = false;
            this.updateLoginUI(false);
            this.showToast('success', 'Logged Out', 'You have been logged out');
        } catch (error) {
            this.showToast('error', 'Logout Failed', error.message);
        }
    }

    async handleLoginSubmit() {
        if (this.loginInProgress) {
            return;
        }

        const usernameInput = document.getElementById('loginUsername');
        const passwordInput = document.getElementById('loginPassword');
        const submitBtn = document.getElementById('loginSubmitBtn');

        if (!usernameInput || !passwordInput) {
            return;
        }

        const username = usernameInput.value.trim();
        const password = passwordInput.value;

        if (!username || !password) {
            this.showToast('error', 'Missing Credentials', 'Enter both username and password');
            return;
        }

        const originalText = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Logging in...';
        }

        this.loginInProgress = true;
        const success = await this.login(username, password);
        this.loginInProgress = false;

        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }

        if (success) {
            this.hideLoginOverlay();
            this.bootstrapData(true);
        }
    }

    updateLoginUI(isLoggedIn, username = null) {
        this.isLoggedIn = !!isLoggedIn;

        const userInfo = document.getElementById('userInfo');
        const loginBtn = document.getElementById('loginBtn');
        const logoutBtn = document.getElementById('logoutBtn');

        if (userInfo) {
            userInfo.textContent = isLoggedIn
                ? `User: ${username || 'Admin'}`
                : 'Not authenticated';
        }

        if (loginBtn) {
            loginBtn.classList.toggle('d-none', !!isLoggedIn);
        }

        if (logoutBtn) {
            logoutBtn.classList.toggle('d-none', !isLoggedIn);
        }

        if (isLoggedIn) {
            this.hideLoginOverlay();
        } else {
            this.dataInitialized = false;
            this.showLoginOverlay();
        }
    }

    // ========================================================================
    // API Status
    // ========================================================================

    async checkApiStatus() {
        try {
            const response = await fetch(`${this.apiBaseUrl}/health`);
            const data = await response.json();
            const statusEl = document.getElementById('apiStatus');
            if (response.ok) {
                statusEl.innerHTML = `<i class="fas fa-circle me-2"></i>Online`;
                statusEl.className = 'status-online';
            } else {
                throw new Error('API not healthy');
            }
        } catch (error) {
            const statusEl = document.getElementById('apiStatus');
            statusEl.innerHTML = `<i class="fas fa-circle me-2"></i>Offline`;
            statusEl.className = 'status-offline';
        }
    }

    // ========================================================================
    // Templates
    // ========================================================================

    async loadTemplates() {
        if (!this.ensureAuthenticated(false)) return;
        try {
            // Add cache busting to ensure fresh data
            const cacheBuster = `?t=${Date.now()}`;
            const data = await this.apiJson(`/templates${cacheBuster}`);
            if (data && data.templates) {
                this.templates = data.templates.slice().sort((a, b) => {
                    const nameA = (a.metadata?.display_name || a.title || a.name || '').toLowerCase();
                    const nameB = (b.metadata?.display_name || b.title || b.name || '').toLowerCase();
                    return nameA.localeCompare(nameB);
                });
                // Build template name list for plan editing - use canonical names
                // Use name (which includes .docx extension) as primary identifier
                this.allTemplates = this.templates.map(t => {
                    if (typeof t === 'string') {
                        return t.endsWith('.docx') ? t : `${t}.docx`;
                    }
                    // Prioritize 'name' field as it's the canonical identifier
                    if (t.name) {
                        return t.name.endsWith('.docx') ? t.name : `${t.name}.docx`;
                    }
                    if (t.file_with_extension) {
                        return t.file_with_extension.endsWith('.docx') ? t.file_with_extension : `${t.file_with_extension}.docx`;
                    }
                    if (t.file_name) {
                        return t.file_name.endsWith('.docx') ? t.file_name : `${t.file_name}.docx`;
                    }
                    // Fallback to title-based name
                    if (t.title) {
                        return t.title.endsWith('.docx') ? t.title : `${t.title}.docx`;
                    }
                    return '';
                }).filter(t => t && t.trim() !== ''); // Remove empty values
                // Remove duplicates
                this.allTemplates = [...new Set(this.allTemplates)];
                console.log('Loaded templates:', this.allTemplates.length, 'templates:', this.allTemplates);
                this.displayTemplates(this.templates);
            } else {
                this.templates = [];
                this.allTemplates = [];
            }
        } catch (error) {
            console.error('Error loading templates:', error);
            this.showToast('error', 'Load Error', `Failed to load templates: ${error.message}`);
            this.templates = [];
            this.allTemplates = [];
        }
    }

    displayTemplates(templates) {
        const container = document.getElementById('templatesList');
        
        if (!Array.isArray(templates) || templates.length === 0) {
            container.innerHTML = '<div class="text-center text-muted py-4">No templates found</div>';
            return;
        }
        
        container.innerHTML = templates.map(template => {
            const meta = template.metadata || {};
            const placeholderList = template.placeholders || [];
            const preview = placeholderList.slice(0, 12).map(p => `<span class="placeholder-badge">${p}</span>`).join('');
            const extraCount = Math.max(0, placeholderList.length - 12);
            const description = meta.description || template.description || 'No description provided';
            const fontFamily = meta.font_family || 'Default';
            const fontSize = meta.font_size ? `${meta.font_size}pt` : '';
            const fontSummary = fontSize ? `${fontFamily} · ${fontSize}` : fontFamily;

            return `
                <div class="template-card card mb-3">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1 me-3">
                                <h5 class="mb-1 d-flex align-items-center">
                                    <i class="fas fa-file-word text-primary me-2"></i>
                                    ${meta.display_name || template.title || template.name}
                                </h5>
                                <div class="text-muted small mb-2">
                                    <i class="fas fa-file me-1"></i>${this.formatBytes(template.size || 0)} · 
                                    <i class="fas fa-tags me-1"></i>${placeholderList.length} placeholders
                                </div>
                                <p class="text-muted mb-2 small">${description}</p>
                                <div class="text-muted small mb-2">
                                    <i class="fas fa-font me-1"></i>${fontSummary}
                                </div>
                                <div class="mb-2">
                                    ${preview}
                                    ${extraCount > 0 ? `<span class="text-muted">+${extraCount} more</span>` : ''}
                                </div>
                            </div>
                            <div class="d-flex flex-column align-items-end gap-2">
                                <button class="btn btn-sm btn-success w-100" onclick="cms.testGenerateDocument('${template.name}')">
                                    <i class="fas fa-vial me-1"></i>Test
                                </button>
                                <button class="btn btn-sm btn-primary w-100" onclick="window.open('editor.html?template_id=${template.id || template.name}', '_blank')">
                                    <i class="fas fa-edit me-1"></i>Edit Rules
                                </button>
                                <button class="btn btn-sm btn-outline-secondary w-100" onclick="cms.viewPlaceholders('${template.name}')">
                                    <i class="fas fa-list me-1"></i>Placeholders
                                </button>
                                <button class="btn btn-sm btn-outline-primary w-100" onclick="cms.openMetadataModal('${template.name}')">
                                    <i class="fas fa-pen me-1"></i>Metadata
                                </button>
                                <button class="btn btn-sm btn-danger w-100" onclick="cms.deleteTemplate('${template.name}')">
                                    <i class="fas fa-trash me-1"></i>Delete
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.selectedFile = file;
            const uploadArea = document.getElementById('uploadArea');
            uploadArea.innerHTML = `
                <i class="fas fa-file-word fa-3x text-success mb-3"></i>
                <h5 class="text-success">${file.name}</h5>
                <p class="text-muted mb-0">Ready to upload</p>
            `;
        }
    }

    async uploadTemplate() {
        if (!this.ensureAuthenticated()) return;
        if (!this.selectedFile) {
            this.showToast('error', 'No File', 'Please select a file first');
            return;
        }

        const formData = new FormData();
        const displayNameInput = document.getElementById('templateNameInput');
        const descriptionInput = document.getElementById('templateDescriptionInput');
        const fontFamilySelect = document.getElementById('templateFontFamily');
        const fontSizeInput = document.getElementById('templateFontSize');

        formData.append('file', this.selectedFile);
        if (displayNameInput && displayNameInput.value) {
            formData.append('name', displayNameInput.value);
        }
        if (descriptionInput && descriptionInput.value) {
            formData.append('description', descriptionInput.value);
        }
        if (fontFamilySelect && fontFamilySelect.value) {
            formData.append('font_family', fontFamilySelect.value);
        }
        if (fontSizeInput && fontSizeInput.value) {
            formData.append('font_size', fontSizeInput.value);
        }
        
        // Get selected plan IDs
        const planCheckboxes = document.querySelectorAll('#planCheckboxes input[type="checkbox"]:checked');
        const selectedPlanIds = Array.from(planCheckboxes).map(cb => cb.value).filter(v => v);
        if (selectedPlanIds.length > 0) {
            formData.append('plan_ids', JSON.stringify(selectedPlanIds));
        }

        // Show loading state
        const uploadBtn = document.getElementById('uploadBtn');
        let originalText = '';
        if (uploadBtn) {
            originalText = uploadBtn.innerHTML;
            uploadBtn.disabled = true;
            uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Uploading...';
        }

        try {
            console.log('Uploading file:', this.selectedFile.name);
            const response = await this.apiFetch('/upload-template', {
                method: 'POST',
                body: formData
            });

            if (uploadBtn) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = originalText;
            }

            if (response && response.ok) {
                const data = await response.json();
                const warningMessages = Array.isArray(data.warnings) ? data.warnings : [];
                if (warningMessages.length) {
                    warningMessages.forEach(msg => this.showToast('warning', 'Upload Warning', msg));
                }
                this.showToast('success', 'Upload Success', `Template "${data.filename}" uploaded with ${data.placeholder_count} placeholders`);
                this.selectedFile = null;
                const uploadArea = document.getElementById('uploadArea');
                if (uploadArea) {
                    uploadArea.innerHTML = `
                        <i class="fas fa-cloud-upload-alt fa-3x text-muted mb-3"></i>
                        <h5>Drop DOCX file here</h5>
                        <p class="text-muted mb-0">or click to browse</p>
                    `;
                }
                const fileInput = document.getElementById('templateFile');
                if (fileInput) fileInput.value = '';
                if (displayNameInput) displayNameInput.value = '';
                if (descriptionInput) descriptionInput.value = '';
                if (fontFamilySelect) fontFamilySelect.value = '';
                if (fontSizeInput) fontSizeInput.value = '';

                // Force reload templates after a short delay to ensure backend has processed the upload
                // This helps ensure the template appears in the list immediately after upload
                console.log('Upload successful, reloading templates...');
                setTimeout(() => {
                    this.loadTemplates().then(() => {
                        console.log('Templates reloaded after upload');
                        // Also refresh plans to include new template
                        this.loadPlans();
                    }).catch(err => {
                        console.error('Error reloading templates after upload:', err);
                    });
                }, 500);
            } else {
                const statusText = response?.statusText || 'Unknown error';
                const statusCode = response?.status || 'N/A';
                let errorDetail = `HTTP ${statusCode}: ${statusText}`;
                
                try {
                    const errorJson = await response.json();
                    errorDetail = errorJson.detail || errorJson.message || errorDetail;
                } catch {
                    // Couldn't parse error JSON, use status text
                }
                
                this.showToast('error', 'Upload Failed', errorDetail);
                console.error('Upload error:', { status: statusCode, statusText, detail: errorDetail });
            }
        } catch (error) {
            if (uploadBtn && originalText) {
                uploadBtn.disabled = false;
                uploadBtn.innerHTML = originalText;
            }
            this.showToast('error', 'Upload Failed', error.message || 'Network error occurred');
            console.error('Upload exception:', error);
        }
    }

    async deleteTemplate(templateName) {
        if (!this.ensureAuthenticated()) return;
        if (!confirm(`Delete template "${templateName}"?`)) return;

        try {
            const response = await this.apiFetch(`/templates/${encodeURIComponent(templateName)}`, {
                method: 'DELETE'
            });
            
            if (response && response.ok) {
                const data = await response.json();
                if (data && data.success) {
                    const warnings = Array.isArray(data.warnings) ? data.warnings : [];
                    warnings.forEach(msg => this.showToast('warning', 'Delete Warning', msg));

                    this.showToast('success', 'Deleted', `Template "${templateName}" deleted`);
                    const target = this.normalizeTemplateName(templateName);

                    if (Array.isArray(this.templates)) {
                        this.templates = this.templates.filter(template => {
                            if (!template) return false;
                            const candidate = this.normalizeTemplateName(
                                template.name ||
                                template.file_with_extension ||
                                template.file_name ||
                                template.id ||
                                template
                            );
                            return candidate !== target;
                        });
                    }

                    if (Array.isArray(this.allTemplates)) {
                        this.allTemplates = this.allTemplates.filter(name => this.normalizeTemplateName(name) !== target);
                    }

                    // Remove from display immediately
                    this.displayTemplates(this.templates);
                    // Force reload templates after a short delay to ensure backend deletion is complete
                    setTimeout(() => {
                        this.loadTemplates().then(() => {
                            // Also refresh plans to drop deleted template references
                            this.loadPlans();
                        });
                    }, 1000);
                }
            } else {
                const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
                throw new Error(error.detail);
            }
        } catch (error) {
            this.showToast('error', 'Delete Failed', error.message);
        }
    }

    // ========================================================================
    // Data Sources
    // ========================================================================

    async loadDataSources() {
        if (!this.ensureAuthenticated(false)) return;
        try {
            const data = await this.apiJson('/data/all');
            if (data && data.data_sources) {
                this.displayDataSources(data.data_sources);
            }
        } catch (error) {
            this.showToast('error', 'Load Error', `Failed to load data sources: ${error.message}`);
        }
    }

    displayDataSources(sources) {
        const container = document.getElementById('dataSourcesList');
        const entries = Object.entries(sources || {});

        if (entries.length === 0) {
            container.innerHTML = `
                <div class="text-muted text-center py-3">
                    <i class="fas fa-circle-info me-2"></i>No CSV datasets uploaded yet.
                </div>
            `;
            return;
        }

        container.innerHTML = entries.map(([id, source]) => {
            const displayName = source.display_name || id.replace('_', ' ').toUpperCase();
            const exists = source.exists;
            const size = exists ? this.formatBytes(source.size) : 'n/a';
            const rows = exists ? source.row_count : 0;
            return `
                <div class="card mb-3">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <h6 class="mb-1">
                                    <i class="fas fa-database me-2"></i>${displayName}
                                </h6>
                                <div class="small text-muted mb-1">Dataset ID: <code>${id}</code></div>
                                <div class="small">
                                    <div><strong>File:</strong> ${source.filename}</div>
                                    <div><strong>Status:</strong> ${exists ? '<span class="text-success">✓ Available</span>' : '<span class="text-danger">✗ Missing</span>'}</div>
                                    ${exists ? `<div><strong>Size:</strong> ${size}</div>` : ''}
                                    ${exists ? `<div><strong>Rows:</strong> ${rows}</div>` : ''}
                                </div>
                            </div>
                            <div>
                                ${exists ? `<button class="btn btn-sm btn-outline-danger" onclick="cms.deleteCSV('${id}')">
                                    <i class="fas fa-trash me-1"></i>Delete
                                </button>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    handleCSVSelect(event) {
        const file = event.target.files[0];
        if (file) {
            this.selectedCSV = file;
            const uploadArea = document.getElementById('csvUploadArea');
            uploadArea.innerHTML = `
                <i class="fas fa-file-csv fa-3x text-success mb-3"></i>
                <h5 class="text-success">${file.name}</h5>
                <p class="text-muted mb-0">Ready to upload</p>
            `;
        }
    }

    async uploadCSV() {
        if (!this.ensureAuthenticated()) return;
        if (!this.selectedCSV) {
            this.showToast('error', 'No File', 'Please select a CSV file first');
            return;
        }

        const dataTypeInput = document.getElementById('csvDataType');
        if (!dataTypeInput) {
            this.showToast('error', 'Upload Failed', 'Dataset name input missing in the page.');
            return;
        }
        const dataType = dataTypeInput.value.trim();
        if (!dataType) {
            this.showToast('error', 'Upload Failed', 'Please enter a dataset name (letters and numbers only).');
            return;
        }

        const formData = new FormData();
        formData.append('file', this.selectedCSV);
        formData.append('data_type', dataType);

        try {
            const response = await this.apiFetch('/upload-csv', {
                method: 'POST',
                headers: {},
                body: formData
            });

            if (response && response.ok) {
                const data = await response.json();
                this.showToast('success', 'Upload Success', `Dataset "${data.display_name || data.dataset_id}" uploaded`);
                this.selectedCSV = null;
                const csvUploadArea = document.getElementById('csvUploadArea');
                if (csvUploadArea) {
                    csvUploadArea.innerHTML = `
                        <i class="fas fa-file-csv fa-3x text-muted mb-3"></i>
                        <h5>Drop CSV file here</h5>
                        <p class="text-muted mb-0">or click to browse</p>
                    `;
                }
                const csvFileInput = document.getElementById('csvFile');
                if (csvFileInput) {
                    csvFileInput.value = '';
                }
                dataTypeInput.value = '';
                this.loadDataSources();
            } else {
                const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
                throw new Error(error.detail);
            }
        } catch (error) {
            this.showToast('error', 'Upload Failed', error.message);
        }
    }

    async deleteCSV(csvId) {
        if (!this.ensureAuthenticated()) return;
        if (!csvId) return;
        if (!confirm(`Delete dataset "${csvId}"?`)) return;

        try {
            const response = await this.apiFetch(`/csv-files/${encodeURIComponent(csvId)}`, {
                method: 'DELETE'
            });

            if (response && response.ok) {
                const data = await response.json();
                this.showToast('success', 'Deleted', `Dataset "${data.dataset_id || csvId}" deleted`);
                this.loadDataSources();
            } else {
                const error = await response.json().catch(() => ({ detail: 'Delete failed' }));
                throw new Error(error.detail || 'Delete failed');
            }
        } catch (error) {
            this.showToast('error', 'Delete Failed', error.message);
        }
    }

    // ========================================================================
    // Plans
    // ========================================================================

    async loadPlans(forceReload = false) {
        if (!this.ensureAuthenticated(false)) return;
        try {
            // CRITICAL: Always use database endpoint first to get latest plans
            // Add cache busting to ensure fresh data
            const cacheBuster = `?t=${Date.now()}`;
            let data = null;
            let source = 'unknown';
            
            if (forceReload) {
                console.log('[loadPlans] 🔄 Force reloading plans from database...');
            } else {
                console.log('[loadPlans] 📋 Loading plans...');
            }
            
            try {
                // Always try database first to get latest plans from CMS
                // Use aggressive cache busting for force reloads
                const cacheBusterValue = forceReload ? `?t=${Date.now()}&_=${Math.random()}` : cacheBuster;
                data = await this.apiJson(`/plans-db${cacheBusterValue}`);
                source = 'database';
                const plansCount = data && data.plans ? Object.keys(data.plans).length : 0;
                console.log('[loadPlans] ✅ Loaded plans from database:', plansCount, 'plans');
                console.log('[loadPlans] Plan IDs:', data && data.plans ? Object.keys(data.plans) : []);
                
                // Log each plan's can_download to debug
                if (data && data.plans) {
                    for (const [planKey, plan] of Object.entries(data.plans)) {
                        const canDownload = plan.can_download || [];
                        const isAllTemplates = Array.isArray(canDownload) && canDownload.length === 1 && canDownload[0] === '*';
                        console.log(`[loadPlans] Plan ${planKey}: can_download = ${isAllTemplates ? 'ALL (*)' : `${canDownload.length} templates`}`, canDownload.slice(0, 3));
                    }
                }
            } catch (e) {
                console.warn('[loadPlans] ⚠️ Failed to load plans from database, trying JSON:', e);
                // Fallback to JSON
                try {
                    data = await this.apiJson(`/plans${cacheBuster}`);
                    source = 'json';
                    console.log('[loadPlans] ✅ Loaded plans from JSON:', Object.keys(data.plans || {}).length, 'plans');
                } catch (e2) {
                    console.error('[loadPlans] ❌ Failed to load plans from JSON:', e2);
                    this.showToast('error', 'Load Error', 'Failed to load plans. Using empty list.');
                    data = { plans: {} };
                }
            }
            
            if (data && data.plans && typeof data.plans === 'object') {
                console.log('[loadPlans] ✅ Displaying plans from', source, ':', Object.keys(data.plans));
                console.log('[loadPlans] 📋 All plan IDs:', Object.keys(data.plans));
                console.log('[loadPlans] 📋 Plan tiers:', Object.values(data.plans).map(p => p.plan_tier || p.id || 'unknown'));
                
                // IMPORTANT: Store plans before displaying - include broker membership
                // Store all plans including broker membership
                this.allPlans = data.plans || {};
                console.log('[loadPlans] 💾 Stored', Object.keys(this.allPlans).length, 'plans/memberships in allPlans:', Object.keys(this.allPlans));
                this.displayPlans(data.plans || {});
                // Update plan checkboxes in upload form
                this.populatePlanCheckboxes();
                // Also update plan checkboxes in metadata modal if open
                if (this.activeTemplateMetadata) {
                    this.populateMetaPlanCheckboxes(this.findTemplateByName(this.activeTemplateMetadata));
                }
            } else {
                console.warn('[loadPlans] ⚠️ No plans data received or invalid format');
                this.allPlans = {};
                this.displayPlans({});
                this.populatePlanCheckboxes();
            }
        } catch (error) {
            console.error('[loadPlans] ❌ Error loading plans:', error);
            this.showToast('error', 'Load Error', `Failed to load plans: ${error.message}`);
            this.allPlans = {};
            this.displayPlans({});
        }
    }

    displayPlans(plans) {
        const container = document.getElementById('plansList');
        if (!container) {
            console.error('[displayPlans] ❌ plansList container not found');
            return;
        }
        
        // Ensure plans is an object
        if (!plans || typeof plans !== 'object' || Array.isArray(plans)) {
            console.warn('[displayPlans] ⚠️ Invalid plans data:', plans);
            container.innerHTML = '<div class="text-center text-muted py-4">No plans found</div>';
            return;
        }
        
        const planEntries = Object.entries(plans);
        console.log('[displayPlans] 📋 Rendering', planEntries.length, 'plans');
        
        if (planEntries.length === 0) {
            container.innerHTML = '<div class="text-center text-muted py-4">No plans found</div>';
            // Still store empty plans
            this.allPlans = {};
            return;
        }
        
        // Separate plans and broker membership
        const subscriptionPlans = [];
        let brokerMembership = null;
        
        for (const [planId, plan] of planEntries) {
            const tier = (plan.plan_tier || planId || '').toLowerCase();
            if (tier === 'broker' || plan.is_membership) {
                brokerMembership = [planId, plan];
            } else {
                subscriptionPlans.push([planId, plan]);
            }
        }
        
        // Sort subscription plans
        subscriptionPlans.sort(([aId, aPlan], [bId, bPlan]) => {
            const aTier = aPlan.plan_tier || aId || '';
            const bTier = bPlan.plan_tier || bId || '';
            const order = ['basic', 'professional', 'enterprise'];
            const aIndex = order.indexOf(aTier.toLowerCase());
            const bIndex = order.indexOf(bTier.toLowerCase());
            if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
            if (aIndex !== -1) return -1;
            if (bIndex !== -1) return 1;
            return aTier.localeCompare(bTier);
        });
        
        console.log('[displayPlans] 📋 Rendering', subscriptionPlans.length, 'plans and', brokerMembership ? '1 broker membership' : '0 broker memberships');
        
        // Render subscription plans first
        let html = subscriptionPlans.map(([planId, plan]) => {
            const canDownload = plan.can_download || [];
            const canDownloadList = Array.isArray(canDownload) ? canDownload : [canDownload];
            const isAllTemplates = canDownloadList.length === 1 && canDownloadList[0] === '*';
            const maxDownloads = plan.max_downloads_per_month !== undefined ? plan.max_downloads_per_month : 10;
            const features = Array.isArray(plan.features) ? plan.features : [];
            const planTier = plan.plan_tier || planId;
            const planName = plan.name || plan.plan_name || planId;
            // Use plan_tier as the identifier for editing (backend expects this)
            const editPlanId = plan.plan_tier || plan.id || planId;
            
            console.log('[displayPlans] 📋 Rendering plan:', planId, 'tier:', planTier, 'name:', planName, 'editId:', editPlanId);
            console.log('[displayPlans] 📋 can_download:', canDownloadList, 'isAllTemplates:', isAllTemplates);
            
            return `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="mb-0">${planName} <small class="text-muted">(${planTier})</small></h5>
                        <button class="btn btn-sm btn-outline-primary" onclick="cms.editPlan('${editPlanId}')">
                            <i class="fas fa-edit me-1"></i>Edit
                        </button>
                    </div>
                    <div class="mb-2">
                        <strong>Download Allowed:</strong>
                        ${isAllTemplates ? 
                            '<span class="badge bg-success ms-2">All templates (*)</span>' : 
                            `<span class="badge bg-info ms-2">${canDownloadList.length} template${canDownloadList.length === 1 ? '' : 's'}</span>`
                        }
                        ${!isAllTemplates && canDownloadList.length > 0 ? 
                            `<ul class="mb-0 mt-2"><li><small>${canDownloadList.map(t => this.formatTemplateLabel(t)).join('</small></li><li><small>')}</small></li></ul>` : ''
                        }
                    </div>
                    <div class="mb-2">
                        <strong>Max Downloads:</strong> ${maxDownloads === -1 ? '<span class="badge bg-success ms-2">Unlimited</span>' : `<span class="badge bg-secondary ms-2">${maxDownloads}/month</span>`}
                    </div>
                    ${features.length > 0 ? `
                    <div>
                        <strong>Features:</strong> <small class="text-muted">${features.slice(0, 3).join(', ')}${features.length > 3 ? '...' : ''}</small>
                    </div>
                    ` : ''}
                </div>
            </div>
        `;
        }).join('');
        
        // Add broker membership display if it exists
        if (brokerMembership) {
            const [brokerId, broker] = brokerMembership;
            const canDownload = broker.can_download || [];
            const canDownloadList = Array.isArray(canDownload) ? canDownload : [canDownload];
            const isAllTemplates = canDownloadList.length === 1 && canDownloadList[0] === '*';
            const features = Array.isArray(broker.features) ? broker.features : [];
            
            html += `
            <div class="card mb-3 border-warning">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="mb-0">
                            <i class="fas fa-crown me-2 text-warning"></i>${broker.name || 'Broker Membership'} 
                            <small class="text-muted">(Membership)</small>
                        </h5>
                        <button class="btn btn-sm btn-outline-warning" onclick="cms.editBrokerMembership('${brokerId}')">
                            <i class="fas fa-edit me-1"></i>Edit
                        </button>
                    </div>
                    <div class="mb-2">
                        <strong>Download Allowed:</strong>
                        ${isAllTemplates ? 
                            '<span class="badge bg-success ms-2">All templates (*)</span>' : 
                            `<span class="badge bg-info ms-2">${canDownloadList.length} template${canDownloadList.length === 1 ? '' : 's'}</span>`
                        }
                        ${!isAllTemplates && canDownloadList.length > 0 ? 
                            `<ul class="mb-0 mt-2"><li><small>${canDownloadList.map(t => this.formatTemplateLabel(t)).join('</small></li><li><small>')}</small></li></ul>` : ''
                        }
                    </div>
                    <div class="mb-2">
                        <strong>Download Limits:</strong> <span class="badge bg-warning ms-2">Per-template limits</span>
                    </div>
                    ${features.length > 0 ? `
                    <div>
                        <strong>Features:</strong> <small class="text-muted">${features.slice(0, 3).join(', ')}${features.length > 3 ? '...' : ''}</small>
                    </div>
                    ` : ''}
                </div>
            </div>
            `;
        }
        
        container.innerHTML = html;
        
        // Store plans for editing (already stored in loadPlans, but ensure it's set)
        if (!this.allPlans || Object.keys(this.allPlans).length === 0) {
            this.allPlans = plans;
        } else {
            // Merge with existing plans to preserve any that might have been loaded elsewhere
            this.allPlans = { ...this.allPlans, ...plans };
        }
        console.log('[displayPlans] ✅ Stored', Object.keys(this.allPlans).length, 'plans in allPlans');
        // Ensure templates are loaded - rebuild allTemplates from current templates
        if (this.templates && Array.isArray(this.templates) && this.templates.length > 0) {
            this.allTemplates = this.templates.map(t => {
                if (typeof t === 'string') {
                    return t.endsWith('.docx') ? t : `${t}.docx`;
                }
                if (t.name) {
                    return t.name.endsWith('.docx') ? t.name : `${t.name}.docx`;
                }
                if (t.file_with_extension) {
                    return t.file_with_extension.endsWith('.docx') ? t.file_with_extension : `${t.file_with_extension}.docx`;
                }
                if (t.file_name) {
                    return t.file_name.endsWith('.docx') ? t.file_name : `${t.file_name}.docx`;
                }
                return '';
            }).filter(t => t && t.trim() !== '');
            // Remove duplicates
            this.allTemplates = [...new Set(this.allTemplates)];
            console.log('Rebuilt allTemplates in displayPlans:', this.allTemplates.length, 'templates:', this.allTemplates);
        } else {
            // If templates aren't loaded, load them now (async, won't block)
            if (this.allTemplates && this.allTemplates.length === 0) {
                console.log('Templates not loaded, fetching...');
                this.loadTemplates().catch(err => {
                    console.warn('Failed to load templates in displayPlans:', err);
                });
            }
        }
    }

    // Removed testPermission() - functionality moved to test suite

    async testGenerateDocument(templateName) {
        if (!this.ensureAuthenticated()) return;
        // Show vessel selection modal
        this.showVesselSelectionModal(templateName);
    }

    showVesselSelectionModal(templateName) {
        // Create modal HTML
        const modalHtml = `
            <div class="modal fade" id="vesselModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Generate Document</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label">Select Vessel</label>
                                <select class="form-select" id="vesselSelect">
                                    <option value="">Loading vessels...</option>
                                </select>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Or enter IMO number</label>
                                <input type="text" class="form-control" id="vesselIMO" placeholder="e.g., TEST001">
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" onclick="cms.generateWithVessel('${templateName}')">
                                <i class="fas fa-download me-1"></i>Generate & Download
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove existing modal if any
        const existingModal = document.getElementById('vesselModal');
        if (existingModal) {
            existingModal.remove();
        }
        
        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Load vessels
        this.loadVesselsForModal();
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('vesselModal'));
        modal.show();
    }

    async loadVesselsForModal() {
        const select = document.getElementById('vesselSelect');
        if (!select) return;
        
        try {
            const data = await this.apiJson('/vessels');
            if (data && data.vessels) {
                select.innerHTML = '<option value="">-- Select a vessel --</option>';
                data.vessels.forEach(vessel => {
                    select.innerHTML += `<option value="${vessel.imo}">${vessel.name} (${vessel.imo})</option>`;
                });
            }
        } catch (error) {
            select.innerHTML = '<option value="">Error loading vessels</option>';
            console.error('Error loading vessels:', error);
        }
    }

    async generateWithVessel(templateName) {
        if (!this.ensureAuthenticated()) return;
        const select = document.getElementById('vesselSelect');
        const imoInput = document.getElementById('vesselIMO');
        
        let vesselIMO = '';
        if (select && select.value) {
            vesselIMO = select.value;
        } else if (imoInput && imoInput.value) {
            vesselIMO = imoInput.value.trim();
        }
        
        if (!vesselIMO) {
            this.showToast('error', 'Vessel Required', 'Please select or enter a vessel IMO');
            return;
        }
        
        // Close modal
        const modalElement = document.getElementById('vesselModal');
        if (modalElement) {
            const modal = bootstrap.Modal.getInstance(modalElement);
            if (modal) modal.hide();
        }
        
        this.showToast('info', 'Generating...', 'Creating document...');
        
        try {
            const response = await fetch(`${this.apiBaseUrl}/generate-document`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    template_name: templateName,
                    vessel_imo: vesselIMO
                })
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'Generation failed' }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            // Get filename from Content-Disposition header
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = 'generated_document.pdf';
            if (contentDisposition) {
                const filenameMatch = contentDisposition.match(/filename=(.+?)(?:;|$)/);
                if (filenameMatch) {
                    filename = filenameMatch[1].replace(/"/g, '');  // Remove quotes
                }
            }

            // Download the file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            this.showToast('success', 'Success', `Document "${filename}" generated and downloaded!`);
        } catch (error) {
            this.showToast('error', 'Generation Failed', error.message);
        }
    }

    async editPlan(planId) {
        if (!this.ensureAuthenticated()) return;
        
        console.log('[editPlan] 📝 Opening editor for plan:', planId);
        
        // CRITICAL: Always reload plans and templates to get latest data
        try {
            console.log('[editPlan] 🔄 Reloading plans and templates for plan editor...');
            // Reload plans first to get latest plans from database (force reload with cache busting)
            await this.loadPlans(true);
            // Wait a bit to ensure data is loaded
            await new Promise(resolve => setTimeout(resolve, 100));
            // Reload templates to get latest templates
            await this.loadTemplates();
            
            const plansCount = this.allPlans ? Object.keys(this.allPlans).length : 0;
            const templatesCount = this.templates ? this.templates.length : 0;
            const allTemplatesCount = this.allTemplates ? this.allTemplates.length : 0;
            
            console.log('[editPlan] ✅ Plans reloaded:', plansCount, 'plans');
            console.log('[editPlan] ✅ Plan IDs:', this.allPlans ? Object.keys(this.allPlans) : []);
            console.log('[editPlan] ✅ Templates loaded:', templatesCount);
            console.log('[editPlan] ✅ allTemplates:', allTemplatesCount);
        } catch (error) {
            console.error('[editPlan] ❌ Failed to reload plans/templates:', error);
            this.showToast('error', 'Error', 'Failed to reload data. Please refresh the page.');
            return;
        }
        
        // Check if plan exists after reload
        if (!this.allPlans || !this.allPlans[planId]) {
            console.error('[editPlan] ❌ Plan not found after reload. Available plans:', this.allPlans ? Object.keys(this.allPlans) : []);
            this.showToast('error', 'Error', `Plan "${planId}" not found. Available plans: ${this.allPlans ? Object.keys(this.allPlans).join(', ') : 'none'}`);
            return;
        }
        
        // Ensure allTemplates is populated
        if (!this.allTemplates || this.allTemplates.length === 0) {
            if (this.templates && this.templates.length > 0) {
                this.allTemplates = this.templates.map(t => {
                    if (typeof t === 'string') {
                        return t.endsWith('.docx') ? t : `${t}.docx`;
                    }
                    const name = t.name || t.file_with_extension || t.file_name || '';
                    return name.endsWith('.docx') ? name : `${name}.docx`;
                }).filter(t => t && t.trim() !== '');
                this.allTemplates = [...new Set(this.allTemplates)];
            } else {
                this.showToast('error', 'Error', 'No templates found. Please upload templates first.');
                return;
            }
        }
        
        // CRITICAL: Get fresh plan data from allPlans (just reloaded)
        // Try to find plan by planId (could be tier or UUID)
        let plan = this.allPlans[planId];
        if (!plan) {
            // Try to find by plan_tier or id
            for (const [key, p] of Object.entries(this.allPlans)) {
                if (p.plan_tier === planId || key === planId || p.id === planId || String(p.id) === String(planId)) {
                    plan = p;
                    console.log('[editPlan] ✅ Found plan by search:', key, 'plan_tier:', p.plan_tier, 'id:', p.id);
                    break;
                }
            }
        }
        
        // If still not found, try case-insensitive search
        if (!plan) {
            const planIdLower = String(planId).toLowerCase();
            for (const [key, p] of Object.entries(this.allPlans)) {
                const tierLower = (p.plan_tier || '').toLowerCase();
                const keyLower = key.toLowerCase();
                if (tierLower === planIdLower || keyLower === planIdLower) {
                    plan = p;
                    console.log('[editPlan] ✅ Found plan by case-insensitive search:', key);
                    break;
                }
            }
        }
        
        if (!plan) {
            console.error('[editPlan] ❌ Plan not found:', planId);
            this.showToast('error', 'Error', `Plan "${planId}" not found`);
            return;
        }
        
        const templates = this.allTemplates || [];
        
        // CRITICAL: Log plan.can_download to verify it's updated
        console.log('[editPlan] 📋 Editing plan:', planId);
        console.log('[editPlan] 📋 Plan can_download:', plan.can_download);
        console.log('[editPlan] 📋 Plan max_downloads_per_month:', plan.max_downloads_per_month);
        console.log('[editPlan] 📋 Plan data:', JSON.stringify(plan, null, 2));
        console.log('[editPlan] 📋 Templates available:', templates.length, templates);
        console.log('[editPlan] 📋 Stored templates:', this.templates ? this.templates.length : 0);
        
        // Validate plan data
        if (!plan) {
            console.error('[editPlan] ❌ Plan object is null or undefined');
            this.showToast('error', 'Error', 'Plan data is invalid');
            return;
        }
        
        // Create modal HTML
        const modalHtml = `
            <div class="modal fade" id="editPlanModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Edit Plan: ${plan.name}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label"><strong>Allowed Templates:</strong></label>
                                <div class="mb-2">
                                    <label class="form-check">
                                        <input type="radio" name="accessType" value="all" class="form-check-input" ${plan.can_download && plan.can_download[0] === '*' ? 'checked' : ''} onchange="cms.toggleTemplateSelection()">
                                        <span>All templates (unlimited)</span>
                                    </label>
                                </div>
                                <div class="mb-2">
                                    <label class="form-check">
                                        <input type="radio" name="accessType" value="specific" class="form-check-input" ${(plan.can_download && plan.can_download.length > 0 && plan.can_download[0] !== '*') ? 'checked' : ''} onchange="cms.toggleTemplateSelection()">
                                        <span>Specific templates</span>
                                    </label>
                                </div>
                            </div>
                            <div id="templateSelection" class="mb-3 border rounded p-3" style="max-height: 300px; overflow-y: auto; ${(plan.can_download && plan.can_download.length === 1 && plan.can_download[0] === '*') ? 'display:none;' : 'display:block;'}">
                                <p class="mb-2"><strong>Select templates:</strong></p>
                                ${templates.length > 0 ? templates.map(t => {
                                    // Normalize template name - ensure consistent format
                                    let templateName = '';
                                    let templateId = '';
                                    if (typeof t === 'string') {
                                        templateName = t.endsWith('.docx') ? t : `${t}.docx`;
                                        // Try to find ID from this.templates array
                                        const templateObj = this.templates.find(tmpl => {
                                            const tmplName = tmpl.name || tmpl.file_with_extension || tmpl.file_name || '';
                                            return tmplName === templateName || tmplName === t || tmplName.replace('.docx', '') === t.replace('.docx', '');
                                        });
                                        templateId = templateObj ? (templateObj.id || templateObj.template_id || '') : '';
                                    } else {
                                        templateName = t.name || t.file_with_extension || t.file_name || '';
                                        if (templateName && !templateName.endsWith('.docx')) {
                                            templateName = `${templateName}.docx`;
                                        }
                                        // Get template ID - CRITICAL for reliable matching
                                        templateId = t.id || t.template_id || '';
                                        console.log('[editPlan] 📋 Template:', templateName, 'ID:', templateId);
                                    }
                                    // CRITICAL: Get fresh can_download list from plan object
                                    // Normalize can_download: handle both array and single value
                                    let canDownloadList = [];
                                    if (plan.can_download) {
                                        if (Array.isArray(plan.can_download)) {
                                            canDownloadList = [...plan.can_download];
                                        } else if (typeof plan.can_download === 'string') {
                                            canDownloadList = [plan.can_download];
                                        }
                                    }
                                    
                                    console.log('[editPlan] 🔍 Checking template:', templateName, 'against can_download:', canDownloadList);
                                    
                                    // Check if plan has all templates access
                                    const hasAllTemplates = canDownloadList.length === 1 && canDownloadList[0] === '*';
                                    
                                    // Normalize template name for comparison (lowercase, ensure .docx)
                                    const normalizedTemplateName = templateName.toLowerCase().endsWith('.docx') ? templateName.toLowerCase() : `${templateName.toLowerCase()}.docx`;
                                    const templateNameWithoutExt = normalizedTemplateName.replace('.docx', '');
                                    
                                    // Check if this specific template is allowed
                                    let isChecked = false;
                                    if (hasAllTemplates) {
                                        // If plan has all templates, don't check individual templates
                                        isChecked = false; // Will be handled by radio button
                                        console.log('[editPlan] ✅ Plan has all templates access, not checking individual template');
                                    } else {
                                        // Check if this template is in the allowed list
                                        // Try multiple matching strategies for flexibility
                                        isChecked = canDownloadList.some(allowed => {
                                            if (!allowed || allowed === '*') return false;
                                            
                                            // Normalize allowed template name
                                            const normalizedAllowed = allowed.toLowerCase().endsWith('.docx') ? allowed.toLowerCase() : `${allowed.toLowerCase()}.docx`;
                                            const allowedWithoutExt = normalizedAllowed.replace('.docx', '');
                                            
                                            // Match with or without extension, case-insensitive
                                            const match = normalizedAllowed === normalizedTemplateName || 
                                                         allowedWithoutExt === templateNameWithoutExt ||
                                                         allowed.toLowerCase() === templateNameWithoutExt ||
                                                         allowed.toLowerCase() === templateName.toLowerCase() ||
                                                         allowed.toLowerCase().replace('.docx', '') === templateNameWithoutExt;
                                            
                                            if (match) {
                                                console.log('[editPlan] ✅ Template', templateName, 'matches allowed template:', allowed);
                                            }
                                            
                                            return match;
                                        });
                                        
                                        if (!isChecked) {
                                            console.log('[editPlan] ❌ Template', templateName, 'NOT in can_download list');
                                        }
                                    }
                                    const displayName = typeof t === 'string' ? t : (t.metadata?.display_name || t.title || t.name || templateName).replace('.docx', '');
                                    // Get existing per-template limit
                                    const templateLimits = plan.template_limits || {};
                                    const existingLimit = templateId ? (templateLimits[templateId] || templateLimits[String(templateId)] || '') : '';
                                    
                                    return `
                                        <div class="d-flex align-items-center mb-2 border-bottom pb-2">
                                            <div class="form-check flex-grow-1">
                                                <input type="checkbox" class="form-check-input template-checkbox" value="${templateName}" 
                                                    data-template-id="${templateId}"
                                                    ${isChecked ? 'checked' : ''}>
                                                <label class="form-check-label">${displayName}</label>
                                            </div>
                                            <div class="ms-3" style="width: 150px;">
                                                <input type="number" class="form-control form-control-sm template-limit-input" 
                                                    data-template-id="${templateId}"
                                                    placeholder="Limit" 
                                                    value="${existingLimit}"
                                                    min="1"
                                                    ${!isChecked ? 'disabled' : ''}>
                                                <small class="text-muted d-block" style="font-size: 0.75rem;">Per-template limit</small>
                                            </div>
                                        </div>
                                    `;
                                }).join('') : '<p class="text-muted">No templates available. Please upload templates first.</p>'}
                            </div>
                            <div class="mb-3">
                                <label class="form-label"><strong>Plan-Level Max Downloads Per Month (Fallback):</strong></label>
                                <input type="number" class="form-control" id="maxDownloads" value="${plan.max_downloads_per_month !== undefined && plan.max_downloads_per_month !== null ? plan.max_downloads_per_month : 10}" placeholder="Enter number (use -1 for unlimited)">
                                <small class="text-muted">This is used as fallback if per-template limit is not set. Enter -1 for unlimited downloads, or a positive number for the monthly limit. Current value: ${plan.max_downloads_per_month !== undefined && plan.max_downloads_per_month !== null ? plan.max_downloads_per_month : 10}</small>
                            </div>
                            <div class="mb-3">
                                <label class="form-label"><strong>Features (comma-separated):</strong></label>
                                <input type="text" class="form-control" id="planFeatures" value="${plan.features && Array.isArray(plan.features) ? plan.features.join(', ') : (plan.features || '')}">
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" onclick="cms.savePlan('${planId}')">
                                <i class="fas fa-save me-1"></i>Save Changes
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove existing modal if any
        const existingModal = document.getElementById('editPlanModal');
        if (existingModal) existingModal.remove();
        
        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('editPlanModal'));
        modal.show();
        
        // Add event listeners for template checkboxes to enable/disable limit inputs
        const modalElement = document.getElementById('editPlanModal');
        if (modalElement) {
            const checkboxes = modalElement.querySelectorAll('.template-checkbox');
            checkboxes.forEach(checkbox => {
                checkbox.addEventListener('change', function() {
                    const templateId = this.getAttribute('data-template-id');
                    const limitInput = modalElement.querySelector(`.template-limit-input[data-template-id="${templateId}"]`);
                    if (limitInput) {
                        limitInput.disabled = !this.checked;
                        if (!this.checked) {
                            limitInput.value = '';
                        }
                    }
                });
            });
        }
        
        // Clean up modal when hidden
        document.getElementById('editPlanModal').addEventListener('hidden.bs.modal', function() {
            this.remove();
        });
    }
    
    toggleTemplateSelection() {
        // CRITICAL: Query from within modal to ensure correct elements
        const modalElement = document.getElementById('editPlanModal');
        const specificRadio = modalElement ? 
            modalElement.querySelector('input[name="accessType"][value="specific"]') :
            document.querySelector('input[name="accessType"][value="specific"]');
        const templateSelection = document.getElementById('templateSelection');
        
        if (templateSelection && specificRadio) {
            const isChecked = specificRadio.checked;
            console.log('[toggleTemplateSelection] 🔄 Toggling template selection, specific checked:', isChecked);
            templateSelection.style.display = isChecked ? 'block' : 'none';
        } else {
            console.warn('[toggleTemplateSelection] ⚠️ Could not find elements:', { modalElement, specificRadio, templateSelection });
        }
    }
    
    async savePlan(planId) {
        if (!this.ensureAuthenticated()) return;
        try {
            const accessTypeRadio = document.querySelector('input[name="accessType"]:checked');
            if (!accessTypeRadio) {
                console.error('[savePlan] ❌ No access type radio selected');
                this.showToast('error', 'Error', 'Please select access type');
                return;
            }
            
            const accessType = accessTypeRadio.value;
            console.log('[savePlan] 📋 Access type selected:', accessType);
            let canDownload = [];
            
            if (accessType === 'all') {
                canDownload = ['*'];
                console.log('[savePlan] ✅ Setting can_download to ["*"] (all templates)');
            } else {
                // CRITICAL: Use template IDs instead of names for reliable matching
                const modalElement = document.getElementById('editPlanModal');
                const checkboxes = modalElement ? 
                    modalElement.querySelectorAll('.template-checkbox:checked') : 
                    document.querySelectorAll('.template-checkbox:checked');
                
                console.log('[savePlan] 📋 Found', checkboxes.length, 'checked template checkboxes');
                
                // Collect template IDs and names
                const templateIds = [];
                const templateNames = [];
                
                Array.from(checkboxes).forEach(cb => {
                    const templateId = cb.getAttribute('data-template-id');
                    const templateName = cb.value;
                    
                    if (templateId) {
                        // Use ID if available (more reliable)
                        templateIds.push(templateId);
                        console.log('[savePlan] 📋 Template ID:', templateId, 'name:', templateName);
                    } else {
                        // Fallback to name if no ID
                        const normalizedValue = templateName.endsWith('.docx') ? templateName : `${templateName}.docx`;
                        templateNames.push(normalizedValue);
                        console.log('[savePlan] 📋 Template name (no ID):', normalizedValue);
                    }
                });
                
                // Send both IDs and names for maximum compatibility
                // Backend will prioritize IDs if provided
                canDownload = {
                    template_ids: templateIds,
                    template_names: templateNames
                };
                
                console.log('[savePlan] 📋 Selected templates - IDs:', templateIds, 'Names:', templateNames);
                
                if (templateIds.length === 0 && templateNames.length === 0) {
                    console.error('[savePlan] ❌ No templates selected');
                    this.showToast('error', 'Error', 'Please select at least one template');
                    return;
                }
            }
            
            const maxDownloadsInput = document.getElementById('maxDownloads');
            if (!maxDownloadsInput) {
                this.showToast('error', 'Error', 'Max downloads input not found');
                return;
            }
            // Parse max downloads - handle empty string, null, -1 for unlimited, and valid numbers
            const maxDownloadsValue = maxDownloadsInput.value.trim();
            let maxDownloads;
            // Get existing plan to use as fallback
            const existingPlan = this.allPlans && this.allPlans[planId] ? this.allPlans[planId] : {};
            if (maxDownloadsValue === '' || maxDownloadsValue === null || maxDownloadsValue === undefined) {
                // If empty, use existing value or default to 10
                maxDownloads = existingPlan.max_downloads_per_month !== undefined ? existingPlan.max_downloads_per_month : 10;
            } else {
                const parsed = parseInt(maxDownloadsValue, 10);
                if (isNaN(parsed)) {
                    // Invalid input, use existing value or default
                    maxDownloads = existingPlan.max_downloads_per_month !== undefined ? existingPlan.max_downloads_per_month : 10;
                } else {
                    // Valid number (can be -1 for unlimited, 0, or positive number)
                    maxDownloads = parsed;
                }
            }
            
            const featuresInput = document.getElementById('planFeatures');
            const featuresValue = featuresInput ? featuresInput.value : '';
            const features = featuresValue ? featuresValue.split(',').map(f => f.trim()).filter(f => f) : [];
            
            // Collect per-template download limits
            const templateLimits = {};
            const modalElement = document.getElementById('editPlanModal');
            if (modalElement) {
                const checkedBoxes = modalElement.querySelectorAll('.template-checkbox:checked');
                checkedBoxes.forEach(checkbox => {
                    const templateId = checkbox.getAttribute('data-template-id');
                    if (templateId) {
                        const limitInput = modalElement.querySelector(`.template-limit-input[data-template-id="${templateId}"]`);
                        if (limitInput && limitInput.value.trim() !== '') {
                            const limitValue = parseInt(limitInput.value.trim(), 10);
                            if (!isNaN(limitValue) && limitValue > 0) {
                                templateLimits[templateId] = limitValue;
                            }
                        }
                    }
                });
            }
            console.log('[savePlan] 📋 Collected template limits:', templateLimits);
            
            if (!this.allPlans || !this.allPlans[planId]) {
                this.showToast('error', 'Error', 'Plan not found');
                return;
            }
            
            // Prepare plan data to send - only send changed fields
            const planDataToSave = {
                template_limits: templateLimits,
                can_download: canDownload,
                max_downloads_per_month: maxDownloads,
                features: features
            };
            
            // Preserve existing plan fields (use existingPlan already defined above)
            if (existingPlan.name) planDataToSave.name = existingPlan.name;
            if (existingPlan.description) planDataToSave.description = existingPlan.description;
            if (existingPlan.monthly_price !== undefined) planDataToSave.monthly_price = existingPlan.monthly_price;
            if (existingPlan.annual_price !== undefined) planDataToSave.annual_price = existingPlan.annual_price;
            if (existingPlan.plan_tier) planDataToSave.plan_tier = existingPlan.plan_tier;
            
            console.log('[savePlan] 💾 Saving plan:', planId, planDataToSave);
            
            // Get the actual plan_tier or UUID to send to backend
            // Backend expects plan_tier (like "basic", "professional", "enterprise") or UUID
            const planToUpdate = this.allPlans[planId] || plan;
            const backendPlanId = planToUpdate.plan_tier || planToUpdate.id || planId;
            console.log('[savePlan] 📋 Using backend plan ID:', backendPlanId, '(original planId:', planId, ')');
            
            // Save to API
            const data = await this.apiJson('/update-plan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    plan_id: backendPlanId,
                    plan_data: planDataToSave
                })
            });
            
            if (data && data.success) {
                console.log('[savePlan] ✅ Plan saved successfully');
                console.log('[savePlan] 📋 Response data:', JSON.stringify(data, null, 2));
                this.showToast('success', 'Success', 'Plan updated successfully!');
                
                // Update local copy with returned data if available
                if (data.plan_data) {
                    if (!this.allPlans) {
                        this.allPlans = {};
                    }
                    // CRITICAL: Use plan_tier as key if planId was a tier, otherwise use planId
                    const planKey = data.plan_data.plan_tier || planId;
                    this.allPlans[planKey] = data.plan_data;
                    // Also update by original planId for compatibility
                    this.allPlans[planId] = data.plan_data;
                    console.log('[savePlan] ✅ Updated local plan copy:', this.allPlans[planKey]);
                }
                
                // Close modal first
                const modalElement = document.getElementById('editPlanModal');
                if (modalElement) {
                    const modal = bootstrap.Modal.getInstance(modalElement);
                    if (modal) {
                        modal.hide();
                    }
                    // Remove modal after hiding
                    setTimeout(() => {
                        if (modalElement.parentNode) {
                            modalElement.remove();
                        }
                    }, 300);
                }
                
                // CRITICAL: Force reload plans from database to get latest data
                console.log('[savePlan] 🔄 Reloading plans after save...');
                console.log('[savePlan] 📋 Response plan_data:', JSON.stringify(data.plan_data, null, 2));
                
                // Update local copy immediately with response data
                if (data.plan_data) {
                    const responsePlanId = data.plan_data.plan_tier || data.plan_data.id || planId;
                    if (!this.allPlans) {
                        this.allPlans = {};
                    }
                    // Update by multiple keys for compatibility
                    this.allPlans[responsePlanId] = data.plan_data;
                    this.allPlans[planId] = data.plan_data;
                    if (data.plan_data.plan_tier) {
                        this.allPlans[data.plan_data.plan_tier] = data.plan_data;
                    }
                    console.log('[savePlan] ✅ Updated local plan copy immediately:', responsePlanId, 'can_download:', data.plan_data.can_download);
                    
                    // Force immediate display update with saved data
                    this.displayPlans(this.allPlans);
                }
                
                // Wait a moment for database to be ready, then reload from database
                await new Promise(resolve => setTimeout(resolve, 800));
                
                // Force reload with cache busting to get latest from database
                await this.loadPlans(true);
                
                // Wait for display to update
                await new Promise(resolve => setTimeout(resolve, 300));
                
                // Force a visual refresh and scroll to the updated plan
                setTimeout(() => {
                    const container = document.getElementById('plansList');
                    if (container) {
                        container.style.opacity = '0.5';
                        setTimeout(() => {
                            container.style.opacity = '1';
                            // Scroll to the plan that was just edited
                            const planCard = container.querySelector(`[onclick*="editPlan('${planId}')"]`)?.closest('.card') ||
                                           container.querySelector(`[onclick*="editPlan('${data.plan_data?.plan_tier || planId}')"]`)?.closest('.card');
                            if (planCard) {
                                planCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                // Highlight the card briefly
                                planCard.style.transition = 'box-shadow 0.3s';
                                planCard.style.boxShadow = '0 0 20px rgba(0, 123, 255, 0.5)';
                                setTimeout(() => {
                                    planCard.style.boxShadow = '';
                                }, 2000);
                            }
                        }, 200);
                    }
                }, 100);
            } else {
                console.error('[savePlan] ❌ Save failed - no success response:', data);
                this.showToast('error', 'Error', 'Failed to update plan');
            }
        } catch (error) {
            console.error('Error saving plan:', error);
            this.showToast('error', 'Save Failed', error.message);
        }
    }

    async editBrokerMembership(brokerId) {
        if (!this.ensureAuthenticated()) return;
        
        console.log('[editBrokerMembership] 📝 Opening editor for broker membership:', brokerId);
        
        // Reload plans and templates
        try {
            await this.loadPlans(true);
            await new Promise(resolve => setTimeout(resolve, 100));
            await this.loadTemplates();
        } catch (error) {
            console.error('[editBrokerMembership] ❌ Failed to reload data:', error);
            this.showToast('error', 'Error', 'Failed to reload data. Please refresh the page.');
            return;
        }
        
        // Get broker membership data
        const broker = this.allPlans && this.allPlans[brokerId] ? this.allPlans[brokerId] : null;
        if (!broker) {
            console.error('[editBrokerMembership] ❌ Broker membership not found:', brokerId);
            this.showToast('error', 'Error', `Broker membership "${brokerId}" not found`);
            return;
        }
        
        // Use full template objects (with IDs) instead of just names
        let templates = [];
        if (this.templates && this.templates.length > 0 && typeof this.templates[0] === 'object' && this.templates[0].id) {
            templates = this.templates;
        } else {
            templates = this.allTemplates || [];
        }
        
        const canDownload = broker.can_download || [];
        const canDownloadList = Array.isArray(canDownload) ? canDownload : [canDownload];
        const hasAllTemplates = canDownloadList.length === 1 && canDownloadList[0] === '*';
        const templateLimits = broker.template_limits || {};
        
        // Create modal HTML (similar to editPlan but for broker)
        const modalHtml = `
            <div class="modal fade" id="editBrokerModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-warning">
                            <h5 class="modal-title"><i class="fas fa-crown me-2"></i>Edit Broker Membership</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <label class="form-label"><strong>Allowed Templates:</strong></label>
                                <div class="mb-2">
                                    <label class="form-check">
                                        <input type="radio" name="brokerAccessType" value="all" class="form-check-input" ${hasAllTemplates ? 'checked' : ''} onchange="cms.toggleBrokerTemplateSelection()">
                                        <span>All templates (unlimited)</span>
                                    </label>
                                </div>
                                <div class="mb-2">
                                    <label class="form-check">
                                        <input type="radio" name="brokerAccessType" value="specific" class="form-check-input" ${!hasAllTemplates ? 'checked' : ''} onchange="cms.toggleBrokerTemplateSelection()">
                                        <span>Specific templates</span>
                                    </label>
                                </div>
                            </div>
                            <div id="brokerTemplateSelection" class="mb-3 border rounded p-3" style="max-height: 300px; overflow-y: auto; ${hasAllTemplates ? 'display:none;' : 'display:block;'}">
                                <p class="mb-2"><strong>Select templates:</strong></p>
                                ${templates.length > 0 ? templates.map(t => {
                                    let templateName = '';
                                    if (typeof t === 'string') {
                                        templateName = t.endsWith('.docx') ? t : `${t}.docx`;
                                    } else {
                                        templateName = t.name || t.file_with_extension || t.file_name || '';
                                        if (templateName && !templateName.endsWith('.docx')) {
                                            templateName = `${templateName}.docx`;
                                        }
                                    }
                                    // Get template ID if available
                                    let templateId = '';
                                    if (typeof t === 'object') {
                                        templateId = t.id || t.template_id || '';
                                    }
                                    
                                    const normalizedTemplateName = templateName.toLowerCase().endsWith('.docx') ? templateName.toLowerCase() : `${templateName.toLowerCase()}.docx`;
                                    const templateNameWithoutExt = normalizedTemplateName.replace('.docx', '');
                                    const isChecked = canDownloadList.some(allowed => {
                                        if (!allowed || allowed === '*') return false;
                                        const normalizedAllowed = allowed.toLowerCase().endsWith('.docx') ? allowed.toLowerCase() : `${allowed.toLowerCase()}.docx`;
                                        const allowedWithoutExt = normalizedAllowed.replace('.docx', '');
                                        return normalizedAllowed === normalizedTemplateName || 
                                               allowedWithoutExt === templateNameWithoutExt ||
                                               allowed.toLowerCase() === templateNameWithoutExt;
                                    });
                                    const displayName = typeof t === 'string' ? t : (t.metadata?.display_name || t.title || t.name || templateName).replace('.docx', '');
                                    const existingLimit = templateId ? (templateLimits[templateId] || templateLimits[String(templateId)] || '') : '';
                                    
                                    return `
                                        <div class="d-flex align-items-center mb-2 border-bottom pb-2">
                                            <div class="form-check flex-grow-1">
                                                <input type="checkbox" class="form-check-input broker-template-checkbox" value="${templateName}" 
                                                    data-template-id="${templateId}"
                                                    ${isChecked ? 'checked' : ''}>
                                                <label class="form-check-label">${displayName}</label>
                                            </div>
                                            <div class="ms-3" style="width: 150px;">
                                                <input type="number" class="form-control form-control-sm broker-template-limit-input" 
                                                    data-template-id="${templateId}"
                                                    placeholder="Limit" 
                                                    value="${existingLimit}"
                                                    min="1"
                                                    ${!isChecked ? 'disabled' : ''}>
                                                <small class="text-muted d-block" style="font-size: 0.75rem;">Per-template limit</small>
                                            </div>
                                        </div>
                                    `;
                                }).join('') : '<p class="text-muted">No templates available. Please upload templates first.</p>'}
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-warning" onclick="cms.saveBrokerMembership('${brokerId}')">
                                <i class="fas fa-save me-1"></i>Save Changes
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove existing modal if any
        const existingModal = document.getElementById('editBrokerModal');
        if (existingModal) existingModal.remove();
        
        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('editBrokerModal'));
        modal.show();
        
        // Add event listeners for template checkboxes
        const modalElement = document.getElementById('editBrokerModal');
        if (modalElement) {
            const checkboxes = modalElement.querySelectorAll('.broker-template-checkbox');
            checkboxes.forEach(checkbox => {
                checkbox.addEventListener('change', function() {
                    const templateId = this.getAttribute('data-template-id');
                    const limitInput = modalElement.querySelector(`.broker-template-limit-input[data-template-id="${templateId}"]`);
                    if (limitInput) {
                        limitInput.disabled = !this.checked;
                        if (!this.checked) {
                            limitInput.value = '';
                        }
                    }
                });
            });
        }
        
        // Clean up modal when hidden
        document.getElementById('editBrokerModal').addEventListener('hidden.bs.modal', function() {
            this.remove();
        });
    }
    
    toggleBrokerTemplateSelection() {
        const modalElement = document.getElementById('editBrokerModal');
        const specificRadio = modalElement ? 
            modalElement.querySelector('input[name="brokerAccessType"][value="specific"]') :
            document.querySelector('input[name="brokerAccessType"][value="specific"]');
        const templateSelection = document.getElementById('brokerTemplateSelection');
        
        if (templateSelection && specificRadio) {
            templateSelection.style.display = specificRadio.checked ? 'block' : 'none';
        }
    }
    
    async saveBrokerMembership(brokerId) {
        if (!this.ensureAuthenticated()) return;
        try {
            const accessTypeRadio = document.querySelector('input[name="brokerAccessType"]:checked');
            if (!accessTypeRadio) {
                this.showToast('error', 'Error', 'Please select access type');
                return;
            }
            
            const accessType = accessTypeRadio.value;
            let canDownload = [];
            
            if (accessType === 'all') {
                canDownload = ['*'];
            } else {
                const modalElement = document.getElementById('editBrokerModal');
                const checkboxes = modalElement ? 
                    modalElement.querySelectorAll('.broker-template-checkbox:checked') : 
                    document.querySelectorAll('.broker-template-checkbox:checked');
                
                canDownload = Array.from(checkboxes).map(cb => cb.value).filter(v => v);
                
                if (canDownload.length === 0) {
                    this.showToast('error', 'Error', 'Please select at least one template');
                    return;
                }
            }
            
            // Collect per-template download limits
            const templateLimits = {};
            const modalElement = document.getElementById('editBrokerModal');
            if (modalElement) {
                const checkedBoxes = modalElement.querySelectorAll('.broker-template-checkbox:checked');
                checkedBoxes.forEach(checkbox => {
                    const templateId = checkbox.getAttribute('data-template-id');
                    if (templateId) {
                        const limitInput = modalElement.querySelector(`.broker-template-limit-input[data-template-id="${templateId}"]`);
                        if (limitInput && limitInput.value.trim() !== '') {
                            const limitValue = parseInt(limitInput.value.trim(), 10);
                            if (!isNaN(limitValue) && limitValue > 0) {
                                templateLimits[templateId] = limitValue;
                            }
                        }
                    }
                });
            }
            
            const membershipDataToSave = {
                can_download: canDownload,
                template_limits: templateLimits
            };
            
            console.log('[saveBrokerMembership] 💾 Saving broker membership:', brokerId, membershipDataToSave);
            
            const data = await this.apiJson('/update-broker-membership', {
                method: 'POST',
                body: JSON.stringify({
                    membership_data: membershipDataToSave
                })
            });
            
            if (data && data.success) {
                this.showToast('success', 'Success', 'Broker membership updated successfully!');
                
                // Update local copy
                if (data.membership_data) {
                    if (!this.allPlans) {
                        this.allPlans = {};
                    }
                    this.allPlans[brokerId] = data.membership_data;
                }
                
                // Close modal
                const modalElement = document.getElementById('editBrokerModal');
                if (modalElement) {
                    const modal = bootstrap.Modal.getInstance(modalElement);
                    if (modal) {
                        modal.hide();
                    }
                    setTimeout(() => {
                        if (modalElement.parentNode) {
                            modalElement.remove();
                        }
                    }, 300);
                }
                
                // Reload plans
                await this.loadPlans(true);
            } else {
                this.showToast('error', 'Error', 'Failed to update broker membership');
            }
        } catch (error) {
            console.error('Error saving broker membership:', error);
            this.showToast('error', 'Save Failed', error.message);
        }
    }

    // ========================================================================
    // Utilities
    // ========================================================================

    formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    formatTemplateLabel(name) {
        if (!name) return '';
        if (name === '*') return 'All templates';
        return name.replace(/\.docx$/i, '');
    }

    showToast(type, title, message) {
        const toast = document.getElementById('toast');
        const toastTitle = document.getElementById('toastTitle');
        const toastMessage = document.getElementById('toastMessage');
        
        toastTitle.textContent = title;
        toastMessage.textContent = message;
        
        // Set toast color
        toast.className = 'toast';
        if (type === 'success') {
            toast.querySelector('.toast-header').className = 'toast-header bg-success text-white';
        } else if (type === 'error') {
            toast.querySelector('.toast-header').className = 'toast-header bg-danger text-white';
        } else {
            toast.querySelector('.toast-header').className = 'toast-header';
        }
        
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
    }
}

// Global instance
const cms = new DocumentCMS();

// Login handler
async function handleLogin(event) {
    event.preventDefault();
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const errorDiv = document.getElementById('loginError');
    
    errorDiv.classList.add('d-none');
    const success = await cms.login(username, password);
    
    if (success) {
        const modal = bootstrap.Modal.getInstance(document.getElementById('loginModal'));
        if (modal) modal.hide();
    } else {
        errorDiv.textContent = 'Invalid username or password';
        errorDiv.classList.remove('d-none');
    }
}
