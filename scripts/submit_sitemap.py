#!/usr/bin/env python3
"""
Submit sitemap to search engines for indexing.
This script submits the generated sitemap to Google and Bing for faster indexing.
"""

import os
import requests
import urllib.parse
from pathlib import Path

def submit_to_google(sitemap_url):
    """Submit sitemap to Google Search Console."""
    try:
        google_url = f"https://www.google.com/ping?sitemap={urllib.parse.quote(sitemap_url)}"
        response = requests.get(google_url, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Successfully submitted sitemap to Google: {sitemap_url}")
            return True
        else:
            print(f"⚠️ Google submission failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error submitting to Google: {e}")
        return False

def submit_to_bing(sitemap_url):
    """Submit sitemap to Bing Webmaster Tools."""
    try:
        bing_url = f"https://www.bing.com/ping?sitemap={urllib.parse.quote(sitemap_url)}"
        response = requests.get(bing_url, timeout=10)
        
        if response.status_code == 200:
            print(f"✅ Successfully submitted sitemap to Bing: {sitemap_url}")
            return True
        else:
            print(f"⚠️ Bing submission failed with status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error submitting to Bing: {e}")
        return False

def submit_sitemap():
    """Submit sitemap to major search engines."""
    # Get the repository info from environment
    repo_name = os.getenv('GITHUB_REPOSITORY', 'username/gguf-models').split('/')[-1]
    repo_owner = os.getenv('GITHUB_REPOSITORY_OWNER', 'username')
    base_url = f"https://{repo_owner}.github.io/{repo_name}"
    sitemap_url = f"{base_url}/sitemap.xml"
    
    print(f"🚀 Submitting sitemap: {sitemap_url}")
    
    # Check if sitemap exists locally
    if not Path('sitemap.xml').exists():
        print("❌ sitemap.xml not found. Please generate it first.")
        return False
    
    success_count = 0
    
    # Submit to Google
    if submit_to_google(sitemap_url):
        success_count += 1
    
    # Submit to Bing
    if submit_to_bing(sitemap_url):
        success_count += 1
    
    if success_count > 0:
        print(f"🎉 Sitemap submitted to {success_count} search engines successfully!")
        return True
    else:
        print("⚠️ Failed to submit sitemap to any search engines")
        return False

def main():
    """Main function."""
    print("Starting sitemap submission...")
    submit_sitemap()

if __name__ == "__main__":
    main()