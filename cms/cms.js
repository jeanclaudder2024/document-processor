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

        const modal = new bootstrap.Modal(modalEl);
        modal.show();
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

        const payload = {
            display_name: displayInput ? displayInput.value : '',
            description: descriptionInput ? descriptionInput.value : '',
            font_family: fontFamilyInput ? fontFamilyInput.value : '',
            font_size: fontSizeInput ? fontSizeInput.value : ''
        };

        try {
            const data = await this.apiJson(`/templates/${encodeURIComponent(this.activeTemplateMetadata)}/metadata`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            if (data && data.success) {
                const template = this.findTemplateByName(this.activeTemplateMetadata);
                if (template) {
                    template.metadata = template.metadata || {};
                    Object.assign(template.metadata, data.metadata || {});
                    if (data.metadata?.display_name) {
                        template.title = data.metadata.display_name;
                    }
                    if (data.metadata?.description) {
                        template.description = data.metadata.description;
                    }
                }

                // Force reload templates to get updated metadata from backend
                await this.loadTemplates();
                this.showToast('success', 'Metadata Saved', 'Template details updated successfully');

                const modalEl = document.getElementById('templateMetaModal');
                if (modalEl) {
                    const modal = bootstrap.Modal.getInstance(modalEl);
                    if (modal) modal.hide();
                }
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
            const data = await this.apiJson('/templates');
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

    async loadPlans() {
        if (!this.ensureAuthenticated(false)) return;
        try {
            // Try JSON first (more reliable for immediate updates)
            let data = null;
            let source = 'unknown';
            
            try {
                // Try JSON endpoint first for consistency
                data = await this.apiJson('/plans');
                source = 'json';
                console.log('Loaded plans from JSON:', Object.keys(data.plans || {}).length, 'plans');
            } catch (e) {
                console.warn('Failed to load plans from JSON, trying database:', e);
                // Fallback to database
                try {
                    data = await this.apiJson('/plans-db');
                    source = 'database';
                    console.log('Loaded plans from database:', Object.keys(data.plans || {}).length, 'plans');
                } catch (e2) {
                    console.error('Failed to load plans from database:', e2);
                    this.showToast('error', 'Load Error', 'Failed to load plans. Using empty list.');
                    data = { plans: {} };
                }
            }
            
            if (data && data.plans) {
                console.log('Displaying plans from', source, ':', Object.keys(data.plans));
                this.displayPlans(data.plans);
                // Update plan checkboxes in upload form
                this.populatePlanCheckboxes();
            } else {
                console.warn('No plans data received');
                this.displayPlans({});
                this.populatePlanCheckboxes();
            }
        } catch (error) {
            console.error('Error loading plans:', error);
            this.showToast('error', 'Load Error', `Failed to load plans: ${error.message}`);
            this.displayPlans({});
        }
    }

    displayPlans(plans) {
        const container = document.getElementById('plansList');
        if (!container) {
            console.error('plansList container not found');
            return;
        }
        
        container.innerHTML = Object.entries(plans).map(([planId, plan]) => {
            const canDownload = plan.can_download || [];
            const canDownloadList = Array.isArray(canDownload) ? canDownload : [canDownload];
            const isAllTemplates = canDownloadList.length === 1 && canDownloadList[0] === '*';
            const maxDownloads = plan.max_downloads_per_month !== undefined ? plan.max_downloads_per_month : 10;
            const features = Array.isArray(plan.features) ? plan.features : [];
            
            return `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h5 class="mb-0">${plan.name || planId}</h5>
                        <button class="btn btn-sm btn-outline-primary" onclick="cms.editPlan('${planId}')">
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
        
        // Store plans for editing
        this.allPlans = plans;
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

    async testPermission() {
        if (!this.ensureAuthenticated()) return;
        const userId = document.getElementById('testUserId').value;
        const templateName = document.getElementById('testTemplate').value;

        if (!templateName) {
            this.showToast('error', 'Missing Info', 'Please enter template name');
            return;
        }

        try {
            const data = await this.apiJson('/check-download-permission', {
                method: 'POST',
                body: JSON.stringify({ user_id: userId, template_name: templateName })
            });

            if (data) {
                const resultDiv = document.getElementById('permissionResult');
                resultDiv.innerHTML = `
                    <div class="alert alert-${data.can_download ? 'success' : 'warning'}">
                        <strong>Result:</strong> ${data.can_download ? '✓ Can Download' : '✗ Cannot Download'}<br>
                        <small>User: ${data.user_id} | Plan: ${data.plan} | Template: ${data.template_name}</small>
                    </div>
                `;
            }
        } catch (error) {
            this.showToast('error', 'Permission Check Failed', error.message);
        }
    }

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
        if (!this.allPlans || !this.allPlans[planId]) {
            this.showToast('error', 'Error', 'Plan not found');
            return;
        }
        
        // Always reload templates to ensure we have the latest list
        try {
            console.log('Loading templates for plan editor...');
            await this.loadTemplates();
            console.log('Templates loaded:', this.templates ? this.templates.length : 0);
            console.log('allTemplates:', this.allTemplates ? this.allTemplates.length : 0);
        } catch (error) {
            console.error('Failed to load templates:', error);
            this.showToast('error', 'Error', 'Failed to load templates. Please refresh the page.');
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
        
        const plan = this.allPlans[planId];
        const templates = this.allTemplates || [];
        
        console.log('Editing plan:', planId);
        console.log('Plan:', plan);
        console.log('Templates available:', templates.length, templates);
        console.log('Stored templates:', this.templates ? this.templates.length : 0);
        
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
                                        <input type="radio" name="accessType" value="specific" class="form-check-input" ${plan.can_download && plan.can_download[0] !== '*' ? 'checked' : ''} onchange="cms.toggleTemplateSelection()">
                                        <span>Specific templates</span>
                                    </label>
                                </div>
                            </div>
                            <div id="templateSelection" class="mb-3 border rounded p-3" style="max-height: 300px; overflow-y: auto; ${plan.can_download && plan.can_download[0] === '*' ? 'display:none;' : ''}">
                                <p class="mb-2"><strong>Select templates:</strong></p>
                                ${templates.length > 0 ? templates.map(t => {
                                    // Normalize template name - ensure consistent format
                                    let templateName = '';
                                    if (typeof t === 'string') {
                                        templateName = t.endsWith('.docx') ? t : `${t}.docx`;
                                    } else {
                                        templateName = t.name || t.file_with_extension || t.file_name || '';
                                        if (templateName && !templateName.endsWith('.docx')) {
                                            templateName = `${templateName}.docx`;
                                        }
                                    }
                                    // Check if this template is in the plan's can_download list
                                    const canDownloadList = plan.can_download && Array.isArray(plan.can_download) ? plan.can_download : [];
                                    // Normalize comparison - check both with and without .docx
                                    const isChecked = canDownloadList.some(allowed => {
                                        const normalizedAllowed = allowed.endsWith('.docx') ? allowed : `${allowed}.docx`;
                                        const normalizedTemplate = templateName.endsWith('.docx') ? templateName : `${templateName}.docx`;
                                        return normalizedAllowed === normalizedTemplate || allowed === '*' || allowed === templateName.replace('.docx', '');
                                    });
                                    const displayName = typeof t === 'string' ? t : (t.metadata?.display_name || t.title || t.name || templateName).replace('.docx', '');
                                    return `
                                        <div class="form-check mb-2">
                                            <input type="checkbox" class="form-check-input template-checkbox" value="${templateName}" 
                                                ${isChecked ? 'checked' : ''}>
                                            <label class="form-check-label">${displayName}</label>
                                        </div>
                                    `;
                                }).join('') : '<p class="text-muted">No templates available. Please upload templates first.</p>'}
                            </div>
                            <div class="mb-3">
                                <label class="form-label"><strong>Max Downloads Per Month:</strong></label>
                                <input type="number" class="form-control" id="maxDownloads" value="${plan.max_downloads_per_month !== undefined && plan.max_downloads_per_month !== null ? plan.max_downloads_per_month : ''}" placeholder="Use -1 for unlimited, or enter a number">
                                <small class="text-muted">Enter -1 for unlimited downloads, or a number for the monthly limit</small>
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
        
        // Clean up modal when hidden
        document.getElementById('editPlanModal').addEventListener('hidden.bs.modal', function() {
            this.remove();
        });
    }
    
    toggleTemplateSelection() {
        const specificRadio = document.querySelector('input[name="accessType"][value="specific"]');
        const templateSelection = document.getElementById('templateSelection');
        if (templateSelection) {
            templateSelection.style.display = specificRadio.checked ? 'block' : 'none';
        }
    }
    
    async savePlan(planId) {
        if (!this.ensureAuthenticated()) return;
        try {
            const accessTypeRadio = document.querySelector('input[name="accessType"]:checked');
            if (!accessTypeRadio) {
                this.showToast('error', 'Error', 'Please select access type');
                return;
            }
            
            const accessType = accessTypeRadio.value;
            let canDownload = [];
            
            if (accessType === 'all') {
                canDownload = ['*'];
            } else {
                const checkboxes = document.querySelectorAll('.template-checkbox:checked');
                canDownload = Array.from(checkboxes).map(cb => cb.value).filter(v => v);
                
                if (canDownload.length === 0) {
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
            if (maxDownloadsValue === '' || maxDownloadsValue === null || maxDownloadsValue === undefined) {
                // If empty, use existing value or default to 10
                maxDownloads = plan.max_downloads_per_month !== undefined ? plan.max_downloads_per_month : 10;
            } else {
                const parsed = parseInt(maxDownloadsValue, 10);
                if (isNaN(parsed)) {
                    // Invalid input, use existing value or default
                    maxDownloads = plan.max_downloads_per_month !== undefined ? plan.max_downloads_per_month : 10;
                } else {
                    // Valid number (can be -1 for unlimited, 0, or positive number)
                    maxDownloads = parsed;
                }
            }
            
            const featuresInput = document.getElementById('planFeatures');
            const featuresValue = featuresInput ? featuresInput.value : '';
            const features = featuresValue ? featuresValue.split(',').map(f => f.trim()).filter(f => f) : [];
            
            if (!this.allPlans || !this.allPlans[planId]) {
                this.showToast('error', 'Error', 'Plan not found');
                return;
            }
            
            // Prepare plan data to send - only send changed fields
            const planDataToSave = {
                can_download: canDownload,
                max_downloads_per_month: maxDownloads,
                features: features
            };
            
            // Preserve existing plan fields
            const existingPlan = this.allPlans[planId] || {};
            if (existingPlan.name) planDataToSave.name = existingPlan.name;
            if (existingPlan.description) planDataToSave.description = existingPlan.description;
            if (existingPlan.monthly_price !== undefined) planDataToSave.monthly_price = existingPlan.monthly_price;
            if (existingPlan.annual_price !== undefined) planDataToSave.annual_price = existingPlan.annual_price;
            if (existingPlan.plan_tier) planDataToSave.plan_tier = existingPlan.plan_tier;
            
            console.log('Saving plan:', planId, planDataToSave);
            
            // Save to API
            const data = await this.apiJson('/update-plan', {
                method: 'POST',
                body: JSON.stringify({
                    plan_id: planId,
                    plan_data: planDataToSave
                })
            });
            
            if (data && data.success) {
                this.showToast('success', 'Success', 'Plan updated successfully!');
                
                // Update local copy with returned data if available
                if (data.plan_data) {
                    this.allPlans[planId] = data.plan_data;
                    console.log('Updated local plan copy:', this.allPlans[planId]);
                }
                
                // Close modal
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
                
                // Force reload plans - clear cache by adding timestamp
                console.log('Reloading plans after save...');
                await this.loadPlans();
                
                // Force a visual refresh
                setTimeout(() => {
                    const container = document.getElementById('plansList');
                    if (container) {
                        container.style.opacity = '0.5';
                        setTimeout(() => {
                            container.style.opacity = '1';
                        }, 200);
                    }
                }, 100);
            } else {
                console.error('Save failed - no success response:', data);
                this.showToast('error', 'Error', 'Failed to update plan');
            }
        } catch (error) {
            console.error('Error saving plan:', error);
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
