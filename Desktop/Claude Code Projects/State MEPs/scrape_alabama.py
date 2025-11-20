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

# Find all tab-pane divs that contain the full staff details
tab_panes = soup.find_all('div', class_='tab-pane')

print(f"Found {len(tab_panes)} staff detail tabs\n")

staff_data = []

for pane in tab_panes:
    # Find the h2 with name and title
    h2 = pane.find('h2')
    if h2:
        # Name is in the h2, title is in the small tag
        h2_text = h2.get_text()
        small = h2.find('small')

        if small:
            name = h2_text.replace(small.get_text(), '').strip()
            title = small.get_text().strip().replace('|', '').strip()
        else:
            name = h2_text.strip()
            title = ""

        # Extract email and phone from the paragraph right after h2
        contact_p = h2.find_next('p')
        email = ""
        phone = ""

        if contact_p:
            # Find email link
            email_link = contact_p.find('a', href=re.compile(r'mailto:'))
            if email_link:
                email = email_link.get_text(strip=True)

            # Find phone link
            phone_link = contact_p.find('a', href=re.compile(r'tel:'))
            if phone_link:
                phone = phone_link.get_text(strip=True)

        # Extract bio - all paragraphs after the contact info
        bio_parts = []
        for p in pane.find_all('p')[1:]:  # Skip first p (contact info)
            text = p.get_text(strip=True)
            if text:
                bio_parts.append(text)
        bio = ' '.join(bio_parts)

        if name:
            staff_data.append({
                'Name': name,
                'Title': title,
                'Phone': phone,
                'Mobile': '',  # Mobile not separately listed
                'Email': email,
                'Bio': bio
            })
            print(f"Found: {name}")
            print(f"  Title: {title}")
            print(f"  Email: {email}")
            print(f"  Phone: {phone}")
            print(f"  Bio: {bio[:100]}..." if len(bio) > 100 else f"  Bio: {bio}")
            print()

print(f"\n\nSuccessfully extracted {len(staff_data)} staff members")

# Save to CSV
df = pd.DataFrame(staff_data)
df.to_csv('al_staff_temp.csv', index=False)
print("Saved to al_staff_temp.csv")

# Update Excel
print("\nUpdating AL tab in Excel...")
wb = load_workbook('state_meps.xlsx')
al_sheet = wb['AL']

start_row = 4

for idx, staff in enumerate(staff_data):
    current_row = start_row + idx
    al_sheet[f'A{current_row}'] = staff['Name']
    al_sheet[f'B{current_row}'] = staff['Title']
    al_sheet[f'C{current_row}'] = staff['Phone']
    al_sheet[f'D{current_row}'] = staff['Mobile']
    al_sheet[f'E{current_row}'] = staff['Email']
    al_sheet[f'F{current_row}'] = staff['Bio']

wb.save('state_meps.xlsx')
print(f"Successfully updated AL tab in state_meps.xlsx!")
print(f"\nNote: Phone, Mobile, Email, and Bio are not available on this page.")
print("The Alabama site uses JavaScript to load detailed profiles dynamically.")
