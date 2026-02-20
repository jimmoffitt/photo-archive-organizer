# Photo Archive Organizer & Google Photos Uploader

A Python tool to organize photo archives from multiple sources and upload them to Google Photos with proper album organization.

## Features

- **Multi-Archive Support**: Handles multiple photo archive structures dynamically
- **Smart Filename Processing**: Cleans up filenames with customizable rules
- **Album Organization**: Creates well-organized album structures
- **Google Photos Integration**: Uploads organized photos to Google Photos
- **Dry-Run Mode**: Preview all operations before executing
- **Video Handling**: Separates videos into dedicated folder
- **Configurable**: Easy configuration via `.env.local` file

---

## Project Structure

```
photo-processing/
├── src/
│   └── photo_album_organizer/
│       ├── __init__.py
│       ├── main.py                      # Main entry point with CLI
│       ├── photo_organizer_v2.py       # Core organization logic
│       └── google_photos_uploader.py   # Google Photos API integration
├── lookups/
│   └── slides_albums.csv               # Slide album mappings (example: 45 albums)
├── config/
│   ├── .env.example                    # Configuration template
│   ├── .env.local                      # Your configuration (gitignored)
│   ├── credentials.json                # Google OAuth credentials (gitignored)
│   ├── token.pickle                    # Auth token (gitignored)
│   └── .gitignore
├── cache/
│   ├── album_cache.json                # Album ID cache (gitignored)
│   ├── uploaded_photos.json            # Upload tracking (gitignored)
│   └── .gitignore
├── logs/
│   ├── photo_organizer.log             # Application logs (gitignored)
│   └── .gitignore
├── archives/                            # Your source photo archives (gitignored)
│   ├── slides/                         # Example: Slides archive
│   └── portable_drive/                 # Example: Portable drive archive
├── organized_photos/                    # Output directory (gitignored)
│   ├── slides/                         # Organized slides photos
│   └── portable_drive/                 # Organized portable drive photos
├── organized_videos/                    # Separated videos (gitignored)
│   └── portable_drive/                 # Videos from portable drive
├── .gitignore                          # Root gitignore
├── requirements.txt                    # Python dependencies
└── README.md                           # This file
```

---

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Settings

```bash
cp config/.env.example config/.env.local
# Edit config/.env.local with your paths
```

**Required settings in `config/.env.local`:**

```bash
# Source archive locations
ARCHIVE_1_SOURCE_PATH=./archives/slides
ARCHIVE_1_ALBUM_PREFIX=

ARCHIVE_2_SOURCE_PATH=./archives/portable_drive
ARCHIVE_2_ALBUM_PREFIX=Family

# Output directories (will be created)
ORGANIZED_DIR=./organized_photos
VIDEOS_DIR=./organized_videos

# Folders to ignore during upload (not during organize)
# IMPORTANT: Use ORIGINAL source folder names, not organized album names
# Use semicolons (;) as separator to support commas in folder names
IGNORED_FOLDERS=temp_backup;old_duplicates;unsorted_misc

# Google Photos credentials (for upload stage)
GOOGLE_CREDENTIALS_PATH=./config/credentials.json
GOOGLE_TOKEN_PATH=./config/token.pickle
```

**About Ignored Folders:**
- Use the **exact original folder names** from your source archives
- Any file inside these folders (at any depth) will be skipped
- Applies to all archives
- Folder names are case-sensitive
- Use **semicolons (;)** to separate multiple folders (allows commas in names)

### 3. Preview Organization

```bash
# Preview slides archive
python3 -m src.photo_album_organizer.main --dry-run --stage organize --archive slides

# Preview portable_drive archive
python3 -m src.photo_album_organizer.main --dry-run --stage organize --archive portable_drive

# Preview both
python3 -m src.photo_album_organizer.main --dry-run --stage organize --archive all
```

### 4. Execute Organization

```bash
# Organize files (copies to organized_photos/)
python3 -m src.photo_album_organizer.main --execute --stage organize --archive all
```

### 5. Upload to Google Photos (Optional)

```bash
# Upload organized photos
python3 -m src.photo_album_organizer.main --execute --stage upload
```

---

## How It Works

### Three-Stage Pipeline

1. **SCAN**: Discover photos and parse filenames
2. **ORGANIZE**: Copy files to organized folder structure
3. **UPLOAD**: Upload organized photos to Google Photos

### Archive-Specific Processing

#### **Slides Archive**

- **Pattern**: `#_##_img_####.JPG` (album number, photo order, counter)
- **Example**: `5_4_img_0003.JPG`
- **Lookup**: Uses `lookups/slides_albums.csv` to map album numbers to names
- **Output**: `Snowmass_04.jpg` in `organized_photos/slides/Snowmass/`

#### **Portable Drive Archive**

Complex folder structure with date-based organization.

**Filename Cleaning Rules** (applied in order):

1. **Drop year prefixes**: `2006 49 IMG_1081.JPG` → `49 IMG_1081.JPG`
2. **Drop "IMG" tokens**: `49 IMG_1081.JPG` → `49_1081.jpg`
3. **Clean artifacts**: Remove leading underscores/dashes
4. **Add "photo_" prefix**: If result is just a number → `photo_49.jpg`

**Folder Name Cleaning:**
- `Archive 11 - 2010-2015 - School Years` → `2010-2015 - School Years`
- Removes "Archive N - " or "Photo album N - " prefixes

**Examples:**

| Source File | Output File | Album Folder |
|------------|-------------|--------------|
| `2006 49 IMG_1081.JPG` | `photo_49.jpg` | `2006-2007 - WJ infancy` |
| `IMG_6129.JPG` | `photo_6129.jpg` | `3_2009to2010` |
| `17w.jpg` | `photo_17w.jpg` | `2007-2009 - 1 to 3` |
| `Willow in swing, 20.5 mo..jpg` | `Willow in swing, 20.5 mo..jpg` | `3_2009to2010` |

**Output Structure:**
```
organized_photos/portable_drive/
├── 2010-2015 - School Years/
│   ├── photo_49.jpg
│   ├── photo_108.jpg
│   └── ...
├── 2016-2018 - High School/
│   ├── photo_112.jpg
│   └── ...
└── 3_2009to2010/
    ├── photo_6129.jpg
    ├── Willow in swing, 20.5 mo..jpg
    └── ...
```

---

## Command Reference

### Basic Usage

```bash
python3 -m src.photo_album_organizer.main [--dry-run|--execute] --stage STAGE --archive ARCHIVE [OPTIONS]
```

### Options

| Option | Choices | Default | Description |
|--------|---------|---------|-------------|
| `--dry-run` | flag | Yes | Preview without making changes |
| `--execute` | flag | No | Actually perform operations |
| `--stage` | scan, organize, upload, all | scan | Which stage to run |
| `--archive` | slides, portable_drive, all | all | Which archive to process |

**Note:** Archive paths are configured in `.env.local` using `ARCHIVE_N_SOURCE_PATH` variables.

### Common Commands

```bash
# Scan only (see what's found)
python3 -m src.photo_album_organizer.main --dry-run --stage scan --archive both

# Preview organization (see filenames/folders)
python3 -m src.photo_album_organizer.main --dry-run --stage organize --archive portable_drive

# Execute organization (actually copy files)
python3 -m src.photo_album_organizer.main --execute --stage organize --archive both

# Upload to Google Photos
python3 -m src.photo_album_organizer.main --execute --stage upload

# Complete workflow (scan → organize → upload)
python3 -m src.photo_album_organizer.main --execute --stage all --archive both
```

---

## Configuration Details

### Ignored Folders

Specify folders to skip during scanning in `.env.local`:

```bash
IGNORED_FOLDERS=temp,backup,old_duplicates
```

**Rules:**
- Exact folder name matching only (case-sensitive)
- No wildcards or patterns
- Comma-separated list

### Google Photos Setup

1. **Get OAuth Credentials:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable "Photos Library API"
   - Create OAuth 2.0 credentials
   - Download as `credentials.json`

2. **First Run Authentication:**
   - Run upload command
   - Browser will open for OAuth
   - Grant permissions
   - Token saved to `token.pickle`

3. **Rate Limiting:**
   ```bash
   RATE_LIMIT_DELAY=1.0  # Seconds between API calls
   MAX_RETRIES=3
   UPLOAD_BATCH_SIZE=50
   ```

---

## Filename Processing Comments

The code includes detailed comments explaining each filename rule. Key locations:

**`PortableDriveParser.get_album_name_from_path()`**
- Explains folder name cleaning
- Shows regex patterns used

**`PortableDriveParser.simplify_filename()`**
- Documents all 4 filename rules
- Provides before/after examples
- Explains each regex substitution

**`FileOrganizer.organize_photo()`**
- Documents archive subfolder structure
- Shows path construction

---

## Troubleshooting

### No Photos Found

Check your paths in `.env.local`:
```bash
python3 debug_paths.py
```

### Import Errors

Make sure you're in the project directory:
```bash
cd /path/to/photo-processing
python3 -m src.photo_album_organizer.main --dry-run --stage scan
```

### Duplicate Logging

Already fixed! The code uses a single root logger to prevent duplicates.

### Google Photos Authentication Fails

1. Check `credentials.json` exists
2. Delete `token.pickle` and re-authenticate
3. Verify Photos Library API is enabled

---

## Statistics

**Slides Archive:**
- 1,338 photos
- 45 albums
- Pattern: `#_##_img_####.JPG`

**Portable Drive Archive:**
- Example: 4,400+ photos
- Example: 240+ videos (separated)
- Example: 19 albums
- Complex folder structures

**Total:** ~5,700 photos, ~240 videos (varies by archive)

---

## Google Photos API Limitations & Workarounds

### Album Listing Restriction

**Important:** The Google Photos API has a significant limitation - it **cannot list albums you didn't create through the API itself**, even with full read permissions. This is a known API restriction, not a scope or permission issue.

**What this means:**
- If you manually create an album in Google Photos, the API can't see it
- If you create an album through this script, the API can see it
- This limitation exists regardless of OAuth scopes granted

### Local Album Cache Solution

To work around this limitation, the uploader uses a **local JSON cache file** (`album_cache.json`) that stores album IDs:

```json
{
  "Family - 2010-2015 - School Years": "AKhjas8dj2kl3m...",
  "Vacation - Summer 2018": "BMksj3k4jf9sd...",
  ...
}
```

**How it works:**

1. **First run**: Creates albums via API and saves their IDs to cache
2. **Subsequent runs**: Uses cached IDs to find albums (no duplicates!)
3. **Manual albums**: You can manually add album IDs to the cache

### Adding Existing Albums to Cache

If you already have albums in Google Photos and want to avoid duplicates:

1. Open the album in Google Photos
2. Copy the album ID from the URL: `https://photos.google.com/album/ALBUM_ID_HERE`
3. Add to `album_cache.json`:
   ```json
   {
     "Your Album Name": "ALBUM_ID_FROM_URL"
   }
   ```

**Benefits of this approach:**
- ✅ No duplicate albums created
- ✅ Works across multiple runs
- ✅ Can resume interrupted uploads
- ✅ Fast lookups (no API calls needed)

**Note:** If you delete `album_cache.json`, the script will create new albums on the next run (creating duplicates of any existing albums).

---

## Development

### File Structure

- **main.py**: CLI, argument parsing, workflow orchestration
- **photo_organizer_v2.py**: Archive parsing, filename processing, file organization
- **google_photos_uploader.py**: Google Photos API, rate limiting, batch uploads

### Adding New Archives

1. Create new parser class in `photo_organizer_v2.py`
2. Add archive type to `PhotoFile` dataclass
3. Update `ArchiveProcessor` to handle new type
4. Add command-line option in `main.py`

---

## License

Personal use project.

**Need help?** Check the inline comments in the code - they explain each step!
