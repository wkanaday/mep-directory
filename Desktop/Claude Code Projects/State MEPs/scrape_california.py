import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://www.cmtc.com/cmtc-leadership-team"

print(f"Fetching California MEP leadership page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

staff_data = []

# Find all team-member divs
team_members = soup.find_all('div', class_='team-member')

print(f"\nFound {len(team_members)} team members\n")

for member in team_members:
    # Get name
    name_elem = member.find('h3', class_='team-member-name')
    name = name_elem.get_text(strip=True) if name_elem else ""

    # Get title
    title_elem = member.find('p', class_='team-member-title')
    title = title_elem.get_text(strip=True) if title_elem else ""

    # Get bio
    bio_elem = member.find('div', class_='team-member-bio')
    bio = ""
    if bio_elem:
        # Get all paragraph text
        paragraphs = bio_elem.find_all('p')
        bio_parts = [p.get_text(strip=True) for p in paragraphs]
        bio = ' '.join(bio_parts)

    # Look for email and phone in the bio or elsewhere
    email = ""
    phone = ""
    mobile = ""

    # Search for email in the entire member section
    email_links = member.find_all('a', href=lambda x: x and 'mailto:' in x)
    if email_links:
        email = email_links[0].get('href', '').replace('mailto:', '').strip()

    # Search for phone numbers in text
    member_text = member.get_text()
    phone_matches = re.findall(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', member_text)

    if phone_matches:
        for phone_match in phone_matches:
            # Check context to determine if mobile or regular phone
            # For now, treat first as phone, second as mobile if exists
            if not phone:
                phone = phone_match
            elif not mobile:
                mobile = phone_match

    staff_data.append({
        'Name': name,
        'Title': title,
        'Phone': phone,
        'Mobile': mobile,
        'Email': email,
        'Bio': bio
    })

    print(f"Found: {name}")
    print(f"  Title: {title}")
    print(f"  Email: {email if email else '(none found)'}")
    print(f"  Phone: {phone if phone else '(none found)'}")
    print(f"  Mobile: {mobile if mobile else '(none found)'}")
    print(f"  Bio: {bio[:80]}..." if len(bio) > 80 else f"  Bio: {bio}")
    print()

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('ca_staff_temp.csv', index=False)
    print("Saved to ca_staff_temp.csv")

    # Update Excel
    print("\nUpdating CA tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        ca_sheet = wb['CA']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            ca_sheet[f'A{current_row}'] = staff['Name']
            ca_sheet[f'B{current_row}'] = staff['Title']
            ca_sheet[f'C{current_row}'] = staff['Phone']
            ca_sheet[f'D{current_row}'] = staff['Mobile']
            ca_sheet[f'E{current_row}'] = staff['Email']
            ca_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated CA tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
