#!/usr/bin/env python3
"""
Multi-Archive Photo Organizer for Google Photos
Handles two different photo archive structures with dry-run capability
"""

import os
import re
import csv
import json
import shutil
import logging
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

# Note: Environment variables loaded by main.py, not here


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


@dataclass
class PhotoFile:
    """Represents a photo file with its metadata"""
    source_path: Path
    album_name: str
    album_title: str
    new_filename: str
    archive_type: str  # Archive identifier (e.g., 'slides', 'portable_drive')
    album_prefix: str = ""  # Optional prefix for Google Photos album title (e.g., 'NZ', 'Ingela')
    date_stamp: Optional[str] = None
    size_bytes: int = 0  # File size in bytes
    
    def get_google_photos_title(self) -> str:
        """Get the album title for Google Photos with optional prefix"""
        if self.album_prefix:
            return f"{self.album_prefix} - {self.album_title}"
        return self.album_title
    
    def get_size_mb(self) -> float:
        """Get file size in megabytes"""
        return self.size_bytes / (1024 * 1024)
    
    def __str__(self):
        return f"{self.archive_type}: {self.source_path.name} -> {self.album_name}/{self.new_filename}"


class PhotoOrganizer:
    """Base class for photo organization"""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        # Use the root logger configured in main.py instead of creating our own
        self.logger = logging.getLogger()
        self.work_dir = Path(os.getenv('WORK_DIR', './photo_work'))
        self.organized_dir = Path(os.getenv('ORGANIZED_DIR', './organized_photos'))
        self.videos_dir = Path(os.getenv('VIDEOS_DIR', './organized_videos'))
        
        # Note: IGNORED_FOLDERS is now only used during UPLOAD stage
        # All folders are organized locally for sharing with others
        # Uploads are filtered in main.py
        
        # Create directories
        if not dry_run:
            self.work_dir.mkdir(exist_ok=True)
            self.organized_dir.mkdir(exist_ok=True)
            self.videos_dir.mkdir(exist_ok=True)


class SlidesArchiveParser:
    """Parser for the slides archive structure"""
    
    FILENAME_PATTERN = re.compile(r'^(\d+)_(\d+)_img_\d+\.JPG$', re.IGNORECASE)
    
    def __init__(self, csv_path: str = None, album_prefix: str = ""):
        """
        Initialize parser with album mapping CSV
        Args:
            csv_path: Path to CSV file. If None, looks for 'lookups/slides_albums.csv'
            album_prefix: Optional prefix for Google Photos album titles (e.g., 'NZ')
        """
        if csv_path is None:
            # Default to lookups subfolder
            # Go up from src/photo_album_organizer to project root
            script_dir = Path(__file__).parent.parent.parent
            csv_path = script_dir / 'lookups' / 'slides_albums.csv'
        
        self.csv_path = Path(csv_path)
        self.album_prefix = album_prefix
        self.album_mapping = self._load_album_mapping()
    
    def _load_album_mapping(self) -> Dict[int, Tuple[str, str]]:
        """Load album number to (name, title) mapping from CSV"""
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"Album mapping CSV not found at: {self.csv_path}\n"
                f"Please ensure slides_albums.csv is in the 'lookups' folder"
            )
        
        mapping = {}
        with open(self.csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                group = int(row['Group'])
                name = row['Name']
                title = row['Title']
                mapping[group] = (name, title)
        return mapping
    
    def parse_filename(self, filename: str) -> Optional[Tuple[int, int]]:
        """
        Parse slides filename pattern: #_##_img_####.JPG
        Returns: (album_number, photo_order) or None
        """
        match = self.FILENAME_PATTERN.match(filename)
        if match:
            album_num = int(match.group(1))
            photo_order = int(match.group(2))
            return (album_num, photo_order)
        return None
    
    def get_photo_info(self, filepath: Path) -> Optional[PhotoFile]:
        """Extract photo information from slides archive file"""
        parsed = self.parse_filename(filepath.name)
        if not parsed:
            return None
        
        album_num, photo_order = parsed
        
        if album_num not in self.album_mapping:
            return None
        
        album_name, album_title = self.album_mapping[album_num]
        
        # Create new filename: AlbumName_##.jpg
        new_filename = f"{album_name}_{photo_order:02d}.jpg"
        
        # Get file size
        size_bytes = filepath.stat().st_size if filepath.exists() else 0
        
        return PhotoFile(
            source_path=filepath,
            album_name=album_name,
            album_title=album_title,
            new_filename=new_filename,
            archive_type='slides',
            album_prefix=self.album_prefix,
            size_bytes=size_bytes
        )


class PortableDriveParser:
    """Parser for the portable drive archive structure"""
    
    DATE_PATTERN = re.compile(r'(\d{4})[_-](\d{2})[_-](\d{2})')
    VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v'}
    PHOTO_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
    
    def __init__(self, album_prefix: str = ""):
        """
        Initialize parser
        Args:
            album_prefix: Optional prefix for Google Photos album titles (e.g., 'Ingela')
        """
        self.album_prefix = album_prefix
    
    def extract_date_from_path(self, path: Path) -> Optional[str]:
        """Extract YYYY_MM_DD date from path components"""
        for part in path.parts:
            match = self.DATE_PATTERN.search(part)
            if match:
                year, month, day = match.groups()
                return f"{year}_{month}_{day}"
        return None
    
    def is_video(self, filepath: Path) -> bool:
        """Check if file is a video"""
        return filepath.suffix.lower() in self.VIDEO_EXTENSIONS
    
    def is_photo(self, filepath: Path) -> bool:
        """Check if file is a photo"""
        return filepath.suffix.lower() in self.PHOTO_EXTENSIONS
    
    def get_album_name_from_path(self, filepath: Path, root: Path) -> str:
        """
        Determine album name from folder structure, cleaning up the name.
        
        Cleaning rules:
        - Removes "Photo album" prefix
        - Removes album number and following dash (e.g., "11 - ")
        
        Examples:
        - "Photo album 11 - 2011-2013 - pre-K - 1st" → "2011-2013 - pre-K - 1st"
        - "3_2009to2010" → "3_2009to2010" (no change)
        """
        # Get relative path from root
        rel_path = filepath.relative_to(root)
        
        # If file is in a subfolder, use the top-level folder name
        if len(rel_path.parts) > 1:
            folder_name = rel_path.parts[0]
        else:
            # If file is in root, use root folder name
            folder_name = root.name
        
        # Clean up folder name: remove "Photo album N - " prefix
        # Matches: "Photo album 8 - ", "Photo album 11 - ", etc.
        folder_name = re.sub(r'^Photo album \d+\s*-\s*', '', folder_name)
        
        return folder_name
    
    def simplify_filename(self, original_name: str, extension: str) -> str:
        """
        Simplify filename according to Ingela naming rules.
        
        Rules applied in order:
        1. Drop year prefixes: "2006 49 IMG_1081" → "49 IMG_1081"
           - Removes 4-digit year at start followed by space/dash/underscore
           - Matches: "2006 ", "2010 - ", "2022_"
        
        2. Drop "IMG" tokens: "49 IMG_1081" → "49 1081"
           - Removes "IMG" with optional space or underscore
           - Case-insensitive: matches "IMG", "img", "Img"
           - Matches: "IMG_", "IMG ", "IMG1081"
        
        3. Clean up artifacts: Remove leading underscores, dashes, spaces
        
        4. Add "photo_" prefix if result is just a number:
           - "49" → "photo_49"
           - "1081" → "photo_1081"
           - "17w" → "photo_17w" (number with letter suffix)
           - "Willow in swing" → "Willow in swing" (descriptive names kept)
        
        Examples:
        - "2006 49 IMG_1081.JPG" → "photo_49.jpg"
        - "2010 - 171.JPG" → "photo_171.jpg"
        - "IMG_6129.JPG" → "photo_6129.jpg"
        - "17w.jpg" → "photo_17w.jpg"
        - "Willow in swing, 20.5 mo..jpg" → "Willow in swing, 20.5 mo..jpg"
        """
        name = original_name
        
        # Rule 1: Drop year prefix (4 digits followed by space, dash, or underscore at start)
        name = re.sub(r'^(\d{4})[\s\-_]+', '', name)
        
        # Rule 2: Drop "IMG" tokens (with optional underscore/space before digits)
        name = re.sub(r'\bIMG[\s_]*', '', name, flags=re.IGNORECASE)
        
        # Rule 3: Clean up any remaining underscores or dashes at the start
        name = name.lstrip('_- ')
        
        # Rule 4: If result is just numbers (possibly with letter suffix), prefix with "photo_"
        # This prevents filenames like "49.jpg" which sort poorly
        if re.match(r'^\d+[a-z]?$', name, re.IGNORECASE):
            name = f"photo_{name}"
        
        return f"{name}{extension}"
    
    def get_photo_info(self, filepath: Path, root: Path) -> Optional[PhotoFile]:
        """Extract photo information from portable drive archive file"""
        if not self.is_photo(filepath):
            return None
        
        # Get cleaned album name from folder structure
        album_name = self.get_album_name_from_path(filepath, root)
        album_title = album_name  # Use folder name as title
        
        # Simplify filename according to rules
        new_filename = self.simplify_filename(filepath.stem, filepath.suffix.lower())
        
        # Extract date stamp if present in path (for metadata, not used in filename now)
        date_stamp = self.extract_date_from_path(filepath)
        
        # Get file size
        size_bytes = filepath.stat().st_size if filepath.exists() else 0
        
        return PhotoFile(
            source_path=filepath,
            album_name=album_name,
            album_title=album_title,
            new_filename=new_filename,
            archive_type='portable_drive',
            album_prefix=self.album_prefix,
            date_stamp=date_stamp,
            size_bytes=size_bytes
        )


class FileOrganizer:
    """Organizes files into local folder structure"""
    
    def __init__(self, organized_dir: Path, videos_dir: Path, dry_run: bool = True):
        self.organized_dir = organized_dir
        self.videos_dir = videos_dir
        self.dry_run = dry_run
        self.logger = logging.getLogger('PhotoOrganizer')
    
    def organize_photo(self, photo: PhotoFile) -> Path:
        """
        Organize a photo into the local folder structure.
        Creates archive-specific subfolders: organized_photos/ingela/ or organized_photos/slides/
        
        Returns the destination path
        """
        # Create archive-specific subfolder (ingela or slides)
        archive_folder = self.organized_dir / photo.archive_type
        album_folder = archive_folder / photo.album_name
        dest_path = album_folder / photo.new_filename
        
        if self.dry_run:
            # Silent in dry-run - detailed preview shown in main.py
            pass
        else:
            album_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(photo.source_path, dest_path)
            self.logger.info(f"Copied: {photo.source_path.name} -> {dest_path}")
        
        return dest_path
    
    def organize_video(self, video_path: Path, silent: bool = False) -> Path:
        """Move video file to videos directory"""
        dest_path = self.videos_dir / video_path.name
        
        if self.dry_run:
            if not silent:
                self.logger.info(f"[DRY RUN] Would copy video: {video_path.name} -> {dest_path}")
        else:
            self.videos_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(video_path, dest_path)
            if not silent:
                self.logger.info(f"Copied video: {video_path.name} -> {dest_path}")
        
        return dest_path


class ArchiveProcessor:
    """Main processor for handling photo archives dynamically from .env configuration"""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.organizer = PhotoOrganizer(dry_run)
        self.logger = self.organizer.logger
        
        # Dynamic archive configuration
        self.archives = self._discover_archives()
        
        self.file_organizer = FileOrganizer(
            self.organizer.organized_dir,
            self.organizer.videos_dir,
            dry_run
        )
        
        self.stats = {
            'errors': 0
        }
        # Add per-archive stats dynamically
        for archive_name in self.archives.keys():
            self.stats[f'{archive_name}_total_files'] = 0
            self.stats[f'{archive_name}_photos_found'] = 0
            self.stats[f'{archive_name}_photos_processed'] = 0
            self.stats[f'{archive_name}_photos_size_bytes'] = 0
            self.stats[f'{archive_name}_videos_found'] = 0
            self.stats[f'{archive_name}_videos_size_bytes'] = 0
    
    def _discover_archives(self) -> Dict[str, Dict]:
        """
        Discover archives from environment variables.
        Returns dict: {archive_name: {'path': Path, 'prefix': str, 'parser': Parser}}
        """
        archives = {}
        i = 1
        
        while True:
            source_key = f'ARCHIVE_{i}_SOURCE_PATH'
            prefix_key = f'ARCHIVE_{i}_ALBUM_PREFIX'
            
            source_path = os.getenv(source_key)
            if not source_path:
                break  # No more archives
            
            # Extract archive name from path (last component)
            archive_name = Path(source_path).name
            album_prefix = os.getenv(prefix_key, "")
            
            # Determine parser type based on archive name
            if archive_name == 'slides':
                parser = SlidesArchiveParser(album_prefix=album_prefix)
            elif archive_name == 'portable_drive':
                parser = PortableDriveParser(album_prefix=album_prefix)
            else:
                self.logger.warning(f"Unknown archive type: {archive_name}, skipping")
                i += 1
                continue
            
            archives[archive_name] = {
                'path': Path(source_path),
                'prefix': album_prefix,
                'parser': parser
            }
            
            self.logger.info(f"Discovered archive: {archive_name} at {source_path}" + 
                           (f" (prefix: '{album_prefix}')" if album_prefix else ""))
            i += 1
        
        if not archives:
            self.logger.warning("No archives discovered! Check your .env.local configuration.")
        
        return archives
    
    def process_archive(self, archive_name: str) -> Dict[str, List[PhotoFile]]:
        """
        Process a specific archive by name.
        Returns: dict of {album_name: [PhotoFile, ...]}
        """
        if archive_name not in self.archives:
            self.logger.error(f"Archive not found: {archive_name}")
            return {}
        
        archive_config = self.archives[archive_name]
        source_path = archive_config['path']
        parser = archive_config['parser']
        
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"Processing {archive_name.upper()} archive: {source_path}")
        self.logger.info(f"{'='*60}")
        
        if not source_path.exists():
            self.logger.error(f"Source path does not exist: {source_path}")
            return {}
        
        photos_by_album = {}
        
        # Process based on parser type
        if isinstance(parser, SlidesArchiveParser):
            photos_by_album = self._process_slides_structure(source_path, parser, archive_name)
        elif isinstance(parser, PortableDriveParser):
            photos_by_album = self._process_portable_drive_structure(source_path, parser, archive_name)
        
        return photos_by_album
    
    def _process_slides_structure(
        self, 
        source_path: Path, 
        parser: SlidesArchiveParser,
        archive_name: str
    ) -> Dict[str, List[PhotoFile]]:
        """Process slides archive structure"""
        photos_by_album = {}
        
        # Count all files first
        for filepath in source_path.iterdir():
            if filepath.is_file():
                self.stats[f'{archive_name}_total_files'] += 1
        
        # Process photo files
        for filepath in source_path.glob('*.JPG'):
            self.stats[f'{archive_name}_photos_found'] += 1
            
            photo = parser.get_photo_info(filepath)
            if photo:
                if photo.album_name not in photos_by_album:
                    photos_by_album[photo.album_name] = []
                photos_by_album[photo.album_name].append(photo)
                self.stats[f'{archive_name}_photos_processed'] += 1
                self.stats[f'{archive_name}_photos_size_bytes'] += photo.size_bytes
            else:
                self.logger.warning(f"Could not parse: {filepath.name}")
                self.stats['errors'] += 1
        
        total_size = self.stats[f'{archive_name}_photos_size_bytes']
        self.logger.info(f"\n{archive_name} Summary:")
        self.logger.info(f"  Total files: {self.stats[f'{archive_name}_total_files']}")
        self.logger.info(f"  Photos found: {self.stats[f'{archive_name}_photos_found']}")
        self.logger.info(f"  Photos processed: {self.stats[f'{archive_name}_photos_processed']}")
        self.logger.info(f"  Total size: {format_size(total_size)}")
        self.logger.info(f"  Albums: {len(photos_by_album)}")
        
        return photos_by_album
    
    def _process_portable_drive_structure(
        self,
        source_path: Path,
        parser: PortableDriveParser,
        archive_name: str
    ) -> Dict[str, List[PhotoFile]]:
        """Process portable drive archive structure"""
        photos_by_album = {}
        videos_shown = 0
        MAX_VIDEO_MESSAGES = 5
        
        for filepath in source_path.rglob('*'):
            if not filepath.is_file():
                continue
            
            # Count all files
            self.stats[f'{archive_name}_total_files'] += 1
            
            # Handle videos
            if parser.is_video(filepath):
                self.stats[f'{archive_name}_videos_found'] += 1
                video_size = filepath.stat().st_size if filepath.exists() else 0
                self.stats[f'{archive_name}_videos_size_bytes'] += video_size
                
                # Only show first few video messages
                if videos_shown < MAX_VIDEO_MESSAGES:
                    dest_video_path = self.organizer.videos_dir / archive_name / filepath.name
                    if self.dry_run:
                        self.logger.info(f"[DRY RUN] Would copy video: {filepath.name} -> {dest_video_path}")
                    else:
                        dest_video_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(filepath, dest_video_path)
                        self.logger.info(f"Copied video: {filepath.name} -> {dest_video_path}")
                    videos_shown += 1
                continue
            
            # Handle photos
            if parser.is_photo(filepath):
                self.stats[f'{archive_name}_photos_found'] += 1
                
                photo = parser.get_photo_info(filepath, source_path)
                if photo:
                    if photo.album_name not in photos_by_album:
                        photos_by_album[photo.album_name] = []
                    photos_by_album[photo.album_name].append(photo)
                    self.stats[f'{archive_name}_photos_processed'] += 1
                    self.stats[f'{archive_name}_photos_size_bytes'] += photo.size_bytes
        
        # Show summary message for remaining videos
        remaining_videos = self.stats[f'{archive_name}_videos_found'] - videos_shown
        if remaining_videos > 0:
            self.logger.info(f"  ... processing {remaining_videos} more videos (not shown)")
        
        photos_size = self.stats[f'{archive_name}_photos_size_bytes']
        videos_size = self.stats[f'{archive_name}_videos_size_bytes']
        total_size = photos_size + videos_size
        
        self.logger.info(f"\n{archive_name} Summary:")
        self.logger.info(f"  Total files: {self.stats[f'{archive_name}_total_files']}")
        self.logger.info(f"  Photos found: {self.stats[f'{archive_name}_photos_found']}")
        self.logger.info(f"  Photos processed: {self.stats[f'{archive_name}_photos_processed']}")
        self.logger.info(f"  Photos size: {format_size(photos_size)}")
        self.logger.info(f"  Videos found: {self.stats[f'{archive_name}_videos_found']}")
        self.logger.info(f"  Videos size: {format_size(videos_size)}")
        self.logger.info(f"  Total size: {format_size(total_size)}")
        self.logger.info(f"  Albums: {len(photos_by_album)}")
        
        return photos_by_album
    
    def organize_files(self, photos_by_album: Dict[str, List[PhotoFile]]) -> Dict[str, Path]:
        """
        Organize all photos into local folder structure
        Returns: dict of {album_name: album_folder_path}
        """
        # Silent during organization - summary shown at end
        album_folders = {}
        
        for album_name, photos in sorted(photos_by_album.items()):
            for photo in photos:
                dest_path = self.file_organizer.organize_photo(photo)
                album_folders[album_name] = dest_path.parent
        
        return album_folders
    
    def print_final_summary(self):
        """Print final processing summary with sizes"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"FINAL SUMMARY")
        self.logger.info(f"{'='*60}")
        
        grand_total_size = 0
        
        for archive_name in self.archives.keys():
            total_files = self.stats.get(f'{archive_name}_total_files', 0)
            photos_found = self.stats.get(f'{archive_name}_photos_found', 0)
            photos_processed = self.stats.get(f'{archive_name}_photos_processed', 0)
            photos_size = self.stats.get(f'{archive_name}_photos_size_bytes', 0)
            videos_found = self.stats.get(f'{archive_name}_videos_found', 0)
            videos_size = self.stats.get(f'{archive_name}_videos_size_bytes', 0)
            archive_total_size = photos_size + videos_size
            grand_total_size += archive_total_size
            
            self.logger.info(f"\n{archive_name} archive:")
            self.logger.info(f"  Total files scanned: {total_files}")
            self.logger.info(f"  Photos found: {photos_found}")
            self.logger.info(f"  Photos processed: {photos_processed}")
            if photos_size > 0:
                self.logger.info(f"  Photos size: {format_size(photos_size)}")
            if videos_found > 0:
                self.logger.info(f"  Videos found: {videos_found}")
                self.logger.info(f"  Videos size: {format_size(videos_size)}")
            if archive_total_size > 0:
                self.logger.info(f"  Archive total: {format_size(archive_total_size)}")
        
        if grand_total_size > 0:
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"GRAND TOTAL: {format_size(grand_total_size)}")
            self.logger.info(f"{'='*60}")
        
        if self.stats['errors'] > 0:
            self.logger.info(f"\nErrors: {self.stats['errors']}")
        
        if self.dry_run:
            self.logger.info(f"\n*** DRY RUN MODE - No files were actually modified ***")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Multi-Archive Photo Organizer for Google Photos'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Run in dry-run mode (default: True)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually execute the file operations (disables dry-run)'
    )
    parser.add_argument(
        '--archive',
        choices=['slides', 'ingela', 'both'],
        default='both',
        help='Which archive to process'
    )
    parser.add_argument(
        '--stage',
        choices=['scan', 'organize', 'upload', 'all'],
        default='scan',
        help='Which stage to run'
    )
    
    args = parser.parse_args()
    
    # Determine dry-run mode
    dry_run = not args.execute
    
    # Create processor
    processor = ArchiveProcessor(dry_run=dry_run)
    
    # Get source paths from environment
    slides_source = Path(os.getenv('SLIDES_SOURCE_PATH', './slides'))
    ingela_source = Path(os.getenv('INGELA_SOURCE_PATH', './ingela'))
    
    all_photos = {}
    
    # Stage 1: Scan archives
    if args.stage in ['scan', 'all']:
        if args.archive in ['slides', 'both']:
            slides_photos = processor.process_slides_archive(slides_source)
            all_photos.update(slides_photos)
        
        if args.archive in ['ingela', 'both']:
            ingela_photos = processor.process_ingela_archive(ingela_source)
            all_photos.update(ingela_photos)
    
    # Stage 2: Organize files
    if args.stage in ['organize', 'all']:
        if all_photos:
            album_folders = processor.organize_files(all_photos)
    
    # Stage 3: Upload to Google Photos (placeholder for now)
    if args.stage in ['upload', 'all']:
        if not dry_run:
            processor.logger.info("\nGoogle Photos upload not yet implemented")
            processor.logger.info("Run with --stage organize first to prepare files")
    
    # Print summary
    processor.print_final_summary()


if __name__ == '__main__':
    main()