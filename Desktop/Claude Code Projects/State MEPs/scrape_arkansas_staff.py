import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import time
import re

# Fetch the Arkansas staff page
url = "https://www.mfgsolutions.org/our-team/"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def extract_profile_details(profile_url):
    """Extract phone, mobile, email, and bio from individual profile page"""
    try:
        print(f"  Fetching profile: {profile_url}")
        response = requests.get(profile_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        phone = ""
        mobile = ""
        email = ""
        bio = ""

        # Look for contact information - try various patterns
        # Phone numbers are often in links with tel: or in text
        phone_links = soup.find_all('a', href=re.compile(r'tel:'))
        if phone_links:
            for link in phone_links:
                phone_text = link.get_text(strip=True)
                if 'mobile' in link.get('title', '').lower() or 'cell' in link.get('title', '').lower():
                    mobile = phone_text
                elif not phone:
                    phone = phone_text

        # Email - look for mailto links
        email_links = soup.find_all('a', href=re.compile(r'mailto:'))
        if email_links:
            email = email_links[0].get_text(strip=True)

        # Bio - look for content area, article body, or bio section
        bio_areas = soup.find_all(['div', 'article'], class_=lambda x: x and ('content' in x.lower() or 'bio' in x.lower() or 'description' in x.lower()))
        if bio_areas:
            for area in bio_areas:
                paragraphs = area.find_all('p')
                bio_text = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
                if bio_text and len(bio_text) > 50:  # Make sure it's substantial
                    bio = bio_text
                    break

        # If phone/mobile/email not found in links, try to extract from bio text
        if bio:
            # Extract phone numbers from bio text
            phone_pattern = r'Phone:\s*\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})'
            mobile_pattern = r'(?:Mobile|Cell):\s*\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})'
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

            phone_match = re.search(phone_pattern, bio)
            if phone_match and not phone:
                phone = f"({phone_match.group(1)}) {phone_match.group(2)}-{phone_match.group(3)}"

            mobile_match = re.search(mobile_pattern, bio)
            if mobile_match and not mobile:
                mobile = f"({mobile_match.group(1)}) {mobile_match.group(2)}-{mobile_match.group(3)}"

            email_match = re.search(email_pattern, bio)
            if email_match and not email:
                email = email_match.group(0)

        return phone, mobile, email, bio
    except Exception as e:
        print(f"  Error fetching profile: {e}")
        return "", "", "", ""

try:
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, 'html.parser')

    # Find staff members based on the actual HTML structure
    staff_data = []

    # Look for team containers with class "team-container"
    team_containers = soup.find_all('div', class_='team-container')

    print(f"Found {len(team_containers)} team containers\n")

    for idx, container in enumerate(team_containers, 1):
        # Find the name within team-author-name div
        name_div = container.find('div', class_='team-author-name')
        if name_div:
            name_link = name_div.find('a')
            name = name_link.get_text(strip=True) if name_link else ""
            profile_url = name_link.get('href') if name_link else ""

            # Find the title in the <p> tag that follows
            team_author = container.find('div', class_='team-author')
            if team_author:
                title_p = team_author.find('p')
                title = title_p.get_text(strip=True) if title_p else ""

                if name and profile_url:
                    print(f"[{idx}/{len(team_containers)}] Processing: {name}")

                    # Fetch detailed information from profile page
                    phone, mobile, email, bio = extract_profile_details(profile_url)

                    staff_data.append({
                        'Name': name,
                        'Title': title,
                        'Phone': phone,
                        'Mobile': mobile,
                        'Email': email,
                        'Bio': bio
                    })
                    print(f"  Complete\n")

                    # Be polite - don't hammer the server
                    time.sleep(1)

    if staff_data:
        print(f"\n\nSuccessfully extracted {len(staff_data)} staff members")

        # Save to a temporary CSV for inspection
        df = pd.DataFrame(staff_data)
        df.to_csv('arkansas_staff_temp.csv', index=False)
        print("Saved to arkansas_staff_temp.csv")
    else:
        print("\n\nNo staff data extracted. Manual inspection may be needed.")
        print("Saving HTML content for analysis...")
        with open('arkansas_page.html', 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        print("Saved page HTML to arkansas_page.html")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
