# Project Structure

This document explains the clean, organized structure of the photo processing project.

## Directory Layout

```
photo-processing/
├── src/
│   └── photo_album_organizer/
│       ├── main.py                    # Main entry point
│       ├── photo_organizer_v2.py      # Archive scanning and organizing
│       └── google_photos_uploader.py  # Google Photos API integration
├── lookups/
│   └── slides_albums.csv              # Album number to name/title mapping
├── config/
│   ├── .env.example                   # Environment configuration template
│   ├── .env.local                     # Your actual config (gitignored)
│   ├── credentials.json               # Google OAuth credentials (gitignored)
│   ├── token.pickle                   # Auth token (gitignored)
│   └── .gitignore                     # Ignores everything except .env.example
├── cache/
│   ├── album_cache.json               # Maps album names to Google Photos IDs (gitignored)
│   ├── uploaded_photos.json           # Tracks uploaded photos (gitignored)
│   └── .gitignore                     # Ignores all cache files
├── logs/
│   ├── photo_organizer.log            # Application logs (gitignored)
│   └── .gitignore                     # Ignores all log files
├── .gitignore                          # Root gitignore
├── requirements.txt                    # Python dependencies
└── README.md                           # Main documentation
```

## Running the Application

The main script is located at `src/photo_album_organizer/main.py`.

### From Project Root:

```bash
python3 src/photo_album_organizer/main.py --dry-run --stage scan --archive all
```

### With a Helper Script:

Create a `run.sh` in the project root:

```bash
#!/bin/bash
python3 src/photo_album_organizer/main.py "$@"
```

Then use:

```bash
chmod +x run.sh
./run.sh --dry-run --stage scan --archive all
```

## Configuration Files

All configuration is centralized in the `config/` directory:

- **`.env.example`** - Template configuration file (tracked in git)
- **`.env.local`** - Your actual configuration (gitignored, create from .env.example)
- **`credentials.json`** - Google OAuth credentials (gitignored, download from Google Cloud Console)
- **`token.pickle`** - Authentication token (gitignored, created on first run)

## Cache Files

The `cache/` directory stores runtime state:

- **`album_cache.json`** - Maps album names to Google Photos album IDs to avoid duplicates
- **`uploaded_photos.json`** - Tracks which photos have been uploaded

Both files are gitignored. Delete them to reset the application state.

## Logs

Application logs are stored in `logs/photo_organizer.log` (gitignored).

## Output Directories

The following directories are created during execution (gitignored by default):

- **`organized_photos/`** - Organized photo files by archive and album
- **`organized_videos/`** - Video files separated from photos
- **`photo_work/`** - Temporary working directory

## Git Best Practices

The project is configured to ignore:
- All secrets and credentials (`config/.env.local`, `config/credentials.json`, `config/token.pickle`)
- All generated cache files (`cache/*`)
- All logs (`logs/*`)
- Python build artifacts (`__pycache__`, `*.pyc`, etc.)

Only committed files:
- Source code (`src/`)
- Documentation (`README.md`, etc.)
- Configuration template (`config/.env.example`)
- Dependencies (`requirements.txt`)
- Album mapping (`lookups/slides_albums.csv`)

## First Time Setup

1. **Copy environment template:**
   ```bash
   cp config/.env.example config/.env.local
   ```

2. **Edit `config/.env.local`** with your paths and settings

3. **Place Google credentials:**
   ```bash
   # Download credentials.json from Google Cloud Console
   mv ~/Downloads/credentials.json config/
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run a dry-run test:**
   ```bash
   python3 src/photo_album_organizer/main.py --dry-run --stage scan --archive all
   ```
