#!/usr/bin/env python3
"""
Lis Pendens Enricher — uses Miami-Dade PA live API instead of static CSV.
Replaces property_data.csv lookup with real-time MDPA API calls.
"""

import glob
import logging
import os
import re
import time
import urllib.parse
from typing import Dict, Optional, Tuple

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import mdpa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FixedPropertyEnricher:
    def load_lis_pendens_data(self) -> pd.DataFrame:
        """Load the original Lis Pendens CSV"""
        filepath = os.path.join("downloads", "Official Records Search Results.csv")

        if not os.path.exists(filepath):
            download_dir = os.path.join(os.getcwd(), "downloads")
            csv_files = glob.glob(os.path.join(download_dir, "*.csv"))
            original_files = [
                f for f in csv_files
                if "enriched" not in f.lower() and "mail_ready" not in f.lower()
            ]
            if original_files:
                filepath = max(original_files, key=os.path.getctime)
            else:
                raise FileNotFoundError("No original Lis Pendens file found")

        logger.info(f"Loading Lis Pendens data from: {filepath}")
        return pd.read_csv(filepath)

    def parse_party_names(self, party_name: str) -> Dict[str, str]:
        """Parse party names to extract owner information"""
        if pd.isna(party_name) or "/" not in str(party_name):
            return {"plaintiff": "", "defendant": "", "owner_first": "", "owner_last": ""}

        parts = [part.strip() for part in str(party_name).split("/")]
        owner_candidate = parts[1] if len(parts) > 1 else parts[0]

        if any(kw in owner_candidate.upper() for kw in ["LLC", "INC", "CORP", "BANK", "MORTGAGE", "CAPITAL", "FUNDING", "TRUST"]):
            return {
                "plaintiff": parts[0] if parts else "",
                "defendant": owner_candidate,
                "owner_first": "",
                "owner_last": "",
            }

        first_name, last_name = self.parse_individual_name(owner_candidate)
        return {
            "plaintiff": parts[0] if parts else "",
            "defendant": owner_candidate,
            "owner_first": first_name,
            "owner_last": last_name,
        }

    def parse_individual_name(self, name: str) -> Tuple[str, str]:
        """Extract first and last name from individual name"""
        if not name:
            return "", ""
        name = re.sub(r'\b(MR|MRS|MS|DR|JR|SR|III|II)\b\.?', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+', ' ', name).strip()
        parts = name.split()
        if len(parts) >= 2:
            return parts[0], parts[-1]
        if len(parts) == 1:
            return "", parts[0]
        return "", ""

    def scrape_zillow_estimate(self, address: str, city: str, state: str, zip_code: str) -> Optional[float]:
        """Scrape Zillow for property estimate"""
        if not address or not city:
            return None

        driver = None
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(30)

            full_address = f"{address}, {city}, {state} {zip_code}".strip()
            encoded_address = urllib.parse.quote(full_address)
            zillow_url = f"https://www.zillow.com/homes/{encoded_address}_rb/"

            logger.info(f"Getting Zillow estimate for: {full_address}")
            driver.get(zillow_url)
            time.sleep(4)

            price_selectors = [
                "[data-testid='price']",
                "[data-testid='zestimate-text']",
                ".Text-c11n-8-85-1__sc-aiai24-0.notranslate",
                ".zestimate-value",
            ]

            for selector in price_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        price_match = re.search(r'\$([0-9,]+)', element.text)
                        if price_match:
                            price = float(price_match.group(1).replace(',', ''))
                            if 50000 <= price <= 50000000:
                                logger.info(f"Found Zillow estimate: ${price:,.0f}")
                                return price
                except Exception:
                    continue

            logger.info(f"No Zillow estimate found for {address}")
            return None

        except Exception as e:
            logger.error(f"Zillow scraping failed for {address}: {e}")
            return None
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def enrich_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Main enrichment function — uses MDPA live API per record."""
        logger.info(f"Starting enrichment of {len(df)} Lis Pendens records via MDPA API...")

        enriched_records = []
        mdpa_cache = {}

        for idx, row in df.iterrows():
            logger.info(f"Processing record {idx + 1}/{len(df)}")

            try:
                party_info = self.parse_party_names(row.get("Party Name", ""))
                address = str(row.get("Address", "")).strip()

                # MDPA live lookup
                if address and address.lower() != "nan":
                    if address in mdpa_cache:
                        owner_info = mdpa_cache[address]
                        logger.info(f"Using cached MDPA data for {address}")
                    else:
                        owner_info = mdpa.get_owner_info(address)
                        mdpa_cache[address] = owner_info
                else:
                    owner_info = {}

                # Prefer MDPA owner name over parsed party name (more reliable)
                if owner_info.get("owner_first") or owner_info.get("owner_last"):
                    party_info["owner_first"] = owner_info["owner_first"]
                    party_info["owner_last"] = owner_info["owner_last"]

                # Zillow estimate
                zillow_estimate = None
                if address and address.lower() != "nan":
                    zillow_estimate = self.scrape_zillow_estimate(
                        address,
                        owner_info.get("property_city") or owner_info.get("mailing_city", "Miami"),
                        "FL",
                        owner_info.get("mailing_zip", ""),
                    )
                    time.sleep(3)

                enriched_records.append({
                    "clerks_file_number": row.get("Clerk's File Number", ""),
                    "document_type": row.get("Document Type", ""),
                    "recording_date": row.get("Rec Date", ""),
                    "legal_description": row.get("Legal", ""),
                    "original_address": row.get("Address", ""),
                    "original_party_name": row.get("Party Name", ""),
                    "owner_first_name": party_info["owner_first"],
                    "owner_last_name": party_info["owner_last"],
                    "plaintiff": party_info["plaintiff"],
                    "defendant": party_info["defendant"],
                    "property_address": address,
                    "property_city": owner_info.get("property_city", ""),
                    "property_state": "FL",
                    "property_zip": "",
                    "mailing_address": owner_info.get("mailing_address", ""),
                    "mailing_city": owner_info.get("mailing_city", ""),
                    "mailing_state": owner_info.get("mailing_state", ""),
                    "mailing_zip": owner_info.get("mailing_zip", ""),
                    "zillow_estimate": zillow_estimate,
                })

            except Exception as e:
                logger.error(f"Error processing record {idx + 1}: {e}")
                continue

        df_enriched = pd.DataFrame(enriched_records)
        if len(df_enriched) > 0:
            return self.clean_and_deduplicate(df_enriched)
        return df_enriched

    def clean_and_deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicates based on property address"""
        logger.info(f"Starting with {len(df)} records")
        df_dedup = df.drop_duplicates(subset=["property_address"], keep="first")
        logger.info(f"After removing duplicates: {len(df_dedup)} records")
        return df_dedup.reset_index(drop=True)

    def save_enriched_data(self, df: pd.DataFrame) -> str:
        """Save enriched data"""
        timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        filename = f"enriched_lis_pendens_final_{timestamp}.csv"
        filepath = os.path.join("downloads", filename)
        df.to_csv(filepath, index=False)
        logger.info(f"Final enriched data saved to: {filepath}")
        return filepath


def main():
    print("Lis Pendens Property Enricher — MDPA Live API")
    print("=" * 40)

    enricher = FixedPropertyEnricher()

    try:
        df = enricher.load_lis_pendens_data()
        print(f"Loaded {len(df)} Lis Pendens records")
        print(f"Records with addresses: {(df['Address'].notna() & (df['Address'] != '')).sum()}")

        enriched_df = enricher.enrich_data(df)

        if len(enriched_df) > 0:
            output_file = enricher.save_enriched_data(enriched_df)
            print(f"\nEnrichment complete! {len(enriched_df)} records → {output_file}")

            has_mailing = (enriched_df['mailing_address'].notna() & (enriched_df['mailing_address'] != '')).sum()
            has_owner = (enriched_df['owner_first_name'].notna() | enriched_df['owner_last_name'].notna()).sum()
            has_zillow = enriched_df['zillow_estimate'].notna().sum()

            print(f"\nEnrichment Summary:")
            print(f"  Owner names:       {has_owner}/{len(enriched_df)}")
            print(f"  Mailing addresses: {has_mailing}/{len(enriched_df)}")
            print(f"  Zillow estimates:  {has_zillow}/{len(enriched_df)}")

            if len(enriched_df) > 0:
                print(f"\nSample enriched record:")
                sample = enriched_df.iloc[0]
                for col in ['property_address', 'owner_first_name', 'owner_last_name', 'mailing_address', 'zillow_estimate']:
                    print(f"  {col}: {sample.get(col, 'N/A')}")
        else:
            print("No records were successfully enriched")

    except Exception as e:
        print(f"Enrichment failed: {e}")
        logger.error(f"Main error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
