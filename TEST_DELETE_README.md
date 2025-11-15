# Test Delete Script - دليل استخدام سكريبت اختبار الحذف

## كيفية استخدام السكريبت:

### على VPS:

```bash
cd /opt/petrodealhub/document-processor

# تثبيت المكتبات المطلوبة (إذا لم تكن موجودة)
pip3 install requests

# تشغيل السكريبت
python3 test_delete.py
```

### على Local:

```bash
cd document-processor

# تثبيت المكتبات المطلوبة
pip install requests

# تشغيل السكريبت
python test_delete.py

# أو مع API URL محدد
API_URL=http://localhost:8000 python test_delete.py
```

---

## ما الذي يفحصه السكريبت:

1. ✅ **Directories**: يتحقق من وجود `templates/` و `storage/`
2. ✅ **deleted_templates.json**: يفحص الملف ومحتوياته
3. ✅ **Local Templates**: يعرض جميع القوالب في `templates/` directory
4. ✅ **Storage Files**: يتحقق من وجود ملفات metadata و plans
5. ✅ **API Endpoints**: يختبر API (إذا كان يعمل)
6. ✅ **Comparison**: يقارن بين القوالب المحلية وAPI
7. ✅ **Deleted Templates Check**: يتحقق من أن القوالب المحذوفة ليست في filesystem

---

## فهم النتائج:

### إذا كان كل شيء صحيح:
```
✓ TEMPLATES_DIR: .../templates
✓ STORAGE_DIR: .../storage
✓ deleted_templates.json exists
✓ Templates in templates/ directory: X files
✓ API is running
✓ Deleted template 'X.docx' not found in filesystem
```

### إذا كانت هناك مشاكل:
```
✗ deleted_templates.json does not exist
⚠ WARNING: Deleted template 'X.docx' still exists as 'X.docx'
✗ API not available: ...
```

---

## حل المشاكل الشائعة:

### 1. deleted_templates.json غير موجود:
```bash
# السكريبت سينشئه تلقائياً عند الحذف، لكن يمكنك إنشاؤه يدوياً:
cd /opt/petrodealhub/document-processor
mkdir -p storage
echo '{"deleted_templates": [], "last_updated": ""}' > storage/deleted_templates.json
```

### 2. قالب محذوف لكنه موجود في filesystem:
```bash
# السكريبت سيحذفه تلقائياً عند إعادة التحميل، لكن يمكنك حذفه يدوياً:
rm /opt/petrodealhub/document-processor/templates/TEMPLATE_NAME.docx
```

### 3. API لا يعمل:
```bash
# تحقق من حالة API
sudo systemctl status petrodealhub-api

# إعادة تشغيل API
sudo systemctl restart petrodealhub-api

# فحص logs
sudo journalctl -u petrodealhub-api -n 50 --no-pager
```

---

## بعد تشغيل السكريبت:

1. **راجع النتائج** - تحقق من جميع ✓ و ✗
2. **أصلح المشاكل** - استخدم الحلول المذكورة أعلاه
3. **اختبر الحذف** - احذف قالب وتحقق من أنه لا يعود
4. **شغّل السكريبت مرة أخرى** - للتأكد من أن المشاكل تم حلها

---

## مثال على استخدام السكريبت:

```bash
# 1. شغّل السكريبت
python3 test_delete.py

# 2. راجع النتائج - مثال:
# ============================================================
#   TEMPLATE DELETION TEST SCRIPT
# ============================================================
# 
# ============================================================
#   1. Checking Directories
# ============================================================
#   ✓ TEMPLATES_DIR: /opt/petrodealhub/document-processor/templates
#   ✓ STORAGE_DIR: /opt/petrodealhub/document-processor/storage
# 
# ============================================================
#   2. Checking deleted_templates.json
# ============================================================
#   ✓ File exists
#   Content: {
#     "deleted_templates": ["test.docx"],
#     "last_updated": "2025-11-15T..."
#   }
# 
# ============================================================
#   7. Checking for Deleted Templates in Filesystem
# ============================================================
#   ✓ Deleted template 'test.docx' not found in filesystem
# 
# ============================================================
#   SUMMARY
# ============================================================
```

---

## نصائح:

- شغّل السكريبت **قبل وبعد** الحذف لرؤية التغييرات
- إذا كان API يعمل، السكريبت سيختبره أيضاً
- تحقق من logs API لرؤية ما يحدث أثناء الحذف:
  ```bash
  sudo journalctl -u petrodealhub-api -f
  ```

