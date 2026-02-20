#!/usr/bin/env python3
"""
Google Photos Uploader with Rate Limiting
Handles authentication, album creation, and batch uploads
"""

import os
import pickle
import time
import logging
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


SCOPES = [
    'https://www.googleapis.com/auth/photoslibrary',
    'https://www.googleapis.com/auth/photoslibrary.appendonly',
    'https://www.googleapis.com/auth/photoslibrary.readonly'
]


@dataclass
class UploadResult:
    """Result of a photo upload operation"""
    success: bool
    photo_path: Path
    album_name: str
    error: Optional[str] = None
    media_item_id: Optional[str] = None


class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
    
    def wait(self):
        """Wait if necessary to respect rate limit"""
        now = time.time()
        time_since_last = now - self.last_call
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_call = time.time()


class GooglePhotosUploader:
    """Upload photos to Google Photos with rate limiting and error handling"""
    
    def __init__(
        self,
        credentials_path: str = 'credentials.json',
        token_path: str = 'token.pickle',
        rate_limit: float = 1.0,
        max_retries: int = 3,
        dry_run: bool = False,
        test_mode: bool = False,
        interactive: bool = False,
        album_cache_path: str = 'album_cache.json',
        uploaded_photos_path: str = 'uploaded_photos.json'
    ):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.album_cache_path = album_cache_path
        self.uploaded_photos_path = uploaded_photos_path
        self.max_retries = max_retries
        self.dry_run = dry_run
        self.test_mode = test_mode  # Only upload first album + first photo
        self.interactive = interactive  # Pause after each album for user confirmation
        
        self.service = None
        self.rate_limiter = RateLimiter(rate_limit)
        
        # Initialize logger before loading cache (cache needs logger)
        self.logger = logging.getLogger('GooglePhotosUploader')
        
        # Load album cache (needs logger to be initialized first)
        self.album_cache: Dict[str, str] = self._load_album_cache()
        
        # Load uploaded photos tracking
        self.uploaded_photos: Dict[str, str] = self._load_uploaded_photos()
        
        self.stats = {
            'albums_created': 0,
            'albums_found': 0,
            'photos_uploaded': 0,
            'photos_skipped': 0,
            'photos_failed': 0,
            'bytes_uploaded': 0,
            'api_calls': 0,
            'retries': 0
        }
    
    def _load_album_cache(self) -> Dict[str, str]:
        """Load album cache from JSON file"""
        if os.path.exists(self.album_cache_path):
            try:
                with open(self.album_cache_path, 'r') as f:
                    cache = json.load(f)
                    self.logger.info(f"Loaded {len(cache)} albums from cache")
                    return cache
            except Exception as e:
                self.logger.warning(f"Could not load album cache: {e}")
        return {}
    
    def _save_album_cache(self):
        """Save album cache to JSON file"""
        try:
            with open(self.album_cache_path, 'w') as f:
                json.dump(self.album_cache, f, indent=2)
            self.logger.debug(f"Saved {len(self.album_cache)} albums to cache")
        except Exception as e:
            self.logger.warning(f"Could not save album cache: {e}")
    
    def _load_uploaded_photos(self) -> Dict[str, str]:
        """
        Load uploaded photos tracking from JSON file.
        Format: {file_path: media_item_id}
        """
        if os.path.exists(self.uploaded_photos_path):
            try:
                with open(self.uploaded_photos_path, 'r') as f:
                    cache = json.load(f)
                    self.logger.info(f"Loaded {len(cache)} uploaded photos from cache")
                    return cache
            except Exception as e:
                self.logger.warning(f"Could not load uploaded photos cache: {e}")
        return {}
    
    def _save_uploaded_photos(self):
        """Save uploaded photos tracking to JSON file"""
        try:
            with open(self.uploaded_photos_path, 'w') as f:
                json.dump(self.uploaded_photos, f, indent=2)
            self.logger.debug(f"Saved {len(self.uploaded_photos)} uploaded photos to cache")
        except Exception as e:
            self.logger.warning(f"Could not save uploaded photos cache: {e}")
    
    def authenticate(self) -> bool:
        """
        Authenticate with Google Photos API
        Returns True if successful
        """
        if self.dry_run:
            self.logger.info("[DRY RUN] Would authenticate with Google Photos")
            return True
        
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, 'rb') as token:
                    creds = pickle.load(token)
                self.logger.info("Loaded existing credentials")
            except Exception as e:
                self.logger.warning(f"Could not load token: {e}")
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    self.logger.info("Refreshed credentials")
                except Exception as e:
                    self.logger.error(f"Could not refresh credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.credentials_path):
                    self.logger.error(f"Credentials file not found: {self.credentials_path}")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
                self.logger.info("Obtained new credentials")
            
            # Save credentials
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        # Build service
        self.service = build('photoslibrary', 'v1', credentials=creds, static_discovery=False)
        self.logger.info("✓ Successfully authenticated with Google Photos")
        return True
    
    def get_or_create_album(self, album_name: str, album_title: str) -> Optional[str]:
        """
        Get album from cache or create new album in Google Photos.
        Uses local JSON cache since Google Photos API can't list albums created outside the app.
        Returns album ID or None on error
        """
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would get/create album: {album_name} - {album_title}")
            return f"dry_run_album_{album_name}"
        
        # Check cache first (includes albums from previous runs)
        cache_key = f"{album_title}"  # Use title as key for matching
        if cache_key in self.album_cache:
            album_id = self.album_cache[cache_key]
            self.stats['albums_found'] += 1
            self.logger.info(f"  Found album in cache: {album_title}")
            return album_id
        
        # Album not in cache, create new one
        try:
            self.rate_limiter.wait()
            self.stats['api_calls'] += 1
            
            request_body = {
                'album': {'title': album_title}
            }
            response = self.service.albums().create(body=request_body).execute()
            album_id = response['id']
            
            # Save to cache
            self.album_cache[cache_key] = album_id
            self._save_album_cache()
            
            self.stats['albums_created'] += 1
            self.logger.info(f"  Created new album: {album_title}")
            return album_id
            
        except HttpError as e:
            self.logger.error(f"Error creating album {album_name}: {e}")
            return None
    
    def get_album_media_items(self, album_id: str) -> Dict[str, str]:
        """
        Get existing media items in an album.
        Returns dict of {filename: media_item_id}
        Note: This requires reading from the album which may have permission issues.
        """
        if self.dry_run:
            return {}
        
        existing_files = {}
        
        try:
            self.rate_limiter.wait()
            self.stats['api_calls'] += 1
            
            page_token = None
            while True:
                if page_token:
                    response = self.service.mediaItems().search(
                        body={'albumId': album_id, 'pageSize': 100, 'pageToken': page_token}
                    ).execute()
                else:
                    response = self.service.mediaItems().search(
                        body={'albumId': album_id, 'pageSize': 100}
                    ).execute()
                
                media_items = response.get('mediaItems', [])
                for item in media_items:
                    filename = item.get('filename', '')
                    media_id = item.get('id', '')
                    if filename:
                        existing_files[filename] = media_id
                
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
                    
        except HttpError as e:
            # Expected: appendonly scope can't read album contents
            # Silently fall back to uploading all photos
            self.logger.debug(f"Cannot read album contents (expected with appendonly scope): {e}")
            return {}
        
        return existing_files
    
    def filter_existing_photos(
        self, 
        photo_paths: List[Path], 
        album_id: str
    ) -> Tuple[List[Path], int]:
        """
        Filter out photos that have already been uploaded (using local cache).
        Returns: (photos_to_upload, skipped_count)
        """
        if self.dry_run:
            return photo_paths, 0
        
        # Filter out photos that are already in our upload cache
        photos_to_upload = []
        skipped = 0
        
        for photo_path in photo_paths:
            # Use absolute path as key for tracking
            abs_path = str(photo_path.resolve())
            
            if abs_path in self.uploaded_photos:
                self.logger.debug(f"  Skipping (already uploaded): {photo_path.name}")
                skipped += 1
            else:
                photos_to_upload.append(photo_path)
        
        if skipped > 0:
            self.logger.info(f"  Skipping {skipped} photo(s) already uploaded")
            self.stats['photos_skipped'] += skipped
        
        return photos_to_upload, skipped
    
    def upload_photo(
        self,
        file_path: Path,
        album_id: str,
        retries: int = 0
    ) -> UploadResult:
        """
        Upload a single photo to Google Photos
        Returns UploadResult with success status
        """
        if self.dry_run:
            return UploadResult(
                success=True,
                photo_path=file_path,
                album_name="dry_run",
                media_item_id="dry_run_id"
            )
        
        try:
            # Step 1: Upload bytes to Google Photos using raw upload endpoint
            self.rate_limiter.wait()
            self.stats['api_calls'] += 1
            
            import requests
            
            # Get the upload URL
            upload_url = 'https://photoslibrary.googleapis.com/v1/uploads'
            
            # Read file bytes
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            # Get credentials token
            creds = self.service._http.credentials
            access_token = creds.token
            
            # Upload bytes
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-type': 'application/octet-stream',
                'X-Goog-Upload-File-Name': file_path.name,
                'X-Goog-Upload-Protocol': 'raw'
            }
            
            upload_response = requests.post(upload_url, data=file_bytes, headers=headers)
            
            if upload_response.status_code != 200:
                raise Exception(f"Upload failed with status {upload_response.status_code}: {upload_response.text}")
            
            upload_token = upload_response.text
            
            # Step 2: Create media item in album
            self.rate_limiter.wait()
            self.stats['api_calls'] += 1
            
            request_body = {
                'albumId': album_id,
                'newMediaItems': [{
                    'description': file_path.name,
                    'simpleMediaItem': {
                        'uploadToken': upload_token
                    }
                }]
            }
            
            response = self.service.mediaItems().batchCreate(body=request_body).execute()
            
            # Check if creation was successful
            results = response.get('newMediaItemResults', [])
            if results and results[0].get('status', {}).get('message') == 'Success':
                media_item = results[0].get('mediaItem', {})
                media_item_id = media_item.get('id')
                self.stats['photos_uploaded'] += 1
                # Track bytes uploaded
                file_size = len(file_bytes)
                self.stats['bytes_uploaded'] += file_size
                
                # Track this upload in our cache
                abs_path = str(file_path.resolve())
                self.uploaded_photos[abs_path] = media_item_id
                self._save_uploaded_photos()
                
                return UploadResult(
                    success=True,
                    photo_path=file_path,
                    album_name=album_id,
                    media_item_id=media_item_id
                )
            else:
                error_msg = results[0].get('status', {}).get('message', 'Unknown error')
                raise Exception(error_msg)
        
        except Exception as e:
            error_msg = str(e)
            self.logger.warning(f"Upload failed for {file_path.name}: {error_msg}")
            
            # Retry logic
            if retries < self.max_retries:
                self.stats['retries'] += 1
                self.logger.info(f"Retrying ({retries + 1}/{self.max_retries})...")
                time.sleep(2 ** retries)  # Exponential backoff
                return self.upload_photo(file_path, album_id, retries + 1)
            
            self.stats['photos_failed'] += 1
            return UploadResult(
                success=False,
                photo_path=file_path,
                album_name=album_id,
                error=error_msg
            )
    
    def upload_batch(
        self,
        photo_paths: List[Path],
        album_id: str,
        batch_size: int = 50
    ) -> List[UploadResult]:
        """
        Upload a batch of photos to an album
        Returns list of UploadResults
        """
        results = []
        total = len(photo_paths)
        
        for i, photo_path in enumerate(photo_paths, 1):
            self.logger.info(f"  [{i}/{total}] Uploading: {photo_path.name}")
            
            result = self.upload_photo(photo_path, album_id)
            results.append(result)
            
            if not result.success:
                self.logger.error(f"    Failed: {result.error}")
        
        return results
    
    def upload_albums(
        self,
        albums: Dict[str, Tuple[str, List[Path]]],
        batch_size: int = 50
    ) -> Dict[str, List[UploadResult]]:
        """
        Upload multiple albums.
        
        Test mode: Only processes first album with first photo.
        Interactive mode: Pauses after each album for user confirmation.
        Dry run: Simulates all operations without API calls.
        
        albums: Dict[album_name: (album_title, [photo_paths])]
        Returns: Dict[album_name: [UploadResults]]
        """
        all_results = {}
        
        if self.test_mode:
            self.logger.info("\n" + "="*60)
            self.logger.info("🧪 TEST MODE: Only uploading first album + first photo")
            self.logger.info("="*60)
        
        if self.interactive and not self.dry_run:
            self.logger.info("\n" + "="*60)
            self.logger.info("📋 INTERACTIVE MODE: Will pause after each album")
            self.logger.info("="*60)
        
        for i, (album_name, (album_title, photo_paths)) in enumerate(albums.items(), 1):
            self.logger.info(f"\n[{i}/{len(albums)}] Processing album: {album_title} ({len(photo_paths)} photos)")
            
            # Get or create album
            album_id = self.get_or_create_album(album_name, album_title)
            if not album_id:
                self.logger.error(f"Could not get/create album: {album_name}")
                if self.test_mode:
                    self.logger.info("\n🧪 TEST MODE: Stopping due to error")
                    break
                continue
            
            # Filter out already-uploaded photos
            photos_to_upload, skipped_count = self.filter_existing_photos(photo_paths, album_id)
            
            if not photos_to_upload:
                self.logger.info(f"  All {len(photo_paths)} photos already uploaded, skipping album")
                all_results[album_name] = []
                continue
            
            # Track bytes before upload
            bytes_before = self.stats['bytes_uploaded']
            
            # In test mode, only upload first photo
            if self.test_mode:
                test_photos = photos_to_upload[:1]
                self.logger.info(f"  Test mode: Uploading only first photo (out of {len(photos_to_upload)} new)")
                results = self.upload_batch(test_photos, album_id, batch_size)
            else:
                # Upload new photos
                self.logger.info(f"  Uploading {len(photos_to_upload)} new photo(s)")
                results = self.upload_batch(photos_to_upload, album_id, batch_size)
            
            all_results[album_name] = results
            
            # Calculate bytes uploaded for this album
            bytes_this_album = self.stats['bytes_uploaded'] - bytes_before
            
            # Show mini summary for this album
            successful = sum(1 for r in results if r.success)
            failed = len(results) - successful
            self.logger.info(f"  ✓ Uploaded: {successful}, ✗ Failed: {failed}, ⊘ Skipped: {skipped_count}")
            self.logger.info(f"  📊 Size: {format_size(bytes_this_album)}")
            
            # Interactive pause (unless in test/dry-run mode)
            if self.interactive and not self.dry_run and not self.test_mode:
                remaining = len(albums) - i
                if remaining > 0:
                    print(f"\n{'='*60}")
                    print(f"Album '{album_title}' complete.")
                    print(f"Remaining: {remaining} album(s)")
                    print("="*60)
                    choice = input("Continue? [y=yes, n=no, q=quit]: ").lower().strip()
                    
                    if choice in ['q', 'quit', 'exit', 'stop']:
                        self.logger.info("\n⏸️  User quit. Stopping upload.")
                        break
                    elif choice in ['n', 'no', 'skip']:
                        self.logger.info(f"\n⏭️  Skipping remaining {remaining} album(s)")
                        break
                    elif choice in ['y', 'yes', '']:
                        # Continue to next album
                        continue
                    else:
                        # Unknown input, ask for clarification
                        print(f"Unknown choice '{choice}'. Continuing...")
                        continue
            
            # In test mode, stop after first album
            if self.test_mode:
                remaining_albums = len(albums) - 1
                if remaining_albums > 0:
                    self.logger.info(f"\n  Test mode: Skipping {remaining_albums} remaining albums")
                self.logger.info("\n" + "="*60)
                self.logger.info("🧪 TEST MODE COMPLETE")
                self.logger.info("="*60)
                break
        
        return all_results
    
    def print_stats(self):
        """Print upload statistics"""
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"UPLOAD STATISTICS")
        self.logger.info(f"{'='*60}")
        self.logger.info(f"Albums created: {self.stats['albums_created']}")
        self.logger.info(f"Albums found: {self.stats['albums_found']}")
        self.logger.info(f"Photos uploaded: {self.stats['photos_uploaded']}")
        self.logger.info(f"Photos skipped (already exist): {self.stats['photos_skipped']}")
        self.logger.info(f"Photos failed: {self.stats['photos_failed']}")
        self.logger.info(f"Total uploaded: {format_size(self.stats['bytes_uploaded'])}")
        self.logger.info(f"API calls made: {self.stats['api_calls']}")
        self.logger.info(f"Retries: {self.stats['retries']}")


if __name__ == '__main__':
    # Simple test
    logging.basicConfig(level=logging.INFO)
    uploader = GooglePhotosUploader(dry_run=True)
    
    if uploader.authenticate():
        print("Authentication successful")
        uploader.print_stats()
