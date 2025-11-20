import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import re

def search_for_mep_website(mep_name):
    """Search for the MEP organization's main website"""
    search_query = f"{mep_name} manufacturing extension partnership"
    search_url = f"https://www.google.com/search?q={requests.utils.quote(search_query)}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for first organic search result
        for link in soup.find_all('a'):
            href = link.get('href', '')
            if '/url?q=' in href:
                url = href.split('/url?q=')[1].split('&')[0]
                if url.startswith('http') and 'google.com' not in url:
                    return url
    except:
        pass

    return None

def find_staff_page(base_url):
    """Given a base URL, try to find the staff/team page"""
    if not base_url:
        return None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Common staff page patterns
    staff_patterns = [
        '/team', '/our-team', '/staff', '/our-staff', '/about/team',
        '/about/staff', '/people', '/about/people', '/leadership',
        '/about-us/team', '/about-us/staff', '/meet-the-team'
    ]

    # First, try direct patterns
    for pattern in staff_patterns:
        try:
            test_url = urljoin(base_url, pattern)
            response = requests.get(test_url, headers=headers, timeout=5)
            if response.status_code == 200:
                # Check if page actually contains staff content
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text().lower()
                if any(keyword in text for keyword in ['staff', 'team', 'people', 'director', 'manager']):
                    return test_url
        except:
            continue
        time.sleep(0.5)

    # If direct patterns don't work, scrape the homepage for links
    try:
        response = requests.get(base_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        for link in soup.find_all('a', href=True):
            text = link.get_text().lower()
            href = link['href']

            # Look for links with staff/team related text
            if any(keyword in text for keyword in ['team', 'staff', 'our team', 'our staff', 'people', 'meet the team']):
                full_url = urljoin(base_url, href)
                # Verify it's a valid page
                try:
                    test_response = requests.get(full_url, headers=headers, timeout=5)
                    if test_response.status_code == 200:
                        return full_url
                except:
                    continue

            time.sleep(0.3)
    except:
        pass

    return None

def process_mep_centers(input_csv, output_csv):
    """Process all MEP centers and find their staff pages"""
    results = []

    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for i, row in enumerate(rows):
        state = row['State']
        mep_name = row['Program Name (MEP Center)']
        existing_url = row.get('Staff Page', '').strip()

        print(f"\nProcessing {i+1}/{len(rows)}: {state} - {mep_name}")

        if existing_url:
            print(f"  Already has URL: {existing_url}")
            row['Staff Page'] = existing_url
            results.append(row)
            continue

        # Search for main website
        print(f"  Searching for website...")
        base_url = search_for_mep_website(mep_name)

        if base_url:
            print(f"  Found website: {base_url}")
            print(f"  Looking for staff page...")
            staff_url = find_staff_page(base_url)

            if staff_url:
                print(f"  [OK] Found staff page: {staff_url}")
                row['Staff Page'] = staff_url
            else:
                print(f"  [X] No staff page found, using main site")
                row['Staff Page'] = base_url
        else:
            print(f"  [X] Could not find website")
            row['Staff Page'] = ''

        results.append(row)

        # Be polite with delays
        time.sleep(2)

    # Write results
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['State', 'Program Name (MEP Center)', 'Host Organization', 'Staff Page']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\n[COMPLETE] Results saved to {output_csv}")

if __name__ == "__main__":
    input_file = "state meps.csv"
    output_file = "state meps_updated.csv"

    print("Starting MEP staff page search...")
    print("This will take several minutes due to rate limiting...")

    process_mep_centers(input_file, output_file)
