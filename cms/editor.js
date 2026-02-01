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
        else if (hostname === 'control.petrodealhub.com') {
            // Use /api so Nginx proxies to backend; /database-tables, /csv-files, /plans-db etc. go through /api/
            apiBase = 'https://control.petrodealhub.com/api';
        } else if (hostname === 'petrodealhub.com' || hostname === 'www.petrodealhub.com') {
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
            const settingsTemplateId = this.currentTemplateId;

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
            
            // Load placeholder settings (use canonical template_id so we match AI mapping saved on upload)
            const settingsData = await this.apiJson(`/placeholder-settings?template_id=${encodeURIComponent(settingsTemplateId)}`);
            console.log('[loadTemplateById] 📥 Settings data received (template_id=' + settingsTemplateId + '):', settingsData);

            const nested = settingsData && settingsData.settings && settingsData.settings[settingsTemplateId];
            const loadedSettings = nested || (settingsData && settingsData.settings) || {};
            const hasStoredSettings = settingsData && settingsData.settings && Object.keys(loadedSettings).length > 0;

            if (!hasStoredSettings) {
                // No stored settings (e.g. newly uploaded template): default to database only, NO mapping.
                // Do NOT persist; user configures table/field in editor and saves explicitly.
                this.currentSettings = {};
                this.placeholders.forEach(ph => {
                    this.currentSettings[ph] = { source: 'database' };
                    console.log(`[loadTemplateById] 🔧 No stored settings: '${ph}' default source='database' (no mapping)`);
                });
                this.displayPlaceholders();
            } else {
                this.currentSettings = { ...loadedSettings };
                console.log('[loadTemplateById] 📋 Loaded stored settings (AI mapping from upload):', this.currentSettings);
                let db = 0, csv = 0, rnd = 0;
                Object.values(this.currentSettings).forEach(s => {
                    const src = (s && s.source) ? String(s.source) : 'database';
                    if (src === 'database') db++; else if (src === 'csv') csv++; else rnd++;
                });
                console.log('[loadTemplateById] 📊 Source counts: database=' + db + ', csv=' + csv + ', random=' + rnd);
                // Only default to database when placeholder has no stored setting. Preserve explicit csv/random.
                this.placeholders.forEach(ph => {
                    if (!this.currentSettings[ph]) {
                        this.currentSettings[ph] = { source: 'database', databaseTable: '', databaseField: '', csvId: '', csvField: '', csvRow: 0, customValue: '', randomOption: 'ai' };
                        console.log(`🔧 Created new setting for '${ph}' with source='database'`);
                    } else {
                        const s = this.currentSettings[ph].source;
                        if (s === undefined || s === null || (typeof s === 'string' && !s.trim())) {
                            this.currentSettings[ph].source = 'database';
                            console.log(`🔧 Defaulted '${ph}': source -> 'database' (was missing)`);
                        }
                    }
                });
                this.displayPlaceholders();
            }
            console.log('[loadTemplateById] ✅ Final currentSettings:', this.currentSettings);

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
                // Include all tables - they are all supported now
                this.databaseTables = data.tables || [];
                console.log(`✅ Loaded ${this.databaseTables.length} database tables:`, this.databaseTables.map(t => `${t.name} (${t.label || t.name})`));
                
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
        // Update all database table dropdowns - show actual mapped table, not "Select table" when we have one
        document.querySelectorAll('.placeholder-config').forEach(configEl => {
            const ph = configEl.dataset.placeholder;
            const setting = this.currentSettings[ph] || {};
            const mappedTable = (setting.databaseTable || '').trim().toLowerCase();
            const select = configEl.querySelector('select[onchange*="handleDatabaseTableChange"]');
            if (!select) return;
            const currentValue = select.value || mappedTable || '';
            select.innerHTML = '<option value="">-- Select table --</option>' +
                (this.databaseTables || []).map(t => {
                    const tName = (t.name || '').toLowerCase();
                    const isSelected = currentValue.toLowerCase() === tName || (mappedTable && mappedTable === tName);
                    return `<option value="${t.name}" ${isSelected ? 'selected' : ''}>
                        ${t.label || t.name}${t.description ? ` - ${t.description}` : ''}
                    </option>`;
                }).join('');
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
            // CRITICAL: Use /plans-db endpoint to get plans from database (not JSON file)
            // This ensures we get the same structure as the CMS (plan_tier as keys)
            const data = await this.apiJson('/plans-db');
            if (data && data.plans) {
                this.plans = data.plans;
                console.log('[loadPlans] ✅ Loaded plans from database:', Object.keys(this.plans).length, 'plans');
                console.log('[loadPlans] Plan keys (plan_tiers):', Object.keys(this.plans));
                this.populatePlanCheckboxes();
            } else {
                console.warn('[loadPlans] ⚠️ No plans in response, trying /plans fallback');
                // Fallback to JSON file if database endpoint fails
                const fallbackData = await this.apiJson('/plans');
                if (fallbackData && fallbackData.plans) {
                    this.plans = fallbackData.plans;
                    this.populatePlanCheckboxes();
                }
            }
        } catch (error) {
            console.error('[loadPlans] ❌ Failed to load plans:', error);
            // Try fallback to JSON file
            try {
                const fallbackData = await this.apiJson('/plans');
                if (fallbackData && fallbackData.plans) {
                    this.plans = fallbackData.plans;
                    this.populatePlanCheckboxes();
                }
            } catch (fallbackError) {
                console.error('[loadPlans] ❌ Fallback also failed:', fallbackError);
            }
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
            console.log('[loadTemplatePlans] 📋 Plan info response:', data);
            
            if (data && data.plans && Array.isArray(data.plans)) {
                // CRITICAL: Use plan_tier, not plan_id, because checkbox values are plan_tier (basic, professional, etc.)
                const assignedPlanIds = data.plans
                    .map(p => p.plan_tier || p.plan_id || p.id)
                    .filter(t => t); // Remove null/undefined values
                console.log('[loadTemplatePlans] ✅ Assigned plan IDs (plan_tiers):', assignedPlanIds);
                this.populatePlanCheckboxes(assignedPlanIds);
            } else {
                console.log('[loadTemplatePlans] ⚠️ No plans in response or empty array, clearing checkboxes');
                this.populatePlanCheckboxes([]);
            }
        } catch (error) {
            console.error('[loadTemplatePlans] ❌ Failed to load template plan assignments:', error);
            console.error('[loadTemplatePlans] ❌ Error details:', error.message);
            // Show user-friendly error but don't break the page
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
            const aiBtn = document.getElementById('aiScanBtn');
            if (aiBtn) { aiBtn.disabled = true; aiBtn.title = 'No placeholders to scan'; }
            return;
        }

        const aiBtn = document.getElementById('aiScanBtn');
        if (aiBtn) { aiBtn.disabled = false; aiBtn.title = 'AI scans all placeholders and maps them correctly (database/CSV/random)'; }

        container.innerHTML = this.placeholders.map(ph => {
            let setting = this.currentSettings[ph] || { 
                source: 'database', 
                customValue: '', 
                databaseTable: '',
                databaseField: '', 
                csvId: '', 
                csvField: '', 
                csvRow: 0, 
                randomOption: 'ai' 
            };
            const src = (setting.source === undefined || setting.source === null || (typeof setting.source === 'string' && !setting.source.trim())) ? 'database' : String(setting.source);
            
            return `
                <div class="placeholder-config" data-placeholder="${ph}">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong><code>${ph}</code></strong>
                        <select class="form-select form-select-sm" style="width: 150px;" 
                                onchange="editor.handleSourceChange('${ph}', this.value)">
                            <option value="database" ${src === 'database' ? 'selected' : ''}>Database</option>
                            <option value="random" ${src === 'random' ? 'selected' : ''}>Random</option>
                            <option value="custom" ${src === 'custom' ? 'selected' : ''}>Custom</option>
                            <option value="csv" ${src === 'csv' ? 'selected' : ''}>CSV</option>
                        </select>
                    </div>
                    
                    <!-- Custom Value -->
                    <div class="source-option ${src === 'custom' ? 'active' : ''}" data-source="custom">
                        <label class="form-label small">Custom Value:</label>
                        <input type="text" class="form-control form-control-sm" 
                               value="${setting.customValue || ''}" 
                               placeholder="Enter custom value..."
                               onchange="editor.updateSetting('${ph}', 'customValue', this.value)">
                    </div>
                    
                    <!-- Database Source -->
                    <div class="source-option ${src === 'database' ? 'active' : ''}" data-source="database">
                        <label class="form-label small">Database Table:</label>
                        <select class="form-select form-select-sm mb-2" id="dbTable_${ph}"
                                onchange="editor.handleDatabaseTableChange('${ph}', this.value)">
                            <option value="">-- Select table --</option>
                            ${(this.databaseTables && this.databaseTables.length > 0) ? this.databaseTables.map(t => 
                                `<option value="${t.name}" ${((setting.databaseTable || '').toLowerCase() === (t.name || '').toLowerCase()) ? 'selected' : ''}>
                                    ${t.label || t.name}${t.description ? ` - ${t.description}` : ''}
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
                    <div class="source-option ${src === 'csv' ? 'active' : ''}" data-source="csv">
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
                    <div class="source-option ${src === 'random' ? 'active' : ''}" data-source="random">
                        <label class="form-label small">Random Mode:</label>
                        <select class="form-select form-select-sm" 
                                onchange="editor.updateSetting('${ph}', 'randomOption', this.value)">
                            <option value="ai" ${setting.randomOption === 'ai' || !setting.randomOption ? 'selected' : ''}>
                                AI Generated (using OpenAI) - Default
                            </option>
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
        // CRITICAL: Pass isInitialLoad=true to preserve databaseField from settings
        this.placeholders.forEach(ph => {
            const setting = this.currentSettings[ph];
            if (setting && setting.source === 'database' && setting.databaseTable) {
                // Pass true for isInitialLoad to prevent clearing databaseField
                this.handleDatabaseTableChange(ph, setting.databaseTable, setting.databaseField, true);
            }
            if (setting && setting.source === 'csv' && setting.csvId) {
                this.handleCsvFileChange(ph, setting.csvId, setting.csvField, true);
            }
        });
    }

    async handleSourceChange(placeholder, source) {
        if (!this.currentSettings[placeholder]) {
            // Default to 'database' if no setting exists
            this.currentSettings[placeholder] = { source: 'database' };
        }
        // If source is not provided or empty, default to 'database'
        if (!source || source === '') {
            source = 'database';
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

    async handleDatabaseTableChange(placeholder, tableName, selectedField = '', isInitialLoad = false) {
        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = { source: 'database' };
        }
        this.currentSettings[placeholder].databaseTable = tableName;
        
        // CRITICAL FIX: When user changes table (not initial load), clear the databaseField
        // because the old field might not exist in the new table
        if (!isInitialLoad && !selectedField) {
            this.currentSettings[placeholder].databaseField = '';
            console.log(`🔄 Table changed for '${placeholder}': cleared databaseField`);
        }
        
        const fieldSelect = document.getElementById(`dbField_${placeholder}`);
        if (!fieldSelect) return;
        
        if (tableName) {
            fieldSelect.innerHTML = '<option value="">Loading...</option>';
            const columns = await this.loadTableColumns(tableName);
            
            // CRITICAL FIX: Use case-insensitive matching for selectedField
            const selectedFieldLower = (selectedField || '').toLowerCase();
            let matchedField = '';
            
            fieldSelect.innerHTML = '<option value="">-- Select field --</option>' +
                columns.map(col => {
                    const colNameLower = (col.name || '').toLowerCase();
                    const isSelected = selectedFieldLower && colNameLower === selectedFieldLower;
                    if (isSelected) {
                        matchedField = col.name;  // Use actual column name (correct case)
                    }
                    return `<option value="${col.name}" ${isSelected ? 'selected' : ''}>
                        ${col.label} (${col.name})
                    </option>`;
                }).join('');
            
            // CRITICAL FIX: Update databaseField with matched field (correct case)
            if (matchedField) {
                this.currentSettings[placeholder].databaseField = matchedField;
                console.log(`✅ Field matched for '${placeholder}': '${selectedField}' -> '${matchedField}'`);
            } else if (selectedField && isInitialLoad) {
                // Field was configured but not found in columns - might be an issue
                console.warn(`⚠️ Configured field '${selectedField}' not found in columns for table '${tableName}'`);
                console.warn(`   Available columns: ${columns.map(c => c.name).join(', ')}`);
            }
        } else {
            fieldSelect.innerHTML = '<option value="">-- Select field --</option>';
            this.currentSettings[placeholder].databaseField = '';
        }
        
        console.log(`📊 handleDatabaseTableChange: placeholder='${placeholder}', table='${tableName}', field='${this.currentSettings[placeholder].databaseField}'`);
    }

    async handleCsvFileChange(placeholder, csvId, selectedField = '', isInitialLoad = false) {
        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = { source: 'csv' };
        }
        this.currentSettings[placeholder].csvId = csvId;
        
        // CRITICAL FIX: When user changes CSV file (not initial load), clear the csvField
        if (!isInitialLoad && !selectedField) {
            this.currentSettings[placeholder].csvField = '';
            console.log(`🔄 CSV file changed for '${placeholder}': cleared csvField`);
        }
        
        const fieldSelect = document.getElementById(`csvField_${placeholder}`);
        if (!fieldSelect) return;
        
        if (csvId) {
            if (!this.csvFields[csvId]) {
                await this.loadCsvFields(csvId);
            }
            if (this.csvFields[csvId]) {
                // CRITICAL FIX: Use case-insensitive matching for selectedField
                const selectedFieldLower = (selectedField || '').toLowerCase();
                let matchedField = '';
                
                fieldSelect.innerHTML = '<option value="">-- Select field --</option>' +
                    this.csvFields[csvId].map(f => {
                        const fieldNameLower = (f.name || '').toLowerCase();
                        const isSelected = selectedFieldLower && fieldNameLower === selectedFieldLower;
                        if (isSelected) {
                            matchedField = f.name;
                        }
                        return `<option value="${f.name}" ${isSelected ? 'selected' : ''}>
                            ${f.label || f.name} (${f.name})
                        </option>`;
                    }).join('');
                
                // CRITICAL FIX: Update csvField with matched field (correct case)
                if (matchedField) {
                    this.currentSettings[placeholder].csvField = matchedField;
                    console.log(`✅ CSV field matched for '${placeholder}': '${selectedField}' -> '${matchedField}'`);
                } else if (selectedField && isInitialLoad) {
                    console.warn(`⚠️ Configured CSV field '${selectedField}' not found in CSV '${csvId}'`);
                }
            } else {
                fieldSelect.innerHTML = '<option value="">-- Select field --</option>';
            }
        } else {
            fieldSelect.innerHTML = '<option value="">-- Select field --</option>';
            this.currentSettings[placeholder].csvField = '';
        }
        
        console.log(`📊 handleCsvFileChange: placeholder='${placeholder}', csvId='${csvId}', field='${this.currentSettings[placeholder].csvField}'`);
    }


    updateSetting(placeholder, key, value) {
        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = { source: 'database' };
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

    async aiScanPlaceholders() {
        if (!this.currentTemplateId) {
            alert('No template selected');
            return;
        }
        if (!this.placeholders || this.placeholders.length === 0) {
            alert('No placeholders to scan');
            return;
        }
        const btn = document.getElementById('aiScanBtn');
        if (!btn) return;
        const origHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Scanning...';
        try {
            const data = await this.apiJson(`/templates/${encodeURIComponent(this.currentTemplateId)}/ai-scan-placeholders`, {
                method: 'POST',
                body: JSON.stringify({})
            });
            if (!data || !data.settings) {
                alert('AI scan failed: no settings returned');
                return;
            }
            this.currentSettings = { ...data.settings };
            this.displayPlaceholders();
            await this.savePlaceholderSettings(true);
            alert(`AI Scan complete. ${Object.keys(this.currentSettings).length} placeholders mapped and saved.`);
        } catch (e) {
            console.error('AI scan error:', e);
            alert('AI Scan failed: ' + (e.message || 'Unknown error'));
        } finally {
            btn.disabled = false;
            btn.innerHTML = origHtml;
        }
    }

    async saveTemplateSettings() {
        if (!this.currentTemplateId) {
            alert('No template selected');
            return;
        }

        const displayName = document.getElementById('templateDisplayName')?.value || '';
        const description = document.getElementById('templateDescription')?.value || '';
        const fontFamily = document.getElementById('templateFontFamily')?.value || '';
        const fontSizeInput = document.getElementById('templateFontSize')?.value;
        
        // Get selected plan IDs (plan_tiers like "basic", "professional", etc.)
        const planCheckboxes = document.querySelectorAll('#planCheckboxes input[type="checkbox"]:checked');
        const planIds = Array.from(planCheckboxes).map(cb => cb.value).filter(v => v);
        
        console.log('[saveTemplateSettings] 💾 Saving template settings:', {
            templateId: this.currentTemplateId,
            displayName,
            description,
            fontFamily: fontFamily || null,
            fontSize: fontSizeInput,
            planIds,
            planIdsCount: planIds.length,
            checkedCheckboxes: planCheckboxes.length
        });
        
        // Log each checkbox value for debugging
        Array.from(planCheckboxes).forEach((cb, idx) => {
            console.log(`[saveTemplateSettings] 📋 Checkbox ${idx + 1}: value="${cb.value}", checked=${cb.checked}`);
        });

        // Validate fontSize if provided
        let fontSize = null;
        if (fontSizeInput && fontSizeInput.trim()) {
            const parsed = parseInt(fontSizeInput.trim(), 10);
            if (!isNaN(parsed) && parsed > 0) {
                fontSize = parsed;
            } else {
                alert('Font size must be a positive number');
                return;
            }
        }

        try {
            const payload = {
                display_name: displayName,
                description: description,
                font_family: fontFamily || null,
                font_size: fontSize,
                plan_ids: planIds // Array of plan_tiers (basic, professional, etc.)
            };
            
            console.log('[saveTemplateSettings] 📤 Sending payload:', JSON.stringify(payload, null, 2));
            
            const data = await this.apiJson(`/templates/${encodeURIComponent(this.currentTemplateId)}/metadata`, {
                method: 'POST',
                body: JSON.stringify(payload)
            });

            console.log('[saveTemplateSettings] 📥 Response:', data);
            console.log('[saveTemplateSettings] 📥 Response plan_ids:', data?.plan_ids);

            if (data && data.success) {
                alert('Template settings saved successfully!');
                document.getElementById('templateTitle').textContent = displayName || 'Untitled Template';
                
                // CRITICAL: Update checkboxes immediately with saved plan_ids from response
                // This ensures checkboxes reflect what was actually saved
                // The response contains the actual plan_ids that were saved, so we trust that
                const savedPlanIds = data.plan_ids || planIds; // Use response plan_ids, fallback to what we sent
                console.log('[saveTemplateSettings] ✅ Updating checkboxes with saved plan_ids:', savedPlanIds);
                
                // Update checkboxes immediately with saved data from response
                // Don't reload from backend immediately - the response already contains the saved data
                // Reloading might fetch stale data or cause race conditions
                this.populatePlanCheckboxes(savedPlanIds);
                
                // Optionally reload from backend after a longer delay (optional, for sync verification)
                // Only reload if you want to verify the database has the data, but the checkboxes are already updated
                // setTimeout(async () => {
                //     console.log('[saveTemplateSettings] 🔄 Verifying template plans from backend...');
                //     await this.loadTemplatePlans();
                // }, 2000);
            } else {
                const errorMsg = data?.detail || data?.error || 'Unknown error';
                console.error('[saveTemplateSettings] ❌ Save failed:', data);
                alert(`Failed to save template settings: ${errorMsg}`);
            }
        } catch (error) {
            console.error('[saveTemplateSettings] ❌ Error:', error);
            const errorMsg = error.message || 'Failed to save template settings';
            alert(`Failed to save template settings: ${errorMsg}`);
        }
    }

    async savePlaceholderSettings(quiet = false) {
        if (!this.currentTemplateId) {
            alert('No template selected');
            return;
        }

        try {
            // Default to database only when source is missing or empty. Preserve explicit random/csv.
            Object.keys(this.currentSettings).forEach(ph => {
                const setting = this.currentSettings[ph];
                const s = setting.source;
                if (s === undefined || s === null || (typeof s === 'string' && !s.trim())) {
                    setting.source = 'database';
                    console.log(`🔧 Defaulted placeholder '${ph}': source -> 'database' before save (was missing)`);
                }
            });
            
            console.log('=' .repeat(60));
            console.log('💾 SAVING PLACEHOLDER SETTINGS');
            console.log('=' .repeat(60));
            console.log('   Template ID:', this.currentTemplateId);
            console.log('   Total settings count:', Object.keys(this.currentSettings).length);
            
            // Log ALL settings with their database table/field for debugging
            console.log('📋 Settings being saved:');
            Object.entries(this.currentSettings).forEach(([ph, setting]) => {
                console.log(`   ${ph}:`);
                console.log(`      source: '${setting.source}'`);
                if (setting.source === 'database') {
                    console.log(`      databaseTable: '${setting.databaseTable || ''}'`);
                    console.log(`      databaseField: '${setting.databaseField || ''}'`);
                } else if (setting.source === 'csv') {
                    console.log(`      csvId: '${setting.csvId || ''}'`);
                    console.log(`      csvField: '${setting.csvField || ''}'`);
                } else if (setting.source === 'custom') {
                    console.log(`      customValue: '${setting.customValue || ''}'`);
                }
            });
            console.log('=' .repeat(60));
            
            const data = await this.apiJson('/placeholder-settings', {
                method: 'POST',
                body: JSON.stringify({
                    template_id: this.currentTemplateId,
                    settings: this.currentSettings
                })
            });

            if (data && data.success) {
                console.log('✅ Settings saved successfully!', data);
                console.log('   Saved count:', data.saved_count);
                
                // Verify the returned settings match what we sent
                if (data.settings) {
                    console.log('📋 Settings returned from server (verification):');
                    Object.entries(data.settings).slice(0, 5).forEach(([ph, setting]) => {
                        console.log(`   ${ph}: source='${setting.source}', table='${setting.databaseTable || ''}', field='${setting.databaseField || ''}'`);
                    });
                }
                
                if (!quiet) alert(`Placeholder settings saved successfully! (${data.saved_count || Object.keys(this.currentSettings).length} settings)`);
            } else {
                console.error('❌ Save failed:', data);
                if (!quiet) alert('Failed to save placeholder settings: Invalid response');
            }
        } catch (error) {
            console.error('❌ Error saving settings:', error);
            if (!quiet) alert(`Failed to save placeholder settings: ${error.message}`);
            throw error;
        }
    }

    async saveAll() {
        await this.saveTemplateSettings();
        await this.savePlaceholderSettings();
    }
}

// Global instance (expose on window for onclick handlers)
const editor = new TemplateEditor();
if (typeof window !== 'undefined') {
    window.editor = editor;
    window.aiScanPlaceholders = function () { return editor.aiScanPlaceholders(); };
}



