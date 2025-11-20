import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

url = "https://www.atn.org/about-atn/team-members/"

print(f"Fetching Alabama staff page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

# Step 1: Get detailed info from tab-panes (these have full contact info and bios)
tab_panes = soup.find_all('div', class_='tab-pane')
detailed_staff = {}

print(f"Found {len(tab_panes)} staff with detailed profiles\n")

for pane in tab_panes:
    h2 = pane.find('h2')
    if h2:
        h2_text = h2.get_text()
        small = h2.find('small')

        if small:
            name = h2_text.replace(small.get_text(), '').strip()
            title = small.get_text().strip().replace('|', '').strip()
        else:
            name = h2_text.strip()
            title = ""

        contact_p = h2.find_next('p')
        email = ""
        phone = ""

        if contact_p:
            email_link = contact_p.find('a', href=re.compile(r'mailto:'))
            if email_link:
                email = email_link.get_text(strip=True)

            phone_link = contact_p.find('a', href=re.compile(r'tel:'))
            if phone_link:
                phone = phone_link.get_text(strip=True)

        bio_parts = []
        for p in pane.find_all('p')[1:]:
            text = p.get_text(strip=True)
            if text:
                bio_parts.append(text)
        bio = ' '.join(bio_parts)

        if name:
            detailed_staff[name] = {
                'Name': name,
                'Title': title,
                'Phone': phone,
                'Mobile': '',
                'Email': email,
                'Bio': bio
            }

# Step 2: Add all detailed staff first (they're not in the diamond cards)
all_staff = list(detailed_staff.values())
for staff in all_staff:
    print(f"[DETAILED] {staff['Name']} - {staff['Title']}")

# Step 3: Get all staff from the diamond cards (name and title only)
items = soup.find_all('div', class_='item')

print(f"\nFound {len(items)} staff in diamond cards\n")

for item in items:
    p_tag = item.find('p', class_='diamond__title')
    if p_tag:
        text = p_tag.get_text(strip=True)
        small_tag = p_tag.find('small')

        if small_tag:
            name = text.replace(small_tag.get_text(strip=True), '').strip()
            title = small_tag.get_text(strip=True).replace('<br>', ' ').strip()
        else:
            parts = text.split('\n')
            if len(parts) >= 2:
                name = parts[0].strip()
                title = ' '.join(parts[1:]).strip()
            else:
                name = text
                title = ""

        if name:
            all_staff.append({
                'Name': name,
                'Title': title,
                'Phone': '',
                'Mobile': '',
                'Email': '',
                'Bio': ''
            })
            print(f"[BASIC] {name} - {title}")

print(f"\n\nSuccessfully extracted {len(all_staff)} staff members")
print(f"  - {len(detailed_staff)} with full contact info and bios")
print(f"  - {len(all_staff) - len(detailed_staff)} with name and title only")

# Save to CSV
df = pd.DataFrame(all_staff)
df.to_csv('al_staff_temp.csv', index=False)
print("\nSaved to al_staff_temp.csv")

# Update Excel
print("\nUpdating AL tab in Excel...")
wb = load_workbook('state_meps.xlsx')
al_sheet = wb['AL']

start_row = 4

for idx, staff in enumerate(all_staff):
    current_row = start_row + idx
    al_sheet[f'A{current_row}'] = staff['Name']
    al_sheet[f'B{current_row}'] = staff['Title']
    al_sheet[f'C{current_row}'] = staff['Phone']
    al_sheet[f'D{current_row}'] = staff['Mobile']
    al_sheet[f'E{current_row}'] = staff['Email']
    al_sheet[f'F{current_row}'] = staff['Bio']

wb.save('state_meps.xlsx')
print(f"Successfully updated AL tab in state_meps.xlsx!")
