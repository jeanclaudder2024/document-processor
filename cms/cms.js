// Document Processor CMS - Clean Frontend
class DocumentCMS {
    constructor() {
        this.apiBaseUrl = 'http://localhost:8000';
        this.selectedFile = null;
        this.selectedCSV = null;
        this.init();
    }

    init() {
        // this.checkLoginStatus();  // Disabled for now
        this.checkApiStatus();
        this.loadTemplates();
        this.loadDataSources();
        this.loadPlans();
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
        this.showToast('error', 'Session Expired', 'Please login again');
        this.updateLoginUI(false);
    }

    // ========================================================================
    // Authentication
    // ========================================================================

    async checkLoginStatus() {
        try {
            const data = await this.apiJson('/auth/me');
            console.log('Session check:', data);
            if (data && data.user) {
                this.updateLoginUI(true, data.user);
            } else {
                this.updateLoginUI(false);
            }
        } catch (error) {
            console.log('No session:', error.message);
            this.updateLoginUI(false);
        }
    }

    async login(username, password) {
        try {
            console.log('Attempting login...');
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
            console.log('Login response:', data);
            
            if (data && data.success) {
                // Verify session is working
                await this.checkLoginStatus();
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
            this.updateLoginUI(false);
            this.showToast('success', 'Logged Out', 'You have been logged out');
        } catch (error) {
            this.showToast('error', 'Logout Failed', error.message);
        }
    }

    updateLoginUI(isLoggedIn, username = null) {
        const userInfo = document.getElementById('userInfo');
        const loginBtn = document.getElementById('loginBtn');
        const logoutBtn = document.getElementById('logoutBtn');
        
        if (isLoggedIn) {
            userInfo.textContent = `User: ${username}`;
            loginBtn.classList.add('d-none');
            logoutBtn.classList.remove('d-none');
        } else {
            userInfo.textContent = 'Not logged in';
            loginBtn.classList.remove('d-none');
            logoutBtn.classList.add('d-none');
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
        try {
            const data = await this.apiJson('/templates');
            if (data && data.templates) {
                this.templates = data.templates;
                // Build template name list for plan editing - use file_name (without .docx) for consistency
                this.allTemplates = data.templates.map(t => {
                    if (typeof t === 'string') {
                        // If it's a string, remove .docx extension if present
                        return t.replace(/\.docx$/i, '');
                    }
                    // Prefer file_name (without extension) for plan permissions
                    if (t.file_name) {
                        return t.file_name;
                    }
                    // Fallback to name with .docx removed
                    if (t.name) {
                        return t.name.replace(/\.docx$/i, '');
                    }
                    // Other fallbacks
                    return t.title || String(t);
                }).filter(t => t && t.trim() !== ''); // Remove empty values
                console.log('Loaded templates:', this.allTemplates.length, 'templates:', this.allTemplates);
                this.displayTemplates(data.templates);
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
        
        if (templates.length === 0) {
            container.innerHTML = '<div class="text-center text-muted py-4">No templates found</div>';
            return;
        }
        
        container.innerHTML = templates.map(template => `
            <div class="template-card card mb-3">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h5 class="mb-2">
                                <i class="fas fa-file-word text-primary me-2"></i>
                                ${template.name}
                            </h5>
                            <div class="text-muted small mb-2">
                                <i class="fas fa-file me-1"></i>${this.formatBytes(template.size)} | 
                                <i class="fas fa-tags me-1"></i>${template.placeholder_count} placeholders
                            </div>
                            <div class="mb-2">
                                ${template.placeholders.slice(0, 10).map(p => 
                                    `<span class="placeholder-badge">${p}</span>`
                                ).join('')}
                                ${template.placeholders.length > 10 ? `<span class="text-muted">+${template.placeholders.length - 10} more</span>` : ''}
                            </div>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-success me-2" onclick="cms.testGenerateDocument('${template.name}')">
                                <i class="fas fa-vial me-1"></i>Test
                            </button>
                            <button class="btn btn-sm btn-primary me-2" onclick="window.open('editor.html?template=${encodeURIComponent(template.name)}', '_blank')">
                                <i class="fas fa-edit me-1"></i>Edit
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="cms.deleteTemplate('${template.name}')">
                                <i class="fas fa-trash me-1"></i>Delete
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
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
        if (!this.selectedFile) {
            this.showToast('error', 'No File', 'Please select a file first');
            return;
        }

        const formData = new FormData();
        formData.append('file', this.selectedFile);

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
                this.loadTemplates();
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
        if (!confirm(`Delete template "${templateName}"?`)) return;

        try {
            const response = await this.apiFetch(`/templates/${encodeURIComponent(templateName)}`, {
                method: 'DELETE'
            });
            
            if (response && response.ok) {
                const data = await response.json();
                if (data && data.success) {
                    this.showToast('success', 'Deleted', `Template "${templateName}" deleted`);
                    this.loadTemplates();
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
        container.innerHTML = Object.entries(sources).map(([name, source]) => `
            <div class="card mb-3">
                <div class="card-body">
                    <h6 class="mb-2">
                        <i class="fas fa-database me-2"></i>${name.replace('_', ' ').toUpperCase()}
                    </h6>
                    <div class="small">
                        <div><strong>File:</strong> ${source.filename}</div>
                        <div><strong>Status:</strong> ${source.exists ? '<span class="text-success">✓ Available</span>' : '<span class="text-danger">✗ Missing</span>'}</div>
                        ${source.exists ? `<div><strong>Size:</strong> ${this.formatBytes(source.size)}</div>` : ''}
                        ${source.exists ? `<div><strong>Rows:</strong> ${source.row_count}</div>` : ''}
                    </div>
                </div>
            </div>
        `).join('');
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
        if (!this.selectedCSV) {
            this.showToast('error', 'No File', 'Please select a CSV file first');
            return;
        }

        const dataType = document.getElementById('csvDataType').value;
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
                this.showToast('success', 'Upload Success', `CSV "${data.filename}" uploaded`);
                this.selectedCSV = null;
                document.getElementById('csvUploadArea').innerHTML = `
                    <i class="fas fa-file-csv fa-3x text-muted mb-3"></i>
                    <h5>Drop CSV file here</h5>
                    <p class="text-muted mb-0">or click to browse</p>
                `;
                document.getElementById('csvFile').value = '';
                this.loadDataSources();
            } else {
                const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
                throw new Error(error.detail);
            }
        } catch (error) {
            this.showToast('error', 'Upload Failed', error.message);
        }
    }

    // ========================================================================
    // Plans
    // ========================================================================

    async loadPlans() {
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
            } else {
                console.warn('No plans data received');
                this.displayPlans({});
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
                            `<span class="badge bg-info ms-2">${canDownloadList.length} templates</span>`
                        }
                        ${!isAllTemplates && canDownloadList.length > 0 ? 
                            `<ul class="mb-0 mt-2"><li><small>${canDownloadList.map(t => t.replace('.docx', '')).join('</small></li><li><small>')}</small></li></ul>` : ''
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
        // Ensure templates are loaded
        if (this.templates && Array.isArray(this.templates)) {
            this.allTemplates = this.templates.map(t => t.name || t.file_name || t);
        } else {
            this.allTemplates = [];
        }
    }

    async testPermission() {
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
        if (!this.allPlans || !this.allPlans[planId]) {
            this.showToast('error', 'Error', 'Plan not found');
            return;
        }
        
        // Ensure templates are loaded - reload if not available
        if (!this.templates || this.templates.length === 0 || !this.allTemplates || this.allTemplates.length === 0) {
            try {
                console.log('Templates not loaded, fetching...');
                await this.loadTemplates();
            } catch (error) {
                console.error('Failed to load templates:', error);
                this.showToast('error', 'Error', 'Failed to load templates');
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
                                    const templateName = typeof t === 'string' ? t : (t.name || t.file_name || '');
                                    const isChecked = plan.can_download && Array.isArray(plan.can_download) && plan.can_download.includes(templateName);
                                    return `
                                        <div class="form-check mb-2">
                                            <input type="checkbox" class="form-check-input template-checkbox" value="${templateName}" 
                                                ${isChecked ? 'checked' : ''}>
                                            <label class="form-check-label">${templateName}</label>
                                        </div>
                                    `;
                                }).join('') : '<p class="text-muted">No templates available. Please upload templates first.</p>'}
                            </div>
                            <div class="mb-3">
                                <label class="form-label"><strong>Max Downloads Per Month:</strong></label>
                                <input type="number" class="form-control" id="maxDownloads" value="${plan.max_downloads_per_month}" placeholder="Use -1 for unlimited">
                                <small class="text-muted">Enter -1 for unlimited downloads</small>
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
            const maxDownloads = parseInt(maxDownloadsInput.value) || 10;
            
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
