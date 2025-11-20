import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://www.alaska-mep.org/team"

print(f"Fetching Alaska MEP team page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

# Save for analysis
with open('alaska_page.html', 'w', encoding='utf-8') as f:
    f.write(response.text)

staff_data = []

# Find all email links with @alaska.edu
email_links = soup.find_all('a', href=re.compile(r'mailto:.*@alaska\.edu'))

print(f"Found {len(email_links)} staff email links\n")

for link in email_links:
    email = link.get('href', '').replace('mailto:', '').replace('?', '').strip()

    # Find parent container to get name and title
    # The structure is image link -> parent divs -> name/title in nearby elements
    parent = link.find_parent('div', class_='sqs-block')

    if parent:
        # Look for text blocks nearby that might contain name and title
        text_blocks = parent.find_next_siblings('div', class_='sqs-block')

        name = ""
        title = ""
        bio = ""
        phone = ""

        for block in text_blocks[:5]:  # Check next few blocks
            # Get all text from the block
            text = block.get_text(strip=True)

            if not name and text and len(text) < 100 and text not in ['MEET THE TEAM', 'PARTNERSHIPS']:
                # First short text is likely the name
                name = text
            elif name and not title and text and len(text) < 100:
                # Second short text is likely the title
                title = text
            elif name and title and not bio and text and len(text) > 100:
                # Longer text is the bio
                bio = text
                break

        # Try to find phone if exists
        if parent:
            phone_link = None
            for block in text_blocks[:10]:
                phone_link = block.find('a', href=re.compile(r'tel:'))
                if phone_link:
                    phone = phone_link.get('href', '').replace('tel:', '').strip()
                    break

        if name:
            staff_data.append({
                'Name': name,
                'Title': title,
                'Phone': phone,
                'Mobile': '',
                'Email': email,
                'Bio': bio
            })
            print(f"Found: {name}")
            print(f"  Title: {title}")
            print(f"  Email: {email}")
            print(f"  Phone: {phone}")
            print()

# If the above method didn't work well, try a more manual approach
# Look for patterns in the HTML structure
if len(staff_data) < 3:
    print("Primary method found few results, trying alternative parsing...")

    # Find all image blocks that link to emails
    staff_data = []

    # Get all sections
    sections = soup.find_all('div', class_='row')

    for section in sections:
        # Find email link
        email_link = section.find('a', href=re.compile(r'mailto:.*@alaska\.edu'))
        if not email_link:
            continue

        email = email_link.get('href', '').replace('mailto:', '').replace('?', '').strip()

        # Get all text blocks in this section
        text_blocks = section.find_all('div', class_='sqs-block-content')

        name = ""
        title = ""
        bio = ""

        for block in text_blocks:
            text = block.get_text(strip=True)
            if not text or text in ['MEET THE TEAM', 'PARTNERSHIPS']:
                continue

            if not name and len(text) < 100:
                name = text
            elif name and not title and len(text) < 100:
                title = text
            elif name and title and len(text) > 100:
                bio = text
                break

        if name:
            staff_data.append({
                'Name': name,
                'Title': title,
                'Phone': '',
                'Mobile': '',
                'Email': email,
                'Bio': bio
            })
            print(f"Found (alt): {name} - {email}")

print(f"\n\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('ak_staff_temp.csv', index=False)
    print("Saved to ak_staff_temp.csv")

    # Update Excel
    print("\nUpdating AK tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        ak_sheet = wb['AK']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            ak_sheet[f'A{current_row}'] = staff['Name']
            ak_sheet[f'B{current_row}'] = staff['Title']
            ak_sheet[f'C{current_row}'] = staff['Phone']
            ak_sheet[f'D{current_row}'] = staff['Mobile']
            ak_sheet[f'E{current_row}'] = staff['Email']
            ak_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated AK tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and run update separately.")
else:
    print("\nNo staff data extracted. Manual review needed.")
