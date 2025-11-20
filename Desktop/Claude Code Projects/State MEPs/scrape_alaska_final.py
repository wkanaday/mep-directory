import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://www.alaska-mep.org/about"

print(f"Fetching Alaska MEP about page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

# Find the "OUR TEAM" section
staff_data = []

# Look for the section with team info
team_section = soup.find('h3', string=re.compile(r'OUR TEAM', re.I))

if team_section:
    # Get the parent div that contains all the staff info
    parent = team_section.find_parent('div', class_='sqs-html-content')

    if parent:
        # Get all paragraphs
        paragraphs = parent.find_all('p')

        for p in paragraphs:
            # Find all strong tags (names) in this paragraph
            strongs = p.find_all('strong')

            for strong_tag in strongs:
                name = strong_tag.get_text().strip()

                # Clean up name (remove extra spaces, PhD, etc)
                name = re.sub(r',?\s*(Ph\.?D\.?|PhD)\s*$', '', name).strip()

                if not name:
                    continue

                # Find the next <em> tag after this <strong> for the title
                title = ""
                next_em = strong_tag.find_next('em')
                if next_em and next_em.parent == p:  # Make sure it's in the same paragraph
                    title = next_em.get_text().strip()

                # Get text after the strong tag to find email
                # Get all text content from the strong tag onwards
                remaining_text = ""
                for sibling in strong_tag.next_siblings:
                    if isinstance(sibling, str):
                        remaining_text += sibling
                    elif sibling.name == 'br':
                        remaining_text += '\n'
                    elif sibling.name == 'em':
                        remaining_text += sibling.get_text()
                    elif sibling.name == 'strong':
                        break  # Stop at next staff member

                # Find email - look for pattern starting after whitespace or newline
                email_match = re.search(r'[\s\n]([a-zA-Z0-9._%+-]+@alaska\.edu)', remaining_text)
                email = email_match.group(1).strip() if email_match else ""

                # Find phone if exists
                phone_match = re.search(r'(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})', remaining_text)
                phone = phone_match.group(1) if phone_match else ""

                if name and email:
                    staff_data.append({
                        'Name': name,
                        'Title': title,
                        'Phone': phone,
                        'Mobile': '',
                        'Email': email,
                        'Bio': ''
                    })

                    print(f"Found: {name}")
                    print(f"  Title: {title}")
                    print(f"  Email: {email}")
                    print()

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

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
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
