import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://www.demep.org/contact-us/"

print(f"Fetching Delaware MEP contact page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

# Get the main content
content = soup.find('div', class_='entry-content')

staff_data = []

# Find all paragraphs that contain staff information
paragraphs = content.find_all('p')

print(f"\nParsing {len(paragraphs)} paragraphs for staff information...\n")

for p in paragraphs:
    # Each staff member has: <strong>Name</strong> <br/> Title <br/> Email <br/> Phone
    strong = p.find('strong')
    email_link = p.find('a', href=re.compile(r'mailto:'))

    # Skip if no name or email (like the billing notice)
    if not strong or not email_link:
        continue

    # Get name
    name = strong.get_text(strip=True)

    # Get email
    email = email_link.get('href', '').replace('mailto:', '').strip()

    # Get all text content and split by <br/>
    # We need to parse the text between elements
    text_parts = []
    for child in p.children:
        if child.name == 'br':
            text_parts.append('|BR|')
        elif hasattr(child, 'get_text'):
            text_parts.append(child.get_text(strip=True))
        elif isinstance(child, str):
            text_parts.append(child.strip())

    # Join and split by our BR marker
    full_text = ''.join(text_parts)
    lines = [line.strip() for line in full_text.split('|BR|') if line.strip()]

    # lines[0] should be name, lines[1] should be title, lines[2] email, lines[3] phone
    title = ""
    phone = ""

    for line in lines:
        # Skip the name line and email line
        if line == name or email in line:
            continue

        # Check if it's a phone line
        if 'Phone:' in line:
            phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', line)
            if phone_match:
                phone = phone_match.group()
        # Otherwise it's likely the title
        elif not title and len(line) < 100 and len(line) > 3:
            title = line

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
    print(f"  Phone: {phone}")
    print()

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('de_staff_temp.csv', index=False)
    print("Saved to de_staff_temp.csv")

    # Update Excel
    print("\nUpdating DE tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        de_sheet = wb['DE']

        # Clear existing data first
        for row_num in range(4, 20):
            for col in ['A', 'B', 'C', 'D', 'E', 'F']:
                de_sheet[f'{col}{row_num}'] = None

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            de_sheet[f'A{current_row}'] = staff['Name']
            de_sheet[f'B{current_row}'] = staff['Title']
            de_sheet[f'C{current_row}'] = staff['Phone']
            de_sheet[f'D{current_row}'] = staff['Mobile']
            de_sheet[f'E{current_row}'] = staff['Email']
            de_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated DE tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
