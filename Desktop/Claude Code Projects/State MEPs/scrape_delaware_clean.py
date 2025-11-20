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
text = content.get_text() if content else soup.get_text()

print(f"\nParsing staff information...")

staff_data = []

# The pattern is: Name + Title + Email + Phone
# Example: "Lilianne AngeliManufacturing Specialist IIlangeli@demep.orgPhone: (302) 283-3134"

# Split by "Phone:" to separate each staff member
sections = text.split('Phone:')

for section in sections:
    # Look for email in this section
    email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.(?:org|edu))', section)

    if email_match:
        email = email_match.group(1)

        # Get text before the email
        before_email = section[:email_match.start()]

        # Clean up the text
        before_email = before_email.strip()

        # Remove common prefixes
        before_email = before_email.replace('Executive Director', '').replace('Deputy Director', '').replace('Field Staff', '').replace('Administrative Support Staff', '')
        before_email = before_email.strip()

        # Now we need to separate name from title
        # Title keywords to look for
        title_keywords = ['Director', 'Manager', 'Specialist', 'Coordinator', 'President', 'CEO', 'VP']

        name = ""
        title = ""

        # Find where the title starts
        for keyword in title_keywords:
            if keyword in before_email:
                # Find the position
                keyword_pos = before_email.find(keyword)

                # Everything before the title keyword is the name (possibly with Dr. prefix)
                potential_name = before_email[:keyword_pos].strip()

                # Clean up name
                potential_name = potential_name.replace('Dr.', 'Dr').strip()

                # Everything from the keyword onwards is the title
                potential_title = before_email[keyword_pos:].strip()

                # Only accept if we have a reasonable name (2-4 words, at least 5 chars)
                name_words = potential_name.split()
                if len(potential_name) >= 5 and len(name_words) >= 2 and len(name_words) <= 4:
                    name = potential_name
                    title = potential_title
                    break

        # Extract phone number
        phone = ""
        phone_match = re.search(r'\((\d{3})\)\s*(\d{3})-(\d{4})', section)
        if phone_match:
            phone = f"({phone_match.group(1)}) {phone_match.group(2)}-{phone_match.group(3)}"

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
