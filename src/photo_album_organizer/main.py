#!/usr/bin/env python3
"""
Complete Photo Archive Organizer and Google Photos Uploader
Integrates all components: scanning, organizing, and uploading
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Determine project root (parent of src/)
project_root = Path(__file__).parent.parent.parent

# Load environment from config/.env.local file
env_path = project_root / 'config' / '.env.local'
load_dotenv(env_path)

# Current directory is already src/photo_album_organizer, so modules are importable
# No need to modify sys.path

# Import our modules from src/photo_album_organizer folder
try:
    from photo_organizer_v2 import (
        ArchiveProcessor,
        PhotoFile
    )
    from google_photos_uploader import GooglePhotosUploader
except ImportError as e:
    print(f"Error importing modules: {e}")
    print(f"Make sure the 'src/photo_album_organizer' folder exists with photo_organizer_v2.py and google_photos_uploader.py")
    print(f"Looking in: {Path(__file__).parent}")
    sys.exit(1)


def setup_logging(dry_run: bool) -> logging.Logger:
    """Configure logging for the application"""
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_file = os.getenv('LOG_FILE', 'photo_organizer.log')
    
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level))
    
    # CRITICAL: Clear any existing handlers to prevent duplicates
    logger.handlers.clear()
    
    # Console handler with clean format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(message)s')  # No prefix for clean output
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler (only when executing)
    if not dry_run:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger


def prepare_upload_data(
    photos_by_album: Dict[str, List[PhotoFile]],
    organized_dir: Path
) -> Dict[str, Tuple[str, List[Path]]]:
    """
    Prepare data structure for Google Photos upload
    Returns: {album_name: (album_title, [photo_paths])}
    """
    upload_data = {}
    
    for album_name, photos in photos_by_album.items():
        if not photos:
            continue
        
        # Get album title from first photo
        album_title = photos[0].album_title
        
        # Get organized photo paths
        album_folder = organized_dir / album_name
        photo_paths = list(album_folder.glob('*.jpg')) + list(album_folder.glob('*.jpeg'))
        
        if photo_paths:
            upload_data[album_name] = (album_title, photo_paths)
    
    return upload_data


def main():
    """Main application entry point"""
    
    parser = argparse.ArgumentParser(
        description='Complete Photo Archive Organizer and Google Photos Uploader',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run - scan both archives
  python main.py --dry-run --stage scan --archive both
  
  # Organize slides archive into local folders
  python main.py --execute --stage organize --archive slides
  
  # Upload organized photos to Google Photos
  python main.py --execute --stage upload
  
  # Complete workflow for slides
  python main.py --execute --stage all --archive slides
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='Run in dry-run mode (show what would happen)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        default=False,
        help='Execute actual file operations'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        default=False,
        help='Test mode: Only upload first album + first photo (for testing Google Photos connection)'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        default=False,
        help='Interactive mode: Pause after each album upload for confirmation'
    )
    parser.add_argument(
        '--archive',
        type=str,
        default='all',
        help='Which archive to process (use archive name or "all")'
    )
    parser.add_argument(
        '--stage',
        choices=['scan', 'organize', 'upload', 'all'],
        default='scan',
        help='Which processing stage to run'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.dry_run and args.execute:
        print("Error: Cannot specify both --dry-run and --execute")
        sys.exit(1)
    
    # Default to dry-run if neither specified
    dry_run = True
    if args.execute:
        dry_run = False
        
        # Confirm execution
        print("\n" + "="*60)
        print("WARNING: You are about to execute actual file operations")
        print("="*60)
        response = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Operation cancelled.")
            sys.exit(0)
    
    # Setup logging
    logger = setup_logging(dry_run)
    
    # Print configuration
    logger.info("="*60)
    logger.info("Photo Archive Organizer")
    logger.info("="*60)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info(f"Archive: {args.archive}")
    logger.info(f"Stage: {args.stage}")
    logger.info("="*60)
    
    # Get output directory
    organized_dir = Path(os.getenv('ORGANIZED_DIR', './organized_photos'))
    
    # Show configuration
    logger.info(f"Output: {organized_dir}")
    logger.info("")
    
    # Create processor (discovers archives from .env)
    processor = ArchiveProcessor(dry_run=dry_run)
    
    # Determine which archives to process
    if args.archive == 'all':
        archives_to_process = list(processor.archives.keys())
    elif args.archive in processor.archives:
        archives_to_process = [args.archive]
    else:
        logger.error(f"Unknown archive: {args.archive}")
        logger.info(f"Available archives: {', '.join(processor.archives.keys())}")
        sys.exit(1)
    
    logger.info(f"Will process: {', '.join(archives_to_process)}")
    logger.info("")
    
    all_photos = {}
    
    # =================================================================
    # STAGE 1: SCAN
    # =================================================================
    if args.stage in ['scan', 'organize', 'all']:
        logger.info("\n" + "="*60)
        logger.info("STAGE 1: SCANNING ARCHIVES")
        logger.info("="*60)
        
        for archive_name in archives_to_process:
            archive_photos = processor.process_archive(archive_name)
            all_photos.update(archive_photos)
        
        if not all_photos:
            logger.warning("No photos found to process!")
            logger.warning("Check your source paths in .env.local (ARCHIVE_N_SOURCE_PATH)")
            if args.stage == 'scan':
                # For scan stage, just show what we checked and exit gracefully
                logger.info("\nScanned locations:")
                for archive_name in archives_to_process:
                    archive_path = processor.archives[archive_name]['path']
                    logger.info(f"  {archive_name}: {archive_path} (exists: {archive_path.exists()})")
            else:
                # For other stages, we need photos
                sys.exit(1)
        
        # Print what was found
        logger.info(f"\nFound {len(all_photos)} albums with photos:")
        for album_name, photos in sorted(all_photos.items()):
            logger.info(f"  {album_name}: {len(photos)} photos")
            if photos and dry_run:
                # Show first sample in dry-run
                sample = photos[0]
                logger.info(f"    Example: {sample.source_path.name} → {sample.new_filename}")
    
    # =================================================================
    # STAGE 2: ORGANIZE
    # =================================================================
    if args.stage in ['organize', 'all']:
        logger.info("\n" + "="*60)
        logger.info("STAGE 2: ORGANIZING FILES")
        logger.info("="*60)
        
        if all_photos:
            album_folders = processor.organize_files(all_photos)
            logger.info(f"\nOrganized {len(album_folders)} albums")
            
            # Print detailed dry-run report
            if dry_run:
                logger.info("\n" + "="*60)
                logger.info("DRY-RUN PREVIEW: What would be created")
                logger.info("="*60)
                
                total_files = 0
                for album_name in sorted(all_photos.keys()):
                    photos = all_photos[album_name]
                    if not photos:
                        continue
                    
                    album_title = photos[0].album_title
                    archive_type = photos[0].archive_type
                    total_files += len(photos)
                    
                    logger.info(f"\n📁 Album: {album_name}")
                    logger.info(f"   Google Photos Title: \"{album_title}\"")
                    logger.info(f"   Archive: {archive_type}")
                    logger.info(f"   Local folder: {organized_dir / archive_type / album_name}/")
                    logger.info(f"   Photos: {len(photos)}")
                    
                    # Show first 3 and last 2 files as examples
                    logger.info("   File transformations:")
                    num_to_show = min(5, len(photos))
                    samples = photos[:3] + (photos[-2:] if len(photos) > 5 else [])
                    
                    for i, photo in enumerate(samples[:num_to_show], 1):
                        if i == 4 and len(photos) > 5:
                            logger.info(f"     ... {len(photos) - 5} more files ...")
                        logger.info(f"     • {photo.source_path.name}")
                        logger.info(f"       → {photo.new_filename}")
                
                logger.info("\n" + "="*60)
                logger.info(f"📊 SUMMARY")
                logger.info(f"   Total files: {total_files}")
                logger.info(f"   Total albums: {len(all_photos)}")
                logger.info(f"   Output directory: {organized_dir.resolve()}")
                logger.info("="*60)
                logger.info("\n💡 To execute these changes:")
                logger.info(f"   python main.py --execute --stage organize --archive {args.archive}")
        else:
            logger.warning("No photos to organize (run scan stage first)")
    
    # =================================================================
    # STAGE 3: UPLOAD
    # =================================================================
    if args.stage in ['upload', 'all']:
        logger.info("\n" + "="*60)
        logger.info("STAGE 3: UPLOADING TO GOOGLE PHOTOS")
        logger.info("="*60)
        
        if not organized_dir.exists():
            logger.error(f"Organized directory not found: {organized_dir}")
            logger.error("Run --stage organize first to prepare files")
            sys.exit(1)
        
        # Prepare upload data from organized directory (including archive subfolders)
        upload_data = {}
        
        # Re-discover archives for upload (or reuse from earlier stages)
        temp_processor = ArchiveProcessor(dry_run=True)  # Just to get archive config
        
        # Determine which archives to scan based on --archive flag
        if args.archive == 'all':
            archives_to_scan = list(temp_processor.archives.keys())
        elif args.archive in temp_processor.archives:
            archives_to_scan = [args.archive]
        else:
            # Fallback for archives not discovered (shouldn't happen)
            archives_to_scan = []
        
        logger.info(f"Scanning archives for upload: {', '.join(archives_to_scan)}")
        
        # Load slides CSV mapping for proper Google Photos titles
        slides_title_mapping = {}
        slides_csv = project_root / 'lookups' / 'slides_albums.csv'
        if slides_csv.exists():
            import csv
            with open(slides_csv, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    folder_name = row['Name']  # Folder name (e.g., "Snowmass")
                    title = row['Title']  # Google Photos title (e.g., "Snowmass")
                    slides_title_mapping[folder_name] = title
            logger.info(f"Loaded {len(slides_title_mapping)} slides album titles")
        
        # Load IGNORED_FOLDERS (source folder names) and map to cleaned album names
        ignored_folders_str = os.getenv('IGNORED_FOLDERS', '')
        ignored_source_folders = set(
            folder.strip() 
            for folder in ignored_folders_str.split(';') 
            if folder.strip()
        )
        
        # Import the parser to clean folder names the same way organize stage does
        from photo_organizer_v2 import PortableDriveParser
        parser = PortableDriveParser()
        
        # Map ignored source folders to their cleaned album names
        upload_ignore = set()
        for source_folder in ignored_source_folders:
            # Clean the folder name using same logic as parser
            import re
            cleaned = re.sub(r'^Photo album \d+\s*-\s*', '', source_folder)
            upload_ignore.add(cleaned)
        
        if upload_ignore:
            logger.info(f"Skipping albums during upload (from IGNORED_FOLDERS): {', '.join(sorted(upload_ignore))}")
        
        # Scan organized_photos/ARCHIVE_NAME/ folders
        for archive_folder in organized_dir.iterdir():
            if not archive_folder.is_dir():
                continue
            
            archive_name = archive_folder.name
            
            # Check if this is an archive subfolder we want to upload
            if archive_name in archives_to_scan and archive_name in temp_processor.archives:
                # Get prefix for this archive
                album_prefix = temp_processor.archives[archive_name]['prefix']
                
                # Scan albums within the archive folder
                for album_folder in archive_folder.iterdir():
                    if album_folder.is_dir():
                        album_name = album_folder.name
                        
                        # Skip if this album is derived from an ignored source folder
                        if album_name in upload_ignore:
                            logger.info(f"Skipping album (from IGNORED_FOLDERS): {album_name}")
                            continue
                        
                        photo_paths = (
                            list(album_folder.glob('*.jpg')) + 
                            list(album_folder.glob('*.jpeg')) +
                            list(album_folder.glob('*.JPG'))
                        )
                        if photo_paths:
                            # For slides archive, use Title from CSV; otherwise use folder name
                            if archive_name == 'slides' and album_name in slides_title_mapping:
                                base_title = slides_title_mapping[album_name]
                            else:
                                base_title = album_name
                            
                            # Build Google Photos title with prefix if present
                            if album_prefix:
                                google_photos_title = f"{album_prefix} - {base_title}"
                            else:
                                google_photos_title = base_title
                            
                            upload_data[album_name] = (google_photos_title, photo_paths)
            elif archive_name not in temp_processor.archives:
                # Direct album folder (backward compatibility - not in archive subfolders)
                album_name = archive_folder.name
                photo_paths = (
                    list(archive_folder.glob('*.jpg')) + 
                    list(album_folder.glob('*.jpeg')) +
                    list(archive_folder.glob('*.JPG'))
                )
                if photo_paths:
                    upload_data[album_name] = (album_name, photo_paths)
        
        if not upload_data:
            logger.warning("No organized photos found to upload")
        else:
            logger.info(f"Found {len(upload_data)} albums to upload")
            
            if args.test:
                logger.info("🧪 TEST MODE ENABLED: Will only upload first album + first photo")
            
            # Create uploader
            credentials_path = os.getenv('GOOGLE_CREDENTIALS_PATH', './config/credentials.json')
            token_path = os.getenv('GOOGLE_TOKEN_PATH', './config/token.pickle')
            album_cache_path = os.getenv('ALBUM_CACHE_PATH', './cache/album_cache.json')
            uploaded_photos_path = os.getenv('UPLOADED_PHOTOS_PATH', './cache/uploaded_photos.json')
            rate_limit = float(os.getenv('RATE_LIMIT_DELAY', '1.0'))
            max_retries = int(os.getenv('MAX_RETRIES', '3'))
            batch_size = int(os.getenv('UPLOAD_BATCH_SIZE', '50'))
            
            uploader = GooglePhotosUploader(
                credentials_path=credentials_path,
                token_path=token_path,
                album_cache_path=album_cache_path,
                uploaded_photos_path=uploaded_photos_path,
                rate_limit=1.0 / rate_limit,  # Convert delay to calls per second
                max_retries=max_retries,
                dry_run=dry_run,
                test_mode=args.test,  # Pass test mode flag
                interactive=args.interactive  # Pass interactive mode flag
            )
            
            # Authenticate
            if not uploader.authenticate():
                logger.error("Failed to authenticate with Google Photos")
                sys.exit(1)
            
            # Upload albums
            results = uploader.upload_albums(upload_data, batch_size)
            
            # Print results
            uploader.print_stats()
    
    # =================================================================
    # FINAL SUMMARY
    # =================================================================
    processor.print_final_summary()
    
    if dry_run:
        logger.info("\n" + "="*60)
        logger.info("This was a DRY RUN - no files were modified")
        logger.info("Run with --execute to perform actual operations")
        logger.info("="*60)


if __name__ == '__main__':
    main()
