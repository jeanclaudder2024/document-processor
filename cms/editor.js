// Template Editor - Rebuilt for new CMS system
class TemplateEditor {
    constructor() {
        const origin = window.location.origin || '';
        const hostname = window.location.hostname || '';
        const protocol = window.location.protocol || 'http:';
        let apiBase = 'http://localhost:8000';

        // Check for explicit API base URL
        if (window.__CMS_API_BASE__) {
            apiBase = window.__CMS_API_BASE__;
        } 
        // If accessing CMS from same origin, use relative path
        else if (hostname === 'localhost' || hostname === '127.0.0.1') {
            apiBase = 'http://localhost:8000';
        } 
        // Production domains
        else if (hostname === 'control.petrodealhub.com' || hostname === 'petrodealhub.com' || hostname === 'www.petrodealhub.com') {
            apiBase = 'https://petrodealhub.com/api';
        } 
        // If CMS is served from /cms/, API should be at root
        else if (window.location.pathname.startsWith('/cms/')) {
            // Remove /cms/ from path and use root
            const baseUrl = origin.replace(/\/cms.*$/, '');
            apiBase = `${baseUrl}/api`;
        }
        // Fallback: try to construct API URL from current origin
        else if (origin && origin.startsWith('http')) {
            apiBase = `${origin.replace(/\/$/, '')}/api`;
        }

        this.apiBaseUrl = apiBase;
        console.log('CMS Editor initialized with API base URL:', this.apiBaseUrl);
        this.currentTemplateId = null;
        this.currentTemplate = null;
        this.currentSettings = {};
        this.placeholders = [];
        this.databaseTables = [];
        this.databaseColumns = {};  // {tableName: [columns]}
        this.csvFiles = [];
        this.csvFields = {};  // {csvId: [fields]}
        this.plans = {};
        this.init();
    }

    async init() {
        console.log('🚀 Initializing CMS Editor...');
        console.log('📍 Current URL:', window.location.href);
        console.log('🌐 API Base URL:', this.apiBaseUrl);
        
        // Get template_id from URL parameter
        const urlParams = new URLSearchParams(window.location.search);
        const templateId = urlParams.get('template_id');
        
        console.log('📋 Template ID from URL:', templateId);
        
        // Load supporting data FIRST (needed for dropdowns)
        console.log('📦 Loading supporting data...');
        try {
            await Promise.all([
                this.loadDatabaseTables(),
                this.loadCsvFiles(),
                this.loadPlans()
            ]);
            console.log('✅ Supporting data loaded');
        } catch (error) {
            console.error('❌ Error loading supporting data:', error);
            this.showError('Failed to load some data. Please refresh the page.');
        }
        
        // Then load template
        if (templateId) {
            await this.loadTemplateById(templateId);
        } else {
            document.getElementById('templateTitle').textContent = 'No template selected';
            document.getElementById('placeholdersContainer').innerHTML = 
                '<div class="alert alert-warning">Please open this editor from the template list with a template selected.</div>';
        }
    }

    async apiJson(path, options = {}) {
        const url = `${this.apiBaseUrl}${path}`;
        const opts = {
            ...options,
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };
        
        console.log(`API Request: ${opts.method || 'GET'} ${url}`);
        
        try {
            const response = await fetch(url, opts);
            console.log(`API Response: ${response.status} ${response.statusText} for ${path}`);
            
            if (!response.ok) {
                const errorText = await response.text();
                let errorData;
                try {
                    errorData = JSON.parse(errorText);
                } catch {
                    errorData = { detail: errorText || `HTTP ${response.status}` };
                }
                console.error(`API Error (${path}):`, errorData);
                throw new Error(errorData.detail || errorData.message || `HTTP ${response.status}`);
            }
            
            const data = await response.json();
            console.log(`API Success (${path}):`, data);
            return data;
        } catch (error) {
            console.error(`API Error (${path}):`, error);
            if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                throw new Error(`Cannot connect to API at ${url}. Please check if the API server is running.`);
            }
            throw error;
        }
    }

    async loadTemplateById(templateId) {
        try {
            // Try to get template by ID
            const templateData = await this.apiJson(`/templates/${encodeURIComponent(templateId)}`);
            if (!templateData) {
                throw new Error('Template not found');
            }

            this.currentTemplateId = templateData.template_id || templateId;
            this.currentTemplate = templateData;
            this.placeholders = templateData.placeholders || [];
            
            // Update UI
            document.getElementById('templateTitle').textContent = 
                templateData.metadata?.display_name || templateData.title || templateData.name || 'Untitled Template';
            
            // Load template settings
            document.getElementById('templateDisplayName').value = 
                templateData.metadata?.display_name || templateData.title || '';
            document.getElementById('templateDescription').value = 
                templateData.metadata?.description || templateData.description || '';
            document.getElementById('templateFontFamily').value = 
                templateData.metadata?.font_family || templateData.font_family || '';
            document.getElementById('templateFontSize').value = 
                templateData.metadata?.font_size || templateData.font_size || '';
            
            // Load placeholder settings
            const settingsData = await this.apiJson(`/placeholder-settings?template_id=${encodeURIComponent(templateId)}`);
            if (settingsData && settingsData.settings) {
                this.currentSettings = settingsData.settings;
            } else {
                this.currentSettings = {};
            }
            
            // Display placeholders
            this.displayPlaceholders();
            
            // Load plan assignments for this template (after plans are loaded)
            if (this.plans && Object.keys(this.plans).length > 0) {
                await this.loadTemplatePlans();
            } else {
                // If plans not loaded yet, load them first
                await this.loadPlans();
                await this.loadTemplatePlans();
            }
        } catch (error) {
            console.error('Failed to load template:', error);
            alert(`Failed to load template: ${error.message}`);
        }
    }

    async loadDatabaseTables() {
        try {
            console.log('🔄 Loading database tables from:', `${this.apiBaseUrl}/database-tables`);
            const data = await this.apiJson('/database-tables');
            console.log('✅ Database tables response:', data);
            if (data && data.tables && Array.isArray(data.tables)) {
                this.databaseTables = data.tables;
                console.log(`✅ Loaded ${data.tables.length} database tables:`, data.tables.map(t => t.name));
                
                // Update UI if dropdowns are already rendered
                this.updateDatabaseTableDropdowns();
            } else {
                console.warn('⚠️ No tables found in response:', data);
                this.databaseTables = [];
                this.showError('Failed to load database tables: Invalid response format');
            }
        } catch (error) {
            console.error('❌ Failed to load database tables:', error);
            this.databaseTables = [];
            this.showError(`Failed to load database tables: ${error.message}`);
        }
    }
    
    updateDatabaseTableDropdowns() {
        // Update all database table dropdowns in the UI
        document.querySelectorAll('select[onchange*="handleDatabaseTableChange"]').forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="">-- Select table --</option>' +
                this.databaseTables.map(t => 
                    `<option value="${t.name}" ${currentValue === t.name ? 'selected' : ''}>
                        ${t.label}${t.description ? ` - ${t.description}` : ''}
                    </option>`
                ).join('');
        });
    }
    
    showError(message) {
        // Show error message in UI
        const errorDiv = document.getElementById('errorMessage');
        if (errorDiv) {
            errorDiv.textContent = message;
            errorDiv.style.display = 'block';
            setTimeout(() => {
                errorDiv.style.display = 'none';
            }, 5000);
        } else {
            console.error('Error:', message);
        }
    }

    async loadTableColumns(tableName) {
        if (this.databaseColumns[tableName]) {
            return this.databaseColumns[tableName];
        }
        
        try {
            const data = await this.apiJson(`/database-tables/${encodeURIComponent(tableName)}/columns`);
            if (data && data.columns) {
                this.databaseColumns[tableName] = data.columns;
                return data.columns;
            }
        } catch (error) {
            console.error(`Failed to load columns for ${tableName}:`, error);
        }
        return [];
    }

    async loadCsvFiles() {
        try {
            console.log('🔄 Loading CSV files from:', `${this.apiBaseUrl}/csv-files`);
            const data = await this.apiJson('/csv-files');
            console.log('✅ CSV files response:', data);
            if (data && data.csv_files && Array.isArray(data.csv_files)) {
                this.csvFiles = data.csv_files;
                console.log(`✅ Loaded ${data.csv_files.length} CSV files:`, data.csv_files.map(f => f.id));
                // Load fields for each CSV
                for (const csvFile of this.csvFiles) {
                    await this.loadCsvFields(csvFile.id);
                }
                // Update UI if dropdowns are already rendered
                this.updateCsvFileDropdowns();
            } else {
                console.warn('⚠️ No CSV files found in response:', data);
                this.csvFiles = [];
            }
        } catch (error) {
            console.error('❌ Failed to load CSV files:', error);
            this.csvFiles = [];
            this.showError(`Failed to load CSV files: ${error.message}`);
        }
    }
    
    updateCsvFileDropdowns() {
        // Update all CSV file dropdowns in the UI
        if (!this.csvFiles || this.csvFiles.length === 0) {
            console.log('⚠️ No CSV files available to update dropdowns');
            return;
        }
        
        document.querySelectorAll('select[id^="csvFile_"]').forEach(select => {
            const currentValue = select.value;
            select.innerHTML = '<option value="">-- Select CSV file --</option>' +
                this.csvFiles.map(f => 
                    `<option value="${f.id}" ${currentValue === f.id ? 'selected' : ''}>
                        ${f.display_name || f.id}
                    </option>`
                ).join('');
        });
        
        // Also update dropdowns with onchange handler
        document.querySelectorAll('select[onchange*="handleCsvFileChange"]').forEach(select => {
            if (select.id && !select.id.startsWith('csvFile_')) {
                const currentValue = select.value;
                select.innerHTML = '<option value="">-- Select CSV file --</option>' +
                    this.csvFiles.map(f => 
                        `<option value="${f.id}" ${currentValue === f.id ? 'selected' : ''}>
                            ${f.display_name || f.id}
                        </option>`
                    ).join('');
            }
        });
    }

    async loadCsvFields(csvId) {
        try {
            const data = await this.apiJson(`/csv-fields/${csvId}`);
            if (data && data.fields) {
                this.csvFields[csvId] = data.fields;
            }
        } catch (error) {
            console.error(`Failed to load CSV fields for ${csvId}:`, error);
        }
    }

    async loadPlans() {
        try {
            const data = await this.apiJson('/plans');
            if (data && data.plans) {
                this.plans = data.plans;
                this.populatePlanCheckboxes();
            }
        } catch (error) {
            console.error('Failed to load plans:', error);
        }
    }

    async loadTemplatePlans() {
        // Load which plans have access to this template
        if (!this.currentTemplateId) {
            this.populatePlanCheckboxes([]);
            return;
        }
        
        try {
            // Get plan assignments for this template
            const data = await this.apiJson(`/templates/${encodeURIComponent(this.currentTemplateId)}/plan-info`);
            if (data && data.plans) {
                const assignedPlanIds = data.plans.map(p => p.plan_id || p.id);
                this.populatePlanCheckboxes(assignedPlanIds);
            } else {
                this.populatePlanCheckboxes([]);
            }
        } catch (error) {
            console.error('Failed to load template plan assignments:', error);
            this.populatePlanCheckboxes([]);
        }
    }

    populatePlanCheckboxes(assignedPlanIds = []) {
        const container = document.getElementById('planCheckboxes');
        if (!container) return;
        
        if (!this.plans || Object.keys(this.plans).length === 0) {
            container.innerHTML = '<div class="text-muted small">Loading plans...</div>';
            return;
        }
        
        container.innerHTML = Object.entries(this.plans).map(([planId, plan]) => {
            const isChecked = assignedPlanIds.includes(planId) || assignedPlanIds.includes(String(planId));
            return `
            <div class="form-check">
                <input type="checkbox" class="form-check-input" id="plan_${planId}" value="${planId}" ${isChecked ? 'checked' : ''}>
                <label class="form-check-label" for="plan_${planId}">
                    ${plan.name || planId}
                </label>
            </div>
        `;
        }).join('');
    }

    displayPlaceholders() {
        const container = document.getElementById('placeholdersContainer');
        
        if (this.placeholders.length === 0) {
            container.innerHTML = '<div class="alert alert-info">No placeholders found in this template.</div>';
            return;
        }

        container.innerHTML = this.placeholders.map(ph => {
            const setting = this.currentSettings[ph] || { 
                source: 'random', 
                customValue: '', 
                databaseTable: '',
                databaseField: '', 
                csvId: '', 
                csvField: '', 
                csvRow: 0, 
                randomOption: 'auto' 
            };
            
            return `
                <div class="placeholder-config" data-placeholder="${ph}">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong><code>${ph}</code></strong>
                        <select class="form-select form-select-sm" style="width: 150px;" 
                                onchange="editor.handleSourceChange('${ph}', this.value)">
                            <option value="random" ${setting.source === 'random' ? 'selected' : ''}>Random</option>
                            <option value="custom" ${setting.source === 'custom' ? 'selected' : ''}>Custom</option>
                            <option value="database" ${setting.source === 'database' ? 'selected' : ''}>Database</option>
                            <option value="csv" ${setting.source === 'csv' ? 'selected' : ''}>CSV</option>
                        </select>
                    </div>
                    
                    <!-- Custom Value -->
                    <div class="source-option ${setting.source === 'custom' ? 'active' : ''}" data-source="custom">
                        <label class="form-label small">Custom Value:</label>
                        <input type="text" class="form-control form-control-sm" 
                               value="${setting.customValue || ''}" 
                               placeholder="Enter custom value..."
                               onchange="editor.updateSetting('${ph}', 'customValue', this.value)">
                    </div>
                    
                    <!-- Database Source -->
                    <div class="source-option ${setting.source === 'database' ? 'active' : ''}" data-source="database">
                        <label class="form-label small">Database Table:</label>
                        <select class="form-select form-select-sm mb-2" id="dbTable_${ph}"
                                onchange="editor.handleDatabaseTableChange('${ph}', this.value)">
                            <option value="">-- Select table --</option>
                            ${(this.databaseTables && this.databaseTables.length > 0) ? this.databaseTables.map(t => 
                                `<option value="${t.name}" ${setting.databaseTable === t.name ? 'selected' : ''}>
                                    ${t.label}${t.description ? ` - ${t.description}` : ''}
                                </option>`
                            ).join('') : '<option value="">Loading tables...</option>'}
                        </select>
                        <label class="form-label small">Database Field:</label>
                        <select class="form-select form-select-sm" id="dbField_${ph}"
                                onchange="editor.updateSetting('${ph}', 'databaseField', this.value)">
                            <option value="">-- Select field --</option>
                        </select>
                    </div>
                    
                    <!-- CSV Source -->
                    <div class="source-option ${setting.source === 'csv' ? 'active' : ''}" data-source="csv">
                        <label class="form-label small">CSV File:</label>
                        <select class="form-select form-select-sm mb-2" id="csvFile_${ph}"
                                onchange="editor.handleCsvFileChange('${ph}', this.value)">
                            <option value="">-- Select CSV file --</option>
                            ${(this.csvFiles && this.csvFiles.length > 0) ? this.csvFiles.map(f => 
                                `<option value="${f.id}" ${setting.csvId === f.id ? 'selected' : ''}>
                                    ${f.display_name || f.id}
                                </option>`
                            ).join('') : '<option value="">Loading CSV files...</option>'}
                        </select>
                        <label class="form-label small">CSV Field:</label>
                        <select class="form-select form-select-sm mb-2" id="csvField_${ph}"
                                onchange="editor.updateSetting('${ph}', 'csvField', this.value)">
                            <option value="">-- Select field --</option>
                        </select>
                        <label class="form-label small">Row Index (optional):</label>
                        <input type="number" class="form-control form-control-sm" 
                               value="${setting.csvRow || 0}" 
                               min="0"
                               placeholder="0"
                               onchange="editor.updateSetting('${ph}', 'csvRow', parseInt(this.value) || 0)">
                    </div>
                    
                    <!-- Random Source -->
                    <div class="source-option ${setting.source === 'random' ? 'active' : ''}" data-source="random">
                        <label class="form-label small">Random Mode:</label>
                        <select class="form-select form-select-sm" 
                                onchange="editor.updateSetting('${ph}', 'randomOption', this.value)">
                            <option value="auto" ${setting.randomOption === 'auto' ? 'selected' : ''}>
                                Auto (different per vessel)
                            </option>
                            <option value="fixed" ${setting.randomOption === 'fixed' ? 'selected' : ''}>
                                Fixed (same for all vessels)
                            </option>
                        </select>
                    </div>
                </div>
            `;
        }).join('');
        
        // Update dropdowns with loaded data
        this.updateDatabaseTableDropdowns();
        this.updateCsvFileDropdowns();
        
        // Load initial database columns if database source is selected
        this.placeholders.forEach(ph => {
            const setting = this.currentSettings[ph];
            if (setting && setting.source === 'database' && setting.databaseTable) {
                this.handleDatabaseTableChange(ph, setting.databaseTable, setting.databaseField);
            }
            if (setting && setting.source === 'csv' && setting.csvId) {
                this.handleCsvFileChange(ph, setting.csvId, setting.csvField);
            }
        });
    }

    async handleSourceChange(placeholder, source) {
        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = {};
        }
        this.currentSettings[placeholder].source = source;
        
        // Show/hide source options
        const config = document.querySelector(`.placeholder-config[data-placeholder="${placeholder}"]`);
        if (config) {
            config.querySelectorAll('.source-option').forEach(opt => {
                opt.classList.toggle('active', opt.dataset.source === source);
            });
        }
    }

    async handleDatabaseTableChange(placeholder, tableName, selectedField = '') {
        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = {};
        }
        this.currentSettings[placeholder].databaseTable = tableName;
        
        const fieldSelect = document.getElementById(`dbField_${placeholder}`);
        if (!fieldSelect) return;
        
        if (tableName) {
            fieldSelect.innerHTML = '<option value="">Loading...</option>';
            const columns = await this.loadTableColumns(tableName);
            fieldSelect.innerHTML = '<option value="">-- Select field --</option>' +
                columns.map(col => 
                    `<option value="${col.name}" ${selectedField === col.name ? 'selected' : ''}>
                        ${col.label} (${col.name})
                    </option>`
                ).join('');
        } else {
            fieldSelect.innerHTML = '<option value="">-- Select field --</option>';
        }
        
        this.updateSetting(placeholder, 'databaseTable', tableName);
    }

    async handleCsvFileChange(placeholder, csvId, selectedField = '') {
        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = {};
        }
        this.currentSettings[placeholder].csvId = csvId;
        
        const fieldSelect = document.getElementById(`csvField_${placeholder}`);
        if (!fieldSelect) return;
        
        if (csvId && this.csvFields[csvId]) {
            fieldSelect.innerHTML = '<option value="">-- Select field --</option>' +
                this.csvFields[csvId].map(f => 
                    `<option value="${f.name}" ${selectedField === f.name ? 'selected' : ''}>
                        ${f.label || f.name} (${f.name})
                    </option>`
                ).join('');
        } else {
            fieldSelect.innerHTML = '<option value="">-- Select field --</option>';
        }
        
        this.updateSetting(placeholder, 'csvId', csvId);
    }


    updateSetting(placeholder, key, value) {
        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = { source: 'random' };
        }
        this.currentSettings[placeholder][key] = value;
    }

    filterPlaceholders() {
        const searchTerm = document.getElementById('searchPlaceholders').value.toLowerCase();
        const configs = document.querySelectorAll('.placeholder-config');
        
        configs.forEach(config => {
            const placeholder = config.dataset.placeholder.toLowerCase();
            config.style.display = placeholder.includes(searchTerm) ? 'block' : 'none';
        });
    }

    async saveTemplateSettings() {
        if (!this.currentTemplateId) {
            alert('No template selected');
            return;
        }

        const displayName = document.getElementById('templateDisplayName').value;
        const description = document.getElementById('templateDescription').value;
        const fontFamily = document.getElementById('templateFontFamily').value;
        const fontSize = document.getElementById('templateFontSize').value;
        
        // Get selected plan IDs
        const planCheckboxes = document.querySelectorAll('#planCheckboxes input[type="checkbox"]:checked');
        const planIds = Array.from(planCheckboxes).map(cb => cb.value);

        try {
            const data = await this.apiJson(`/templates/${encodeURIComponent(this.currentTemplateId)}/metadata`, {
                method: 'POST',
                body: JSON.stringify({
                    display_name: displayName,
                    description: description,
                    font_family: fontFamily || null,
                    font_size: fontSize ? parseInt(fontSize) : null,
                    plan_ids: planIds
                })
            });

            if (data && data.success) {
                alert('Template settings saved successfully!');
                document.getElementById('templateTitle').textContent = displayName || 'Untitled Template';
            }
        } catch (error) {
            alert(`Failed to save template settings: ${error.message}`);
        }
    }

    async savePlaceholderSettings() {
        if (!this.currentTemplateId) {
            alert('No template selected');
            return;
        }

        try {
            const data = await this.apiJson('/placeholder-settings', {
                method: 'POST',
                body: JSON.stringify({
                    template_id: this.currentTemplateId,
                    settings: this.currentSettings
                })
            });

            if (data && data.success) {
                alert('Placeholder settings saved successfully!');
            }
        } catch (error) {
            alert(`Failed to save placeholder settings: ${error.message}`);
        }
    }

    async saveAll() {
        await this.saveTemplateSettings();
        await this.savePlaceholderSettings();
    }
}

// Global instance
const editor = new TemplateEditor();



