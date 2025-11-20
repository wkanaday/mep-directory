import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# First, get the team page to find all staff profile URLs
team_url = "https://www.connstep.org/our-team/"

print(f"Fetching Connecticut MEP team page...")
response = requests.get(team_url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

# Find all staff profile links
staff_links = soup.find_all('a', href=re.compile(r'/staff/'))

# Get unique URLs
staff_urls = list(set([link.get('href') for link in staff_links if link.get('href')]))

print(f"\nFound {len(staff_urls)} staff members")
print(f"\nVisiting each profile page to extract details...\n")

staff_data = []

for idx, profile_url in enumerate(staff_urls, 1):
    try:
        print(f"{idx}. Fetching: {profile_url}")

        # Fetch the profile page
        profile_response = requests.get(profile_url, headers=headers)
        profile_response.raise_for_status()

        profile_soup = BeautifulSoup(profile_response.content, 'html.parser')

        # Extract name from page title
        name = ""
        title_tag = profile_soup.find('title')
        if title_tag:
            title_text = title_tag.get_text(strip=True)
            # Remove " - CONNSTEP" from the end
            name = title_text.replace(' - CONNSTEP', '').strip()

        # Extract title from subtitle class
        title = ""
        subtitle_elem = profile_soup.find(class_='subtitle')
        if subtitle_elem:
            title = subtitle_elem.get_text(strip=True)

        # Extract email
        email = ""
        email_link = profile_soup.find('a', href=re.compile(r'mailto:'))
        if email_link:
            email = email_link.get('href', '').replace('mailto:', '').strip()

        # Extract phone
        phone = ""
        mobile = ""
        phone_link = profile_soup.find('a', href=re.compile(r'tel:'))
        if phone_link:
            phone = phone_link.get('href', '').replace('tel:', '').strip()

        # Extract bio
        bio = ""
        content_div = profile_soup.find('div', class_='entry-content')
        if content_div:
            # Get all paragraphs
            paragraphs = content_div.find_all('p')
            bio_parts = []

            for p in paragraphs:
                text = p.get_text(strip=True)
                # Skip very short paragraphs and those that look like title/contact info
                if len(text) > 50 and '@' not in text and 'tel:' not in str(p):
                    bio_parts.append(text)

            bio = ' '.join(bio_parts)

        staff_data.append({
            'Name': name,
            'Title': title,
            'Phone': phone,
            'Mobile': mobile,
            'Email': email,
            'Bio': bio
        })

        print(f"   Name: {name}")
        print(f"   Title: {title}")
        print(f"   Email: {email if email else '(none found)'}")
        print(f"   Phone: {phone if phone else '(none found)'}")
        print(f"   Bio: {len(bio)} characters")
        print()

        # Small delay to be respectful to the server
        time.sleep(0.5)

    except Exception as e:
        print(f"   Error processing {profile_url}: {e}")
        print()
        continue

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('ct_staff_temp.csv', index=False)
    print("Saved to ct_staff_temp.csv")

    # Update Excel
    print("\nUpdating CT tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        ct_sheet = wb['CT']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            ct_sheet[f'A{current_row}'] = staff['Name']
            ct_sheet[f'B{current_row}'] = staff['Title']
            ct_sheet[f'C{current_row}'] = staff['Phone']
            ct_sheet[f'D{current_row}'] = staff['Mobile']
            ct_sheet[f'E{current_row}'] = staff['Email']
            ct_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated CT tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
