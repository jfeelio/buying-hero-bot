#!/usr/bin/env python3
"""
Enhanced Master Lis Pendens Automation with Google Drive Integration - FINAL VERSION
=================================================================================
Combines your working components and adds Google Drive upload functionality.
Fixed file coordination between master script and enricher.
"""

import os
import sys
import logging
import subprocess
import shutil
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
import schedule
import time

# Google Drive integration
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

class EnhancedLisPendensAutomation:
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.downloads_dir = self.script_dir / "downloads"
        self.downloads_dir.mkdir(exist_ok=True)
        
        # Set up logging
        self.setup_logging()
        
        # Google Drive setup
        self.SCOPES = ['https://www.googleapis.com/auth/drive.file']
        self.drive_service = None
        self.google_drive_folder_id = "1XIz0x-abhfLb1RGYZBH4fRj16aVxhdNg"  # Your target folder ID
        
    def setup_logging(self):
        """Set up logging configuration with Windows-compatible encoding"""
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        
        # Use Windows-compatible symbols
        self.success_symbol = "[SUCCESS]" if sys.platform == "win32" else "✅"
        self.error_symbol = "[ERROR]" if sys.platform == "win32" else "❌"
        self.warning_symbol = "[WARNING]" if sys.platform == "win32" else "⚠️"
        self.info_symbol = "[INFO]" if sys.platform == "win32" else "📊"
        
        # Configure logging with UTF-8 encoding for file, ASCII-safe for console
        file_handler = logging.FileHandler('lis_pendens_automation.log', encoding='utf-8')
        console_handler = logging.StreamHandler(sys.stdout)
        
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[file_handler, console_handler]
        )
        self.logger = logging.getLogger(__name__)

    def authenticate_google_drive(self):
        """Authenticate with Google Drive API with automatic token refresh"""
        creds = None
        token_file = self.script_dir / 'token.json'
        credentials_file = self.script_dir / 'credentials.json'
        
        # Load existing token
        if token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_file), self.SCOPES)
                self.logger.info("Loaded existing Google Drive credentials")
            except Exception as e:
                self.logger.warning(f"Could not load existing token: {e}")
                creds = None
        
        # Check if credentials are valid or need refresh
        if creds and creds.valid:
            self.logger.info(f"{self.success_symbol} Google Drive credentials are valid")
        elif creds and creds.expired and creds.refresh_token:
            try:
                self.logger.info("Refreshing expired Google Drive token...")
                creds.refresh(Request())
                self.logger.info(f"{self.success_symbol} Google Drive token refreshed successfully")
                
                # Save refreshed credentials
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
                self.logger.info("Saved refreshed token")
                
            except Exception as e:
                self.logger.error(f"{self.error_symbol} Failed to refresh token: {e}")
                self.logger.info("Will need to re-authenticate...")
                creds = None
        else:
            creds = None
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if not credentials_file.exists():
                self.logger.error(f"{self.error_symbol} Google credentials file not found: {credentials_file}")
                self.logger.error("Please download credentials.json from Google Cloud Console")
                self.logger.error("See the setup guide for detailed instructions")
                return False
            
            try:
                self.logger.info("Starting new Google Drive authentication...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_file), self.SCOPES)
                creds = flow.run_local_server(port=0)
                self.logger.info(f"{self.success_symbol} New authentication completed")
                
            except Exception as e:
                self.logger.error(f"{self.error_symbol} Authentication failed: {e}")
                return False
            
            # Save the credentials for the next run
            try:
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
                self.logger.info("Saved new authentication token")
            except Exception as e:
                self.logger.warning(f"Could not save token: {e}")
        
        try:
            self.drive_service = build('drive', 'v3', credentials=creds)
            self.logger.info(f"{self.success_symbol} Google Drive service initialized successfully")
            
            # Test the connection
            about = self.drive_service.about().get(fields="user").execute()
            user_email = about.get('user', {}).get('emailAddress', 'Unknown')
            self.logger.info(f"Connected as: {user_email}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"{self.error_symbol} Failed to initialize Google Drive service: {e}")
            return False

    def upload_to_google_drive(self, file_path, folder_id=None):
        """Upload file to Google Drive with enhanced error handling"""
        if not self.drive_service:
            self.logger.error(f"{self.error_symbol} Google Drive not authenticated")
            return None
        
        try:
            file_name = Path(file_path).name
            file_size = Path(file_path).stat().st_size
            
            self.logger.info(f"Uploading {file_name} ({file_size:,} bytes) to Google Drive...")
            
            file_metadata = {
                'name': file_name,
                'parents': [folder_id] if folder_id else []
            }
            
            media = MediaFileUpload(str(file_path), resumable=True)
            
            # Upload with progress tracking for large files
            request = self.drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,webViewLink,size'
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    self.logger.info(f"   Upload progress: {progress}%")
            
            self.logger.info(f"{self.success_symbol} Successfully uploaded: {file_name}")
            self.logger.info(f"   File ID: {response.get('id')}")
            self.logger.info(f"   View Link: {response.get('webViewLink')}")
            self.logger.info(f"   Size: {response.get('size', 'Unknown')} bytes")
            
            return response
            
        except Exception as e:
            self.logger.error(f"{self.error_symbol} Failed to upload {file_path}: {str(e)}")
            
            # If it's an authentication error, try to refresh
            if "401" in str(e) or "unauthorized" in str(e).lower():
                self.logger.info("Authentication error detected, trying to refresh...")
                if self.authenticate_google_drive():
                    self.logger.info("Retrying upload after authentication refresh...")
                    return self.upload_to_google_drive(file_path, folder_id)
            
            return None

    def run_script(self, script_name, description):
        """Run a Python script and return success status"""
        self.logger.info(f"Running {description}...")
        
        try:
            result = subprocess.run([
                sys.executable, script_name
            ], capture_output=True, text=True, cwd=self.script_dir)
            
            if result.returncode == 0:
                self.logger.info(f"{self.success_symbol} {description} completed successfully")
                return True
            else:
                self.logger.error(f"{self.error_symbol} {description} failed:")
                self.logger.error(f"STDOUT: {result.stdout}")
                self.logger.error(f"STDERR: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"{self.error_symbol} Error running {script_name}: {str(e)}")
            return False

    def find_and_prepare_raw_file(self):
        """Find the correct raw file and prepare it for processing"""
        date_str = datetime.now().strftime("%Y%m%d")
        
        # Try to find the most recent raw file
        possible_patterns = [
            f"lis_pendens_raw_{date_str}*.csv",
            "Official Records Search Results*.csv",  # All numbered variations
            f"*raw*{date_str}*.csv", 
            f"lis_pendens_{date_str}*.csv"
        ]
        
        selected_file = None
        
        for pattern in possible_patterns:
            files = list(self.downloads_dir.glob(pattern))
            if files:
                # Sort by creation time (most recent first) to get today's fresh download
                files_by_creation = sorted(files, key=lambda x: x.stat().st_ctime, reverse=True)
                candidate = files_by_creation[0]
                
                # Check the content to verify it has recent data
                try:
                    df_check = pd.read_csv(candidate, nrows=1)
                    if 'Rec Date' in df_check.columns:
                        rec_date = df_check['Rec Date'].iloc[0] if len(df_check) > 0 else None
                        self.logger.info(f"Checking file {candidate.name}: Rec Date = {rec_date}")
                        
                        # Look for recent dates (within last week)
                        if rec_date and ('9/22/2025' in str(rec_date) or '9/23/2025' in str(rec_date)):
                            selected_file = candidate
                            self.logger.info(f"Found file with recent data: {candidate.name}")
                            break
                except Exception as e:
                    self.logger.warning(f"Could not check content of {candidate.name}: {e}")
                    continue
        
        if not selected_file:
            # Fall back to most recent file if no date matching found
            all_files = []
            for pattern in possible_patterns:
                all_files.extend(self.downloads_dir.glob(pattern))
            
            if all_files:
                selected_file = max(all_files, key=lambda x: x.stat().st_ctime)
                self.logger.warning(f"No recent data found, using most recent file: {selected_file.name}")
        
        if not selected_file:
            self.logger.error(f"{self.error_symbol} No raw file found")
            return None
        
        # Log details about selected file
        file_stat = selected_file.stat()
        created_time = datetime.fromtimestamp(file_stat.st_ctime)
        file_size = file_stat.st_size
        
        self.logger.info(f"Selected raw file: {selected_file.name}")
        self.logger.info(f"  Created: {created_time}")
        self.logger.info(f"  Size: {file_size:,} bytes")
        
        # Verify content
        try:
            df_verify = pd.read_csv(selected_file)
            if 'Rec Date' in df_verify.columns:
                unique_dates = df_verify['Rec Date'].unique()
                self.logger.info(f"  Contains {len(df_verify)} records with dates: {list(unique_dates)}")
            else:
                self.logger.warning(f"  No 'Rec Date' column found")
        except Exception as e:
            self.logger.warning(f"Could not verify file content: {e}")
        
        # Prepare file for enricher by creating standard names
        standard_name = self.downloads_dir / "Official Records Search Results.csv"
        renamed_file = self.downloads_dir / f"lis_pendens_raw_{date_str}.csv"
        
        # Remove old standard file if it exists
        if standard_name.exists():
            standard_name.unlink()
            self.logger.info(f"Removed old standard file")
        
        # Copy selected file to standard name for enricher
        shutil.copy2(selected_file, standard_name)
        self.logger.info(f"Created standard copy for enricher: {standard_name.name}")
        
        # Also create renamed copy for consistency
        if selected_file != renamed_file:
            if renamed_file.exists():
                renamed_file.unlink()
            shutil.copy2(selected_file, renamed_file)
            self.logger.info(f"Created renamed copy: {renamed_file.name}")
        
        return renamed_file

    def format_for_mail_service(self, enriched_file):
        """Format enriched data for mail service using proven formatter logic"""
        try:
            df = pd.read_csv(enriched_file)
            self.logger.info(f"Formatting {len(df)} records for mail service...")
            
            # Create the final formatted dataframe using your proven logic
            formatted_records = []
            
            for _, row in df.iterrows():
                # Handle LLC names - if no last name, put full name in first name
                owner_first = row.get('owner_first_name', '')
                owner_last = row.get('owner_last_name', '')
                
                if not owner_last or pd.isna(owner_last) or str(owner_last).strip() == '':
                    # No last name - this is likely an LLC/company
                    if owner_first:
                        formatted_first_name = str(owner_first).strip()
                        formatted_last_name = ''
                    else:
                        # Fall back to defendant name if available
                        defendant = row.get('defendant', '')
                        if defendant:
                            formatted_first_name = str(defendant).strip()
                            formatted_last_name = ''
                        else:
                            formatted_first_name = ''
                            formatted_last_name = ''
                else:
                    # Has both names - keep as is
                    formatted_first_name = str(owner_first).strip() if owner_first else ''
                    formatted_last_name = str(owner_last).strip() if owner_last else ''
                
                # Clean zip codes to 5 digits only
                def clean_zip(zip_code):
                    if pd.isna(zip_code) or zip_code == '':
                        return ''
                    zip_str = str(zip_code).strip()
                    # Extract first 5 digits
                    import re
                    digits = re.findall(r'\d', zip_str)
                    if len(digits) >= 5:
                        return ''.join(digits[:5])
                    elif len(digits) > 0:
                        return ''.join(digits)
                    else:
                        return ''
                
                mailing_zip_clean = clean_zip(row.get('mailing_zip', ''))
                property_zip_clean = clean_zip(row.get('property_zip', ''))
                
                # Format Zillow value as integer (no decimals)
                zillow_value = row.get('zillow_estimate', '')
                if pd.notna(zillow_value) and zillow_value != '':
                    try:
                        zillow_formatted = f"${int(float(zillow_value)):,}"
                    except:
                        zillow_formatted = ''
                else:
                    zillow_formatted = ''
                
                # Create formatted record with exact column names from screenshot
                formatted_record = {
                    'Owner First Name': formatted_first_name,
                    'Owner Last Name': formatted_last_name,
                    'Mailing Address': str(row.get('mailing_address', '')).strip(),
                    'Mailing City': str(row.get('mailing_city', '')).strip(),
                    'Mailing State': str(row.get('mailing_state', '')).strip(),
                    'Mailing Zip': mailing_zip_clean,
                    'Address': str(row.get('property_address', '')).strip(),
                    'City': str(row.get('property_city', '')).strip(),
                    'State': str(row.get('property_state', '')).strip(),
                    'Zip': property_zip_clean,
                    'Value': zillow_formatted
                }
                
                formatted_records.append(formatted_record)
            
            # Create final dataframe
            final_df = pd.DataFrame(formatted_records)
            
            # Create mail-ready filename
            date_str = datetime.now().strftime("%Y%m%d")
            mail_ready_file = self.downloads_dir / f"lis_pendens_mail_ready_{date_str}.csv"
            
            final_df.to_csv(mail_ready_file, index=False)
            self.logger.info(f"Mail-ready file saved as: {mail_ready_file}")
            
            # Show formatting summary
            self.logger.info(f"Formatting Summary:")
            self.logger.info(f"  Records with first names: {(final_df['Owner First Name'] != '').sum()}")
            self.logger.info(f"  Records with last names: {(final_df['Owner Last Name'] != '').sum()}")
            self.logger.info(f"  Records with mailing addresses: {(final_df['Mailing Address'] != '').sum()}")
            self.logger.info(f"  Records with property addresses: {(final_df['Address'] != '').sum()}")
            self.logger.info(f"  Records with Zillow values: {(final_df['Value'] != '').sum()}")
            
            return mail_ready_file
            
        except Exception as e:
            self.logger.error(f"{self.error_symbol} Error formatting for mail service: {str(e)}")
            return None

    def analyze_zillow_results(self, enriched_file):
        """Analyze Zillow enrichment results and identify missing data"""
        try:
            df = pd.read_csv(enriched_file)
            
            total_records = len(df)
            zillow_records = len(df[df['zillow_estimate'].notna() & (df['zillow_estimate'] != '')])
            success_rate = (zillow_records / total_records * 100) if total_records > 0 else 0
            
            self.logger.info(f"Zillow Analysis:")
            self.logger.info(f"  Total records: {total_records}")
            self.logger.info(f"  Records with Zillow estimates: {zillow_records}")
            self.logger.info(f"  Success rate: {success_rate:.1f}%")
            
            # Identify records without Zillow data
            missing_zillow = df[df['zillow_estimate'].isna() | (df['zillow_estimate'] == '')]
            if not missing_zillow.empty:
                self.logger.info(f"Records missing Zillow data:")
                for idx, row in missing_zillow.iterrows():
                    address = f"{row.get('property_address', 'Unknown')} {row.get('property_city', '')} {row.get('property_state', '')}"
                    self.logger.info(f"  - {address.strip()}")
            
            return {
                'total': total_records,
                'with_zillow': zillow_records,
                'success_rate': success_rate,
                'missing_addresses': missing_zillow['property_address'].tolist() if not missing_zillow.empty else []
            }
            
        except Exception as e:
            self.logger.error(f"{self.error_symbol} Error analyzing Zillow results: {str(e)}")
            return None

    def cleanup_temp_files(self):
        """Clean up temporary files"""
        try:
            temp_patterns = [
                'enriched_lis_pendens_final_*.csv',
                'Official Records Search Results.csv'
            ]
            
            for pattern in temp_patterns:
                for file_path in self.script_dir.glob(pattern):
                    file_path.unlink()
                    self.logger.info(f"Cleaned up: {file_path.name}")
                    
        except Exception as e:
            self.logger.error(f"{self.error_symbol} Error during cleanup: {str(e)}")

    def run_complete_automation(self):
        """Run the complete automation process"""
        self.logger.info("=" * 50)
        self.logger.info("Enhanced Master Lis Pendens Automation - FINAL VERSION")
        self.logger.info("=" * 50)
        
        date_str = datetime.now().strftime("%Y%m%d")
        
        # Step 1: Raw data download
        self.logger.info("Step 1: Running raw Lis Pendens download...")
        if not self.run_script("fully_automated_scraper.py", "Raw download"):
            self.logger.error(f"{self.error_symbol} Raw download failed - stopping automation")
            return False
        
        # Step 2: Find and prepare the correct raw file
        self.logger.info("Step 2: Finding and preparing raw file...")
        raw_file = self.find_and_prepare_raw_file()
        if not raw_file:
            return False
        
        # Step 3: Enrichment (will now use the prepared standard file)
        self.logger.info("Step 3: Running enrichment...")
        if not self.run_script("fixed_enricher.py", "Enrichment"):
            self.logger.warning(f"{self.warning_symbol} Enrichment had issues - continuing with partial results")
        
        # Find the enriched file
        enriched_patterns = [
            f"enriched_lis_pendens_final_{date_str}*.csv",
            "enriched_lis_pendens_final_*.csv"
        ]
        
        enriched_file = None
        for pattern in enriched_patterns:
            files = list(self.downloads_dir.glob(pattern))
            if files:
                enriched_file = max(files, key=lambda x: x.stat().st_ctime)
                break
        
        if not enriched_file:
            self.logger.error(f"{self.error_symbol} Enriched file not found")
            return False
        
        self.logger.info(f"Found enriched file: {enriched_file.name}")
        
        # Analyze Zillow results
        zillow_analysis = self.analyze_zillow_results(enriched_file)
        
        # Step 4: Format for mail service
        self.logger.info("Step 4: Formatting for mail service...")
        mail_ready_file = self.format_for_mail_service(enriched_file)
        if not mail_ready_file:
            self.logger.error(f"{self.error_symbol} Mail formatting failed")
            return False
        
        # Step 5: Upload to Google Drive
        self.logger.info("Step 5: Uploading to Google Drive...")
        
        if self.authenticate_google_drive():
            files_to_upload = [
                (raw_file, "Raw Lis Pendens Data"),
                (enriched_file, "Enriched Lis Pendens Data"), 
                (mail_ready_file, "Mail-Ready Lis Pendens Data")
            ]
            
            uploaded_files = []
            upload_success_count = 0
            
            for file_path, description in files_to_upload:
                if file_path.exists():
                    self.logger.info(f"Uploading {description}...")
                    result = self.upload_to_google_drive(file_path, self.google_drive_folder_id)
                    if result:
                        uploaded_files.append(result)
                        upload_success_count += 1
                    else:
                        self.logger.error(f"{self.error_symbol} Failed to upload {file_path.name}")
                else:
                    self.logger.warning(f"{self.warning_symbol} File not found for upload: {file_path}")
            
            self.logger.info(f"Upload Summary: {upload_success_count}/{len(files_to_upload)} files uploaded successfully")
            
            if upload_success_count > 0:
                self.logger.info("Access your files at: https://drive.google.com/drive/folders/1XIz0x-abhfLb1RGYZBH4fRj16aVxhdNg")
        else:
            self.logger.warning(f"{self.warning_symbol} Google Drive upload skipped - authentication failed")
            self.logger.info("   Files are still available locally in the downloads folder")
        
        # Step 6: Cleanup
        self.logger.info("Step 6: Cleaning up temporary files...")
        self.cleanup_temp_files()
        
        # Final summary
        self.logger.info("=" * 50)
        self.logger.info("AUTOMATION RESULTS - FINAL")
        self.logger.info("=" * 50)
        self.logger.info(f"{self.success_symbol} Raw file: {raw_file.name}")
        self.logger.info(f"{self.success_symbol} Enriched file: {enriched_file.name}")
        self.logger.info(f"{self.success_symbol} Mail-ready file: {mail_ready_file.name}")
        
        if zillow_analysis:
            self.logger.info(f"\nProcessing Summary for {datetime.now().strftime('%Y-%m-%d')}:")
            self.logger.info(f"  Records processed: {zillow_analysis['total']}")
            self.logger.info(f"  Records with Zillow estimates: {zillow_analysis['with_zillow']}")
            self.logger.info(f"  Zillow success rate: {zillow_analysis['success_rate']:.1f}%")
            
            if zillow_analysis['missing_addresses']:
                self.logger.info(f"\nAddresses missing Zillow data (may need manual lookup):")
                for addr in zillow_analysis['missing_addresses']:
                    self.logger.info(f"  - {addr}")
        
        self.logger.info(f"\nLocal files saved in: {self.downloads_dir}")
        self.logger.info(f"Google Drive folder: https://drive.google.com/drive/folders/1XIz0x-abhfLb1RGYZBH4fRj16aVxhdNg")
        self.logger.info(f"{self.success_symbol} Automation complete!")
        
        return True

    def schedule_automation(self, run_time="09:00"):
        """Schedule automation to run daily"""
        self.logger.info(f"Scheduling daily automation at {run_time}")
        
        schedule.every().day.at(run_time).do(self.run_complete_automation)
        
        self.logger.info("Scheduler started. Press Ctrl+C to stop.")
        self.logger.info(f"Next run scheduled for: {run_time}")
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            self.logger.info("Scheduler stopped by user")

def main():
    automation = EnhancedLisPendensAutomation()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "schedule":
            # Run in scheduled mode
            run_time = sys.argv[2] if len(sys.argv) > 2 else "09:00"
            automation.schedule_automation(run_time)
        elif sys.argv[1] == "test-drive":
            # Test Google Drive connection
            if automation.authenticate_google_drive():
                print(f"{automation.success_symbol} Google Drive authentication successful")
            else:
                print(f"{automation.error_symbol} Google Drive authentication failed")
    else:
        # Run once immediately
        automation.run_complete_automation()

if __name__ == "__main__":
    main()
