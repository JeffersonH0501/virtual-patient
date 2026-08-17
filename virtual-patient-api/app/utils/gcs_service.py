"""
Google Cloud Storage Service
Handles uploading files to Google Cloud Storage and generating public URLs.
"""

import os
import tempfile
from typing import Optional
from app.core.config import settings

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False
    print("⚠️  google-cloud-storage not installed. GCS functionality will be disabled.")

class GCSService:
    """Service for uploading files to Google Cloud Storage."""
    
    def __init__(self):
        # Get GCS configuration from environment variables
        self.bucket_name = settings.gcs_bucket_name
        self.credentials_path = settings.gcs_credentials_path
        
        # Initialize GCS client
        self.client = None
        self.bucket = None
        
        if not GCS_AVAILABLE:
            print("⚠️  GCS Service: google-cloud-storage package not installed")
            return
        
        if self.bucket_name:
            try:
                if self.credentials_path and os.path.exists(self.credentials_path):
                    # Use explicit credentials file
                    self.client = storage.Client.from_service_account_json(self.credentials_path)
                    print(f"✅ GCS Service initialized with credentials: {self.credentials_path}")
                else:
                    # Try to use default credentials (e.g., from environment or gcloud auth)
                    self.client = storage.Client()
                    print("✅ GCS Service initialized with default credentials")
                
                self.bucket = self.client.bucket(self.bucket_name)
                print(f"✅ GCS bucket connected: {self.bucket_name}")
            except Exception as e:
                print(f"⚠️  GCS Service initialization failed: {e}")
                print("   GCS uploads will be disabled until credentials are configured")
                self.client = None
                self.bucket = None
        else:
            print("⚠️  GCS_BUCKET_NAME not set - GCS uploads will be disabled")
    
    def upload_file(
        self,
        file_path: str,
        destination_path: str,
        content_type: str = "audio/mpeg",
        make_public: bool = True
    ) -> Optional[str]:
        """
        Upload a file to Google Cloud Storage.
        
        Args:
            file_path: Local path to the file to upload
            destination_path: Path in the GCS bucket (e.g., "audio/interview_123/message_456.mp3")
            content_type: MIME type of the file (default: "audio/mpeg")
            make_public: Whether to make the file publicly accessible (default: True)
            
        Returns:
            Public URL of the uploaded file, or None if upload failed
        """
        if not self.bucket:
            print("❌ GCS Service: Bucket not initialized. Check GCS_BUCKET_NAME and credentials.")
            return None
        
        if not os.path.exists(file_path):
            print(f"❌ GCS Service: File not found: {file_path}")
            return None
        
        try:
            print(f"📤 Uploading to GCS: {destination_path}")
            
            # Create blob
            blob = self.bucket.blob(destination_path)
            
            # Upload file
            blob.upload_from_filename(file_path, content_type=content_type)
            print(f"✅ File uploaded to GCS: {destination_path}")
            
            # Make public if requested
            if make_public:
                blob.make_public()
                public_url = blob.public_url
                print(f"✅ File made public: {public_url}")
                return public_url
            else:
                # Return a signed URL or the blob path
                return f"gs://{self.bucket_name}/{destination_path}"
                
        except Exception as e:
            print(f"❌ GCS upload failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def upload_audio_bytes(
        self,
        audio_data: bytes,
        destination_path: str,
        content_type: str = "audio/mpeg",
        make_public: bool = True
    ) -> Optional[str]:
        """
        Upload audio bytes directly to Google Cloud Storage.
        
        Args:
            audio_data: Audio data as bytes
            destination_path: Path in the GCS bucket
            content_type: MIME type of the file (default: "audio/mpeg")
            make_public: Whether to make the file publicly accessible (default: True)
            
        Returns:
            Public URL of the uploaded file, or None if upload failed
        """
        if not self.bucket:
            print("❌ GCS Service: Bucket not initialized. Check GCS_BUCKET_NAME and credentials.")
            return None
        
        try:
            print(f"📤 Uploading audio bytes to GCS: {destination_path}")
            
            # Create blob
            blob = self.bucket.blob(destination_path)
            
            # Upload from bytes
            blob.upload_from_string(audio_data, content_type=content_type)
            print(f"✅ Audio uploaded to GCS: {destination_path} ({len(audio_data):,} bytes)")
            
            # Make public if requested
            # Handle uniform bucket-level access (no legacy ACL)
            if make_public:
                try:
                    # Try legacy ACL method first (for buckets without uniform access)
                    blob.make_public()
                    public_url = blob.public_url
                    print(f"✅ Audio made public via ACL: {public_url}")
                    return public_url
                except Exception as acl_error:
                    # If uniform bucket-level access is enabled, we can't use legacy ACL
                    if "uniform bucket-level access" in str(acl_error).lower():
                        # With uniform bucket-level access, objects inherit bucket permissions
                        # The public URL will work if bucket-level IAM policy allows public access
                        public_url = blob.public_url
                        print(f"✅ Uniform bucket-level access enabled - using bucket-level permissions")
                        print(f"✅ Public URL generated: {public_url}")
                        print(f"   (Object inherits public access from bucket IAM policy)")
                        return public_url
                    else:
                        # Re-raise if it's a different error
                        raise
            else:
                return f"gs://{self.bucket_name}/{destination_path}"
                
        except Exception as e:
            print(f"❌ GCS upload failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def delete_file(self, destination_path: str) -> bool:
        """
        Delete a file from Google Cloud Storage.
        
        Args:
            destination_path: Path in the GCS bucket
            
        Returns:
            True if deletion was successful, False otherwise
        """
        if not self.bucket:
            return False
        
        try:
            blob = self.bucket.blob(destination_path)
            blob.delete()
            print(f"✅ File deleted from GCS: {destination_path}")
            return True
        except Exception as e:
            print(f"❌ GCS delete failed: {e}")
            return False
