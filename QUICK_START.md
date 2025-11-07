# Quick Start Guide

## 🚀 Starting the System

### 1. Start API Backend Server
```bash
cd document-processor
python main.py
```
**Server will run on:** `http://localhost:8000`

### 2. Start CMS Frontend Server
Open a **new terminal window**:
```bash
cd document-processor/cms
python -m http.server 8080 --bind 127.0.0.1
```
**Frontend will run on:** `http://127.0.0.1:8080`

## 🌐 Access URLs

| Service | URL | Purpose |
|---------|-----|---------|
| **CMS Dashboard** | http://127.0.0.1:8080/index.html | Main admin interface |
| **Advanced Editor** | http://127.0.0.1:8080/editor.html | Placeholder mapping editor |
| **API Health** | http://localhost:8000/health | Check API status |
| **API Docs** | http://localhost:8000/docs | Interactive API documentation |

## 🔐 Login Credentials

- **Username:** `admin`
- **Password:** `admin123`

## 📋 Manual Testing Checklist

### ✅ Test 1: Basic Access
- [ ] Open http://localhost:8000/health
- [ ] Should show: `{"status":"healthy","supabase":"connected",...}`

### ✅ Test 2: CMS Login
- [ ] Open http://127.0.0.1:8080/index.html
- [ ] Click "Login" button (top right)
- [ ] Enter: `admin` / `admin123`
- [ ] Should see "User: admin" in navbar

### ✅ Test 3: Templates Management
- [ ] Go to "Templates" tab
- [ ] Should see list of existing templates
- [ ] Click "Edit" on a template → opens Advanced Editor
- [ ] Try uploading a new .docx file

### ✅ Test 4: Advanced Editor
- [ ] Select a template from dropdown
- [ ] Select a vessel from dropdown
- [ ] Map placeholders to data sources:
  - Database
  - CSV
  - Random
  - Custom (enter value)
- [ ] Click "Save Settings"

### ✅ Test 5: Data Sources
- [ ] Go to "Data Sources" tab
- [ ] Should show status of CSV files (buyers_sellers, bank_accounts, icpo)
- [ ] Try uploading a new CSV file

### ✅ Test 6: Plans Management
- [ ] Go to "Plans" tab
- [ ] Should see subscription plans (basic, premium, enterprise)
- [ ] Test permission check:
  - Enter User ID: `testuser123`
  - Enter Template: `test.docx`
  - Click "Check Permission"
  - Should show result

### ✅ Test 7: API Endpoints
Test these URLs directly in browser:
- [ ] http://localhost:8000/templates
- [ ] http://localhost:8000/plans
- [ ] http://localhost:8000/data/all
- [ ] http://localhost:8000/placeholder-settings

## 🐛 Troubleshooting

### Problem: API returns 404 for endpoints
**Solution:** Restart the API server:
```bash
# Stop old server (Ctrl+C or close window)
python main.py
```

### Problem: Upload fails
**Solution:**
1. Make sure you're logged in
2. Try hard refresh: Ctrl+F5
3. Check browser console (F12) for errors

### Problem: CMS not loading
**Solution:**
```bash
cd cms
python -m http.server 8080 --bind 127.0.0.1
```

### Problem: Login doesn't work
**Solution:**
1. Check API server is running on port 8000
2. Try logout and login again
3. Clear browser cookies

## 📁 Project Structure

```
document-processor/
├── main.py                 # FastAPI backend server
├── cms/
│   ├── index.html         # Main CMS dashboard
│   ├── editor.html        # Advanced document editor
│   ├── cms.js             # CMS JavaScript
│   └── editor.js          # Editor JavaScript
├── templates/              # Word document templates (.docx)
├── data/                   # CSV data files
├── storage/                # JSON storage (plans, users, settings)
├── temp/                   # Temporary files
└── requirements.txt        # Python dependencies
```

## 🎯 Key Features

- ✅ **Template Management:** Upload, view, delete DOCX templates
- ✅ **Placeholder Extraction:** Automatically finds placeholders in templates
- ✅ **Placeholder Mapping:** Configure data source for each placeholder
- ✅ **Data Sources:** Upload/manage CSV data files
- ✅ **Plans System:** Subscription plans with permissions
- ✅ **Authentication:** Simple login/logout with sessions
- ✅ **Clean Interface:** Modern Bootstrap 5 UI

## 🔧 Development

### Add New Endpoint
Edit `main.py`:
```python
@app.get("/new-endpoint")
async def new_endpoint():
    return {"message": "Hello"}
```

### Modify Frontend
Edit files in `cms/` directory and refresh browser.

### Check Logs
Watch the Python terminal windows for API and error logs.

## 📞 Support

If issues persist:
1. Check both terminal windows for error messages
2. Open browser DevTools (F12) → Console tab
3. Verify API is running: http://localhost:8000/health
4. Verify CMS is running: http://127.0.0.1:8080/index.html

