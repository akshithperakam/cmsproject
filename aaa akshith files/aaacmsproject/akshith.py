"""
cms_clfs_fetch.py

Purpose:
    Step 1 of the pipeline (Phase 1 - Data Ingestion).
    Navigates the CMS CLFS Files page, finds the row for a target quarter
    (e.g. "26CLABQ3"), resolves the actual download link for that file,
    and downloads the zip to a local "downloads" folder.

Why Selenium + requests together:
    - Selenium is used only for the parts of the page that need a real
      browser (finding the correct link, since CMS's file list can be
      rendered/updated dynamically and the href isn't always obvious
      from a plain HTML fetch).
    - Once we have the *direct file URL*, we switch to `requests` to do
      the actual binary download. This is faster and more reliable than
      asking Selenium to manage file downloads (which requires fiddling
      with Chrome's download directory settings).

Usage:
    python cms_clfs_fetch.py --quarter 26CLABQ3
"""

import argparse
import os
import sys
import time
from urllib.parse import urljoin

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

CLFS_FILES_URL = (
    "https://www.cms.gov/medicare/payment/fee-schedules/"
    "clinical-laboratory-fee-schedule-clfs/files"
)
DOWNLOAD_DIR = "downloads"


def build_driver(headless: bool = True) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    return webdriver.Chrome(options=options)


def find_quarter_link(driver: webdriver.Chrome, quarter_code: str) -> str:
    """
    quarter_code example: '26CLABQ3'
    Returns the resolved absolute URL to the file's landing/download page.
    """
    driver.get(CLFS_FILES_URL)

    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))

    # Find the link whose visible text matches the quarter code exactly.
    links = driver.find_elements(By.TAG_NAME, "a")
    for link in links:
        text = link.text.strip()
        if text == quarter_code:
            href = link.get_attribute("href")
            if href:
                return urljoin(driver.current_url, href)

    raise ValueError(f"Could not find a link for quarter code '{quarter_code}'")


def resolve_zip_url(driver: webdriver.Chrome, landing_url: str) -> str:
    """
    CMS file links often go to an intermediate landing page rather than
    the raw .zip directly. This opens that page and looks for the actual
    .zip (or .csv) download link.
    """
    driver.get(landing_url)
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    links = driver.find_elements(By.TAG_NAME, "a")
    for link in links:
        href = link.get_attribute("href") or ""
        if href.lower().endswith((".zip", ".csv")):
            return urljoin(driver.current_url, href)

    # If no direct file link found, assume the landing_url itself is the file
    # (some CMS links point straight to the binary).
    return landing_url


def download_file(url: str, dest_folder: str = DOWNLOAD_DIR) -> str:
    os.makedirs(dest_folder, exist_ok=True)
    local_filename = os.path.join(dest_folder, url.split("/")[-1].split("?")[0])

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(local_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    return local_filename


def main():
    parser = argparse.ArgumentParser(description="Fetch a CMS CLFS quarterly file.")
    parser.add_argument(
        "--quarter",
        required=True,
        help="Quarter code as shown on the CMS site, e.g. 26CLABQ3",
    )
    parser.add_argument(
        "--show-browser",
        action="store_true",
        help="Run Chrome with a visible window (for debugging).",
    )
    args = parser.parse_args()

    driver = build_driver(headless=not args.show_browser)

    try:
        print(f"[1/3] Locating link for {args.quarter} on CLFS Files page...")
        landing_url = find_quarter_link(driver, args.quarter)
        print(f"      Found landing URL: {landing_url}")

        print("[2/3] Resolving actual file download URL...")
        zip_url = resolve_zip_url(driver, landing_url)
        print(f"      Resolved file URL: {zip_url}")

        print("[3/3] Downloading file...")
        local_path = download_file(zip_url)
        print(f"      Saved to: {local_path}")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()