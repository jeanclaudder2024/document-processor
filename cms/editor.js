// Advanced Document Editor
class DocumentEditor {
    constructor() {
        this.apiBaseUrl = 'http://localhost:8000';
        this.currentTemplate = null;
        this.currentTemplateId = null;
        this.currentSettings = {};
        this.placeholders = [];
        this.vesselFields = [];  // Store available vessel fields
        this.csvFiles = [];  // Store available CSV files
        this.csvFields = {};  // Store CSV fields by file ID
        this.init();
    }

    init() {
        this.loadTemplates();
        this.loadVessels();
        this.loadVesselFields();  // Load vessel fields
        this.loadCsvFiles();  // Load CSV files
        
        // Get template from URL parameter
        const urlParams = new URLSearchParams(window.location.search);
        const templateParam = urlParams.get('template');
        if (templateParam) {
            setTimeout(() => {
                document.getElementById('templateSelect').value = templateParam;
                this.loadTemplate();
            }, 500);
        }
    }

    async loadVesselFields() {
        try {
            const data = await this.apiJson('/vessel-fields');
            if (data && data.fields) {
                this.vesselFields = data.fields;
            }
        } catch (error) {
            console.error('Failed to load vessel fields:', error);
        }
    }

    async loadCsvFiles() {
        try {
            const data = await this.apiJson('/csv-files');
            if (data && data.csv_files) {
                this.csvFiles = data.csv_files;
                // Load fields for each CSV file
                for (const csvFile of this.csvFiles) {
                    await this.loadCsvFields(csvFile.id);
                }
            }
        } catch (error) {
            console.error('Failed to load CSV files:', error);
        }
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

    async apiJson(path, options = {}) {
        const opts = {
            ...options,
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };
        
        try {
            const response = await fetch(`${this.apiBaseUrl}${path}`, opts);
            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
            return await response.json();
        } catch (error) {
            alert(`Error: ${error.message}`);
            return null;
        }
    }

    async loadTemplates() {
        try {
            const data = await this.apiJson('/templates');
            if (data && data.templates) {
                const select = document.getElementById('templateSelect');
                select.innerHTML = '<option value="">Select template...</option>';
                data.templates.forEach(t => {
                    const option = document.createElement('option');
                    option.value = t.name;
                    option.textContent = t.name;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Failed to load templates:', error);
        }
    }

    async loadVessels() {
        try {
            const data = await this.apiJson('/vessels');
            if (data && data.vessels) {
                const select = document.getElementById('vesselSelect');
                select.innerHTML = '<option value="">Select vessel...</option>';
                data.vessels.forEach(v => {
                    const option = document.createElement('option');
                    option.value = v.imo;
                    option.textContent = `${v.name} (${v.imo})`;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Failed to load vessels:', error);
        }
    }

    async loadTemplate() {
        const templateName = document.getElementById('templateSelect').value;
        if (!templateName) return;

        try {
            const templateData = await this.apiJson(`/templates/${encodeURIComponent(templateName)}`);
            if (!templateData) return;

            this.currentTemplate = templateName;
            this.currentTemplateId = templateData?.template_id || null;
            this.placeholders = templateData.placeholders || [];
            
            document.getElementById('documentTitle').textContent = templateName;

            // Load existing settings
            const settingsData = await this.apiJson(`/placeholder-settings?template_name=${encodeURIComponent(templateName)}`);
            if (settingsData && settingsData.settings) {
                this.currentSettings = settingsData.settings;
                this.currentTemplateId = settingsData.template_id || this.currentTemplateId;
            } else {
                this.currentSettings = {};
            }

            this.displayPlaceholders();
            this.displayDocumentPreview();
        } catch (error) {
            alert(`Failed to load template: ${error.message}`);
        }
    }

    displayPlaceholders() {
        const container = document.getElementById('placeholdersList');
        
        if (this.placeholders.length === 0) {
            container.innerHTML = '<div class="text-muted small">No placeholders found</div>';
            return;
        }

        container.innerHTML = this.placeholders.map(ph => {
            const setting = this.currentSettings[ph] || { source: 'random', customValue: '', databaseField: '', csvId: '', csvField: '', csvRow: 0, randomOption: 'auto' };
            return `
                <div class="placeholder-item" data-placeholder="${ph}">
                    <strong>${ph}</strong>
                    <select class="data-source-select form-select form-select-sm" 
                            data-placeholder="${ph}"
                            onchange="editor.handleSourceChange('${ph}')">
                        <option value="random" ${setting.source === 'random' ? 'selected' : ''}>Random</option>
                        <option value="database" ${setting.source === 'database' ? 'selected' : ''}>Database</option>
                        <option value="csv" ${setting.source === 'csv' ? 'selected' : ''}>CSV</option>
                        <option value="custom" ${setting.source === 'custom' ? 'selected' : ''}>Custom</option>
                    </select>
                    
                    <!-- Random option selection -->
                    <div class="random-option-group mt-1" data-placeholder="${ph}" ${setting.source === 'random' ? '' : 'style="display:none;"'}>
                        <select class="random-option-select form-select form-select-sm" 
                                data-placeholder="${ph}"
                                onchange="editor.updatePlaceholderSetting('${ph}')">
                            <option value="auto" ${setting.randomOption === 'auto' ? 'selected' : ''}>Auto (different per vessel)</option>
                            <option value="fixed" ${setting.randomOption === 'fixed' ? 'selected' : ''}>Fixed (same for all vessels)</option>
                        </select>
                    </div>
                    
                    <!-- Database field selection -->
                    <select class="database-field-select form-select form-select-sm mt-1" 
                            data-placeholder="${ph}"
                            onchange="editor.updatePlaceholderSetting('${ph}')"
                            ${setting.source === 'database' ? '' : 'style="display:none;"'}>
                        <option value="">-- Select database field --</option>
                        ${this.vesselFields.map(f => 
                            `<option value="${f.name}" ${setting.databaseField === f.name ? 'selected' : ''}>${f.label} (${f.name})</option>`
                        ).join('')}
                    </select>
                    
                    <!-- CSV file selection -->
                    <select class="csv-file-select form-select form-select-sm mt-1" 
                            data-placeholder="${ph}"
                            onchange="editor.handleCsvFileChange('${ph}')"
                            ${setting.source === 'csv' ? '' : 'style="display:none;"'}>
                        <option value="">-- Select CSV file --</option>
                        ${this.csvFiles.map(f => 
                            `<option value="${f.id}" ${setting.csvId === f.id ? 'selected' : ''}>${f.display_name}</option>`
                        ).join('')}
                    </select>
                    
                    <!-- CSV field selection -->
                    <select class="csv-field-select form-select form-select-sm mt-1" 
                            data-placeholder="${ph}"
                            ${setting.source === 'csv' && setting.csvId ? '' : 'style="display:none;"'}>
                        <option value="">-- Select CSV field --</option>
                        ${setting.csvId && this.csvFields[setting.csvId] ? 
                            this.csvFields[setting.csvId].map(f => 
                                `<option value="${f.name}" ${setting.csvField === f.name ? 'selected' : ''}>${f.label} (${f.name})</option>`
                            ).join('') : ''}
                    </select>
                    
                    <!-- CSV row selection -->
                    <select class="csv-row-select form-select form-select-sm mt-1" 
                            data-placeholder="${ph}"
                            onchange="editor.updatePlaceholderSetting('${ph}')"
                            ${setting.source === 'csv' && setting.csvId && setting.csvField ? '' : 'style="display:none;"'}>
                        <option value="">-- Select specific value --</option>
                    </select>
                    
                    <!-- Custom value input -->
                    <input type="text" 
                           class="custom-value-input form-control form-control-sm mt-1" 
                           data-placeholder="${ph}"
                           value="${setting.customValue || ''}"
                           placeholder="Enter custom value..."
                           onchange="editor.updatePlaceholderSetting('${ph}')"
                           ${setting.source === 'custom' ? '' : 'style="display:none;"'}>
                </div>
            `;
        }).join('');

        // Attach change handlers
        container.querySelectorAll('.data-source-select').forEach(select => {
            const placeholder = select.dataset.placeholder;
            const fieldSelect = container.querySelector(`select.database-field-select[data-placeholder="${placeholder}"]`);
            const csvFileSelect = container.querySelector(`select.csv-file-select[data-placeholder="${placeholder}"]`);
            const csvFieldSelect = container.querySelector(`select.csv-field-select[data-placeholder="${placeholder}"]`);
            const csvRowSelect = container.querySelector(`select.csv-row-select[data-placeholder="${placeholder}"]`);
            const randomOptionGroup = container.querySelector(`.random-option-group[data-placeholder="${placeholder}"]`);
            const customInput = container.querySelector(`input[data-placeholder="${placeholder}"]`);
            
            select.addEventListener('change', () => {
                if (select.value === 'database') {
                    fieldSelect.style.display = 'block';
                    csvFileSelect.style.display = 'none';
                    csvFieldSelect.style.display = 'none';
                    csvRowSelect.style.display = 'none';
                    if (randomOptionGroup) randomOptionGroup.style.display = 'none';
                    customInput.style.display = 'none';
                } else if (select.value === 'csv') {
                    fieldSelect.style.display = 'none';
                    csvFileSelect.style.display = 'block';
                    csvFieldSelect.style.display = 'none';
                    csvRowSelect.style.display = 'none';
                    if (randomOptionGroup) randomOptionGroup.style.display = 'none';
                    customInput.style.display = 'none';
                } else if (select.value === 'custom') {
                    fieldSelect.style.display = 'none';
                    csvFileSelect.style.display = 'none';
                    csvFieldSelect.style.display = 'none';
                    csvRowSelect.style.display = 'none';
                    if (randomOptionGroup) randomOptionGroup.style.display = 'none';
                    customInput.style.display = 'block';
                } else if (select.value === 'random') {
                    fieldSelect.style.display = 'none';
                    csvFileSelect.style.display = 'none';
                    csvFieldSelect.style.display = 'none';
                    csvRowSelect.style.display = 'none';
                    if (randomOptionGroup) randomOptionGroup.style.display = 'block';
                    customInput.style.display = 'none';
                } else {
                    fieldSelect.style.display = 'none';
                    csvFileSelect.style.display = 'none';
                    csvFieldSelect.style.display = 'none';
                    csvRowSelect.style.display = 'none';
                    if (randomOptionGroup) randomOptionGroup.style.display = 'none';
                    customInput.style.display = 'none';
                }
                this.updatePlaceholderSetting(placeholder);
            });
        });
        
        // Attach CSV field change handlers
        container.querySelectorAll('.csv-field-select').forEach(select => {
            const placeholder = select.dataset.placeholder;
            select.addEventListener('change', () => {
                this.handleCsvFieldChange(placeholder);
            });
        });
    }

    handleSourceChange(placeholder) {
        // This is called from the inline onclick handler
        const container = document.getElementById('placeholdersList');
        const select = container.querySelector(`select.data-source-select[data-placeholder="${placeholder}"]`);
        const fieldSelect = container.querySelector(`select.database-field-select[data-placeholder="${placeholder}"]`);
        const csvFileSelect = container.querySelector(`select.csv-file-select[data-placeholder="${placeholder}"]`);
        const csvFieldSelect = container.querySelector(`select.csv-field-select[data-placeholder="${placeholder}"]`);
        const csvRowSelect = container.querySelector(`select.csv-row-select[data-placeholder="${placeholder}"]`);
        const randomOptionGroup = container.querySelector(`.random-option-group[data-placeholder="${placeholder}"]`);
        const customInput = container.querySelector(`input[data-placeholder="${placeholder}"]`);
        
        if (select.value === 'database') {
            fieldSelect.style.display = 'block';
            csvFileSelect.style.display = 'none';
            csvFieldSelect.style.display = 'none';
            csvRowSelect.style.display = 'none';
            if (randomOptionGroup) randomOptionGroup.style.display = 'none';
            customInput.style.display = 'none';
        } else if (select.value === 'csv') {
            fieldSelect.style.display = 'none';
            csvFileSelect.style.display = 'block';
            csvFieldSelect.style.display = 'none';
            csvRowSelect.style.display = 'none';
            if (randomOptionGroup) randomOptionGroup.style.display = 'none';
            customInput.style.display = 'none';
        } else if (select.value === 'custom') {
            fieldSelect.style.display = 'none';
            csvFileSelect.style.display = 'none';
            csvFieldSelect.style.display = 'none';
            csvRowSelect.style.display = 'none';
            if (randomOptionGroup) randomOptionGroup.style.display = 'none';
            customInput.style.display = 'block';
        } else if (select.value === 'random') {
            fieldSelect.style.display = 'none';
            csvFileSelect.style.display = 'none';
            csvFieldSelect.style.display = 'none';
            csvRowSelect.style.display = 'none';
            if (randomOptionGroup) randomOptionGroup.style.display = 'block';
            customInput.style.display = 'none';
        } else {
            fieldSelect.style.display = 'none';
            csvFileSelect.style.display = 'none';
            csvFieldSelect.style.display = 'none';
            csvRowSelect.style.display = 'none';
            if (randomOptionGroup) randomOptionGroup.style.display = 'none';
            customInput.style.display = 'none';
        }
        this.updatePlaceholderSetting(placeholder);
    }

    handleCsvFileChange(placeholder) {
        const container = document.getElementById('placeholdersList');
        const csvFileSelect = container.querySelector(`select.csv-file-select[data-placeholder="${placeholder}"]`);
        const csvFieldSelect = container.querySelector(`select.csv-field-select[data-placeholder="${placeholder}"]`);
        const csvRowSelect = container.querySelector(`select.csv-row-select[data-placeholder="${placeholder}"]`);
        
        const csvId = csvFileSelect.value;
        
        if (csvId && this.csvFields[csvId]) {
            csvFieldSelect.innerHTML = '<option value="">-- Select CSV field --</option>' +
                this.csvFields[csvId].map(f => 
                    `<option value="${f.name}">${f.label} (${f.name})</option>`
                ).join('');
            csvFieldSelect.style.display = 'block';
        } else {
            csvFieldSelect.style.display = 'none';
        }
        
        csvRowSelect.innerHTML = '<option value="">-- Select specific value --</option>';
        csvRowSelect.style.display = 'none';
        
        this.updatePlaceholderSetting(placeholder);
    }

    async handleCsvFieldChange(placeholder) {
        const container = document.getElementById('placeholdersList');
        const csvFileSelect = container.querySelector(`select.csv-file-select[data-placeholder="${placeholder}"]`);
        const csvFieldSelect = container.querySelector(`select.csv-field-select[data-placeholder="${placeholder}"]`);
        const csvRowSelect = container.querySelector(`select.csv-row-select[data-placeholder="${placeholder}"]`);
        
        const csvId = csvFileSelect.value;
        const csvField = csvFieldSelect.value;
        
        if (csvId && csvField) {
            // Load rows for this field
            csvRowSelect.innerHTML = '<option value="">Loading...</option>';
            csvRowSelect.style.display = 'block';
            
            try {
                const data = await this.apiJson(`/csv-rows/${csvId}/${csvField}`);
                if (data && data.rows) {
                    csvRowSelect.innerHTML = '<option value="">-- Select specific value --</option>' +
                        data.rows.map(row => 
                            `<option value="${row.row_index}">${row.preview}</option>`
                        ).join('');
                }
            } catch (error) {
                csvRowSelect.innerHTML = '<option value="">Error loading rows</option>';
                console.error('Error loading CSV rows:', error);
            }
        } else {
            csvRowSelect.innerHTML = '<option value="">-- Select specific value --</option>';
            csvRowSelect.style.display = 'none';
        }
        
        this.updatePlaceholderSetting(placeholder);
    }

    updatePlaceholderSetting(placeholder) {
        const sourceSelect = document.querySelector(`select.data-source-select[data-placeholder="${placeholder}"]`);
        const fieldSelect = document.querySelector(`select.database-field-select[data-placeholder="${placeholder}"]`);
        const csvFileSelect = document.querySelector(`select.csv-file-select[data-placeholder="${placeholder}"]`);
        const csvFieldSelect = document.querySelector(`select.csv-field-select[data-placeholder="${placeholder}"]`);
        const csvRowSelect = document.querySelector(`select.csv-row-select[data-placeholder="${placeholder}"]`);
        const randomOptionSelect = document.querySelector(`select.random-option-select[data-placeholder="${placeholder}"]`);
        const customInput = document.querySelector(`input[data-placeholder="${placeholder}"]`);
        
        const source = sourceSelect ? sourceSelect.value : 'random';
        const databaseField = fieldSelect ? fieldSelect.value : '';
        const csvId = csvFileSelect ? csvFileSelect.value : '';
        const csvField = csvFieldSelect ? csvFieldSelect.value : '';
        const csvRow = csvRowSelect ? parseInt(csvRowSelect.value) || 0 : 0;
        const randomOption = randomOptionSelect ? randomOptionSelect.value : 'auto';
        const customValue = source === 'custom' && customInput ? customInput.value : '';

        if (!this.currentSettings[placeholder]) {
            this.currentSettings[placeholder] = {};
        }
        
        this.currentSettings[placeholder].source = source;
        this.currentSettings[placeholder].customValue = customValue;
        
        if (source === 'database' && databaseField) {
            this.currentSettings[placeholder].databaseField = databaseField;
        } else {
            this.currentSettings[placeholder].databaseField = '';
        }
        
        if (source === 'csv') {
            this.currentSettings[placeholder].csvId = csvId || '';
            this.currentSettings[placeholder].csvField = csvField || '';
            this.currentSettings[placeholder].csvRow = csvRow;
        } else {
            this.currentSettings[placeholder].csvId = '';
            this.currentSettings[placeholder].csvField = '';
            this.currentSettings[placeholder].csvRow = 0;
        }
        
        if (source === 'random') {
            this.currentSettings[placeholder].randomOption = randomOption;
        } else {
            this.currentSettings[placeholder].randomOption = 'auto';
        }
    }

    displayDocumentPreview() {
        const container = document.getElementById('documentContent');
        if (!this.currentTemplate) {
            container.innerHTML = '<div class="text-center text-muted py-5">Select a template</div>';
            return;
        }

        // Simple preview showing placeholders
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h5>${this.currentTemplate}</h5>
                </div>
                <div class="card-body">
                    <p class="text-muted">This template contains ${this.placeholders.length} placeholders:</p>
                    <div class="mb-3">
                        ${this.placeholders.map(ph => {
                            const setting = this.currentSettings[ph] || { source: 'database' };
                            const sourceBadge = {
                                'database': '<span class="badge bg-primary">Database</span>',
                                'csv': '<span class="badge bg-success">CSV</span>',
                                'random': '<span class="badge bg-warning">Random</span>',
                                'custom': '<span class="badge bg-info">Custom</span>'
                            }[setting.source] || '<span class="badge bg-secondary">Unknown</span>';
                            
                            return `
                                <div class="mb-2 p-2 border rounded">
                                    <code>${ph}</code> ${sourceBadge}
                                    ${setting.source === 'database' && setting.databaseField ? 
                                        `<br><small class="text-muted">Field: ${setting.databaseField}</small>` : ''}
                                    ${setting.source === 'csv' && setting.csvId && setting.csvField ? 
                                        `<br><small class="text-muted">CSV: ${setting.csvId}[${setting.csvRow || 0}].${setting.csvField}</small>` : ''}
                                    ${setting.source === 'random' && setting.randomOption ? 
                                        `<br><small class="text-muted">Mode: ${setting.randomOption === 'auto' ? 'Different per vessel' : 'Fixed for all'}</small>` : ''}
                                    ${setting.source === 'custom' && setting.customValue ? 
                                        `<br><small class="text-muted">Value: ${setting.customValue}</small>` : ''}
                                </div>
                            `;
                        }).join('')}
                    </div>
                    <p class="text-muted small">
                        <i class="fas fa-info-circle me-1"></i>
                        Configure each placeholder's data source in the sidebar. 
                        Custom values override all other sources.
                    </p>
                </div>
            </div>
        `;
    }

    async saveSettings() {
        if (!this.currentTemplate) {
            alert('Please select a template first');
            return;
        }

        // Update all settings from current form state
        this.placeholders.forEach(ph => {
            this.updatePlaceholderSetting(ph);
        });

        try {
            const data = await this.apiJson('/placeholder-settings', {
                method: 'POST',
                body: JSON.stringify({
                    template_name: this.currentTemplate,
                    template_id: this.currentTemplateId,
                    settings: this.currentSettings
                })
            });

            if (data && data.success) {
                alert('Settings saved successfully!');
                this.displayDocumentPreview();
            }
        } catch (error) {
            alert(`Failed to save settings: ${error.message}`);
        }
    }
}

// Global instance
const editor = new DocumentEditor();

