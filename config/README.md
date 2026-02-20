# Config Directory

This directory contains all configuration and credentials for the project.

## Files You Need to Create

After unzipping the project, you need to create these files:

### 1. `.env.local` (Required)
Copy from the template:
```bash
cp config/.env.example config/.env.local
```

Then edit `config/.env.local` with your actual paths:
- Archive source paths
- Archive prefixes
- Ignored folders (optional)

### 2. `credentials.json` (Required for upload)
Download from Google Cloud Console:
1. Go to https://console.cloud.google.com/
2. Enable Photos Library API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download the JSON file
5. Save it as `config/credentials.json`

### 3. `token.pickle` (Auto-generated)
This file is created automatically on first upload when you authenticate with Google.
You don't need to create it manually.

## What's Tracked in Git

- ✅ `.env.example` - Template configuration (tracked)
- ❌ `.env.local` - Your actual config (gitignored)
- ❌ `credentials.json` - OAuth credentials (gitignored)
- ❌ `token.pickle` - Auth token (gitignored)

The `.gitignore` file in this directory ensures your secrets stay private.
