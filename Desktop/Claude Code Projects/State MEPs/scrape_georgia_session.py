import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import time
import re

# Create a session to maintain cookies
session = requests.Session()

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

print("Step 1: Visiting main site to establish session...")
try:
    main_response = session.get('https://gamep.org/', headers=headers, timeout=30)
    print(f"Main site status: {main_response.status_code}")
    time.sleep(3)
except Exception as e:
    print(f"Error visiting main site: {e}")

print("\nStep 2: Navigating to team page...")
try:
    team_url = "https://gamep.org/meet-the-gamep-team/"
    team_response = session.get(team_url, headers=headers, timeout=30)
    print(f"Team page status: {team_response.status_code}")

    if team_response.status_code == 200:
        # Save HTML
        with open('georgia_session.html', 'w', encoding='utf-8') as f:
            f.write(team_response.text)
        print(f"Saved HTML ({len(team_response.text)} chars)")

        soup = BeautifulSoup(team_response.content, 'html.parser')

        staff_data = []

        # Try to find staff information
        # Look for common patterns
        containers = soup.find_all('div', class_=lambda x: x and any(keyword in str(x).lower() for keyword in ['team', 'staff', 'member', 'person', 'employee']))

        print(f"\nFound {len(containers)} potential containers")

        # If no containers found, try other methods
        if not containers:
            print("Trying alternative search methods...")
            # Look for any divs with email links
            email_links = soup.find_all('a', href=re.compile(r'mailto:'))
            print(f"Found {len(email_links)} email links")

            # Or look for headings
            headings = soup.find_all(['h2', 'h3', 'h4'])
            print(f"Found {len(headings)} headings")

        print("\nPage title:", soup.find('title').get_text() if soup.find('title') else "No title")

    elif team_response.status_code == 403:
        print("Still getting 403 Forbidden - site has strong bot protection")
        print("May need to scrape manually or use different approach")
    else:
        print(f"Unexpected status code: {team_response.status_code}")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
