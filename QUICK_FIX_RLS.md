# Quick Fix: RLS Issue - Use Systemd Service File (RECOMMENDED)

## Why Systemd Service File is Better:
✅ **More Secure** - Environment variables not in project directory  
✅ **Faster** - No need to modify .env or restart multiple times  
✅ **Production-Ready** - Standard practice for system services  
✅ **Isolated** - Configuration separate from code  

## Quick Steps (2 minutes):

### 1. Get Service Role Key
- Go to Supabase Dashboard → Settings → API
- Copy the **service_role** key (starts with `eyJ...`)

### 2. Add to Systemd Service (One Command)
```bash
sudo bash -c 'cat >> /etc/systemd/system/petrodealhub-api.service << EOF

# Supabase Service Role Key (bypasses RLS)
Environment="SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY_HERE"
EOF'
```

**Then edit it:**
```bash
sudo nano /etc/systemd/system/petrodealhub-api.service
```
Replace `YOUR_SERVICE_ROLE_KEY_HERE` with your actual service role key.

### 3. Reload and Restart
```bash
sudo systemctl daemon-reload
sudo systemctl restart petrodealhub-api
```

### 4. Verify It's Working
```bash
sudo systemctl status petrodealhub-api
# Should show: "Successfully connected to Supabase (using service_role key for backend operations)"
```

### 5. Test Save Plan
Try saving a plan in the CMS - it should work now!

## Done! ✅

This is the fastest and safest method for production.

