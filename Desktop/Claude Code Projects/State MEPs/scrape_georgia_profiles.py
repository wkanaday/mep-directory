import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import time
import re

# Profile URLs for all 25 staff members
profile_urls = [
    "https://gamep.org/meet-the-team/cassia-baker/",
    "https://gamep.org/meet-the-team/michael-barker-2/",
    "https://gamep.org/meet-the-team/jay-boudreaux/",
    "https://gamep.org/meet-the-team/anna-cali/",
    "https://gamep.org/meet-the-team/ben-cheeks/",
    "https://gamep.org/meet-the-team/jason-clarke/",
    "https://gamep.org/meet-the-team/sam-darwin/",
    "https://gamep.org/meet-the-team/sandra-enciso/",
    "https://gamep.org/meet-the-team/alfred-gardner/",
    "https://gamep.org/meet-the-team/bogna-grabicka/",
    "https://gamep.org/meet-the-team/jasmyn-green/",
    "https://gamep.org/meet-the-team/kelly-grissom/",
    "https://gamep.org/meet-the-team/andy-helm/",
    "https://gamep.org/meet-the-team/dean-hettenbach/",
    "https://gamep.org/meet-the-team/katie-hines/",
    "https://gamep.org/meet-the-team/andrea-hines/",
    "https://gamep.org/meet-the-team/hank-hobbs/",
    "https://gamep.org/meet-the-team/raine-hyde/",
    "https://gamep.org/meet-the-team/tim-israel/",
    "https://gamep.org/meet-the-team/megan-johnson/",
    "https://gamep.org/meet-the-team/ieasha-jones/",
    "https://gamep.org/meet-the-team/amber-kasselman/",
    "https://gamep.org/meet-the-team/andrew-krejci/",
    "https://gamep.org/meet-the-team/caley-landau/",
    "https://gamep.org/meet-the-team/paul-lavigna/",
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

staff_data = []

print(f"Scraping {len(profile_urls)} Georgia MEP staff profiles...")
print(f"{'='*60}\n")

for idx, url in enumerate(profile_urls, 1):
    try:
        print(f"[{idx}/{len(profile_urls)}] Fetching: {url}")
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract name from page title or h1
            name = ""
            title_tag = soup.find('title')
            if title_tag:
                # Title format is usually "Name - GaMEP"
                name = title_tag.get_text().replace(' - GaMEP', '').strip()

            # Extract title/position
            title = ""
            # Look for title in various locations
            title_elem = soup.find(['h2', 'h3', 'p'], class_=lambda x: x and 'title' in str(x).lower())
            if title_elem:
                title = title_elem.get_text(strip=True)

            # Extract phone
            phone = ""
            phone_link = soup.find('a', href=re.compile(r'tel:'))
            if phone_link:
                phone = phone_link.get_text(strip=True)

            # Extract email
            email = ""
            email_link = soup.find('a', href=re.compile(r'mailto:'))
            if email_link:
                email = email_link.get('href', '').replace('mailto:', '').strip()

            # Extract bio
            bio = ""
            bio_sections = soup.find_all(['p', 'div'], class_=lambda x: x and ('bio' in str(x).lower() or 'content' in str(x).lower()))
            if bio_sections:
                bio_parts = []
                for section in bio_sections:
                    paragraphs = section.find_all('p')
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 50 and '@' not in text:  # Skip short paragraphs and contact info
                            bio_parts.append(text)
                bio = ' '.join(bio_parts)

            staff_data.append({
                'Name': name,
                'Title': title,
                'Phone': phone,
                'Mobile': '',
                'Email': email,
                'Bio': bio
            })

            print(f"  Name: {name}")
            print(f"  Title: {title}")
            print(f"  Phone: {phone if phone else '(none)'}")
            print(f"  Email: {email if email else '(none)'}")
            print(f"  Bio: {len(bio)} chars")
            print()

            time.sleep(1)  # Be polite

        else:
            print(f"  Error: Status {response.status_code}")
            print()

    except Exception as e:
        print(f"  Error: {e}")
        print()
        continue

print(f"\n{'='*60}")
print(f"Successfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('ga_staff_temp.csv', index=False)
    print("Saved to ga_staff_temp.csv")

    # Update Excel
    print("\nUpdating GA tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        ga_sheet = wb['GA']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            ga_sheet[f'A{current_row}'] = staff['Name']
            ga_sheet[f'B{current_row}'] = staff['Title']
            ga_sheet[f'C{current_row}'] = staff['Phone']
            ga_sheet[f'D{current_row}'] = staff['Mobile']
            ga_sheet[f'E{current_row}'] = staff['Email']
            ga_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated GA tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
