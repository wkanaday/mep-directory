import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://www.floridamakes.com/about-us/our-team/staff"

print(f"Fetching Florida MEP staff page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

staff_data = []

# Find the main content area
main_content = soup.find('div', id='MainCopy_ContentWrapper')

if main_content:
    # Find all h3 tags (names) and get their following h5 (title)
    h3_tags = main_content.find_all('h3')

    print(f"\nFound {len(h3_tags)} staff members\n")

    for h3 in h3_tags:
        name = h3.get_text(strip=True)

        # Get the next h5 sibling for title
        title = ""
        h5 = h3.find_next('h5')
        if h5:
            title = h5.get_text(strip=True)

        # Get the next p tag after h5 - contains phone, linkedin, email
        phone = ""
        email = ""
        linkedin = ""

        if h5:
            p_tag = h5.find_next('p')
            if p_tag:
                # Find phone link (Tel:)
                phone_link = p_tag.find('a', href=re.compile(r'Tel:', re.I))
                if phone_link:
                    phone_href = phone_link.get('href', '')
                    # Extract number from Tel:xxx-xxx-xxxx
                    phone = phone_href.replace('Tel:', '').replace('tel:', '').strip()

                # Find email link
                email_link = p_tag.find('a', href=re.compile(r'mailto:'))
                if email_link:
                    email = email_link.get('href', '').replace('mailto:', '').strip()

                # Find LinkedIn link
                linkedin_link = p_tag.find('a', href=re.compile(r'linkedin\.com'))
                if linkedin_link:
                    linkedin = linkedin_link.get('href', '').strip()

        # Put LinkedIn in bio field
        bio = f"LinkedIn: {linkedin}" if linkedin else ""

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
        print(f"  Email: {email if email else '(none found)'}")
        print(f"  Phone: {phone if phone else '(none found)'}")
        print(f"  LinkedIn: {linkedin if linkedin else '(none found)'}")
        print()

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('fl_staff_temp.csv', index=False)
    print("Saved to fl_staff_temp.csv")

    # Update Excel
    print("\nUpdating FL tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        fl_sheet = wb['FL']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            fl_sheet[f'A{current_row}'] = staff['Name']
            fl_sheet[f'B{current_row}'] = staff['Title']
            fl_sheet[f'C{current_row}'] = staff['Phone']
            fl_sheet[f'D{current_row}'] = staff['Mobile']
            fl_sheet[f'E{current_row}'] = staff['Email']
            fl_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated FL tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
