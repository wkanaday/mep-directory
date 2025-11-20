import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://www.azcommerce.com/programs/arizona-mep/who-we-are/our-expert-staff/"

print(f"Fetching Arizona MEP staff page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

# For Arizona, we need to use Selenium because content loads via JavaScript
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')

print("Loading page with Selenium...")
driver = webdriver.Chrome(options=chrome_options)
driver.get(url)
time.sleep(5)

# Scroll to load all content
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

html = driver.page_source
driver.quit()

soup = BeautifulSoup(html, 'html.parser')

staff_data = []

# Find all bioBoard sections (these contain individual staff details)
bio_sections = soup.find_all('div', class_='bioBoard')

print(f"\nFound {len(bio_sections)} staff members\n")

for section in bio_sections:
    # Get name and title from h3
    h3 = section.find('div', class_='h3')

    if not h3:
        continue

    # Parse name and title from children (separated by <br/>)
    children = list(h3.children)
    name = ""
    title = ""

    for i, child in enumerate(children):
        if child.name == 'br':
            continue
        text = str(child).strip()
        if text and not name:
            name = text
        elif text and not title:
            title = text

    # Get all paragraphs
    paragraphs = section.find_all('p')

    # Extract email, phone, mobile, and bio
    email = ""
    phone = ""
    mobile = ""
    bio_parts = []

    for p in paragraphs:
        p_text = p.get_text(strip=True)

        # Check for email
        email_link = p.find('a', href=lambda x: x and 'mailto:' in x)
        if email_link:
            email = email_link.get('href', '').replace('mailto:', '').strip()
            continue

        # Check for phone numbers
        if re.search(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', p_text):
            # Check if it's mobile or regular phone
            if 'mobile' in p_text.lower() or 'cell' in p_text.lower():
                mobile = re.search(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', p_text).group()
            else:
                phone_num = re.search(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}', p_text).group()
                # If we already have mobile, this is regular phone
                if mobile:
                    phone = phone_num
                else:
                    # Check if text indicates it's mobile
                    mobile = phone_num
            continue

        # If it's a substantial paragraph (bio content), add to bio
        if len(p_text) > 50:
            bio_parts.append(p_text)

    bio = ' '.join(bio_parts)

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
    print(f"  Email: {email}")
    print(f"  Mobile: {mobile}")
    print(f"  Phone: {phone}")
    print(f"  Bio: {bio[:80]}..." if len(bio) > 80 else f"  Bio: {bio}")
    print()

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('az_staff_temp.csv', index=False)
    print("Saved to az_staff_temp.csv")

    # Update Excel
    print("\nUpdating AZ tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        az_sheet = wb['AZ']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            az_sheet[f'A{current_row}'] = staff['Name']
            az_sheet[f'B{current_row}'] = staff['Title']
            az_sheet[f'C{current_row}'] = staff['Phone']
            az_sheet[f'D{current_row}'] = staff['Mobile']
            az_sheet[f'E{current_row}'] = staff['Email']
            az_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated AZ tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
