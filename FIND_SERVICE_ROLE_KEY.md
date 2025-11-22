# How to Find Service Role Key in Supabase

## Step-by-Step Instructions

### Method 1: Supabase Dashboard (Recommended)

1. **Go to your Supabase project**
   - Open: https://supabase.com/dashboard
   - Select your project: `ozjhdxvwqbzcvcywhwjg`

2. **Navigate to Settings**
   - Click on the **gear icon** (⚙️) in the left sidebar
   - Or click **"Project Settings"** at the bottom of the sidebar

3. **Go to API Settings**
   - In the Settings menu, click **"API"**
   - You'll see a page with API keys

4. **Find Service Role Key**
   - Look for a section labeled **"Project API keys"**
   - You'll see two keys:
     - **anon** `public` - This is the one you already have
     - **service_role** `secret` - This is what you need!
   - Click the **eye icon** 👁️ or **"Reveal"** button next to `service_role`
   - Copy the key (it's a long JWT token starting with `eyJ...`)

### Method 2: If You Don't See It

If you don't see the service_role key, it might be hidden for security. Try:

1. **Check if you're the project owner**
   - Only project owners can see the service_role key
   - If you're not the owner, ask the project owner to get it

2. **Look for "Reveal" button**
   - The service_role key is often hidden by default
   - Look for a button that says "Reveal" or an eye icon 👁️
   - Click it to show the key

### Method 3: Alternative - Disable RLS (Not Recommended)

If you can't get the service_role key, we can disable RLS on the table instead. But this is **less secure**.

## Visual Guide

```
Supabase Dashboard
├── Your Project (ozjhdxvwqbzcvcywhwjg)
│   ├── Settings (⚙️ icon)
│   │   ├── API
│   │   │   ├── Project API keys
│   │   │   │   ├── anon public (you have this)
│   │   │   │   └── service_role secret (you need this!) 👁️
```

## What the Service Role Key Looks Like

- Starts with: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...`
- Much longer than the anon key
- Labeled as "service_role" or "secret"
- Usually has a "Reveal" button to show it

## Still Can't Find It?

If you still can't find it, we have two options:

1. **Ask the project owner** to get it for you
2. **Disable RLS on the table** (less secure, but works)

Let me know which option you prefer!

