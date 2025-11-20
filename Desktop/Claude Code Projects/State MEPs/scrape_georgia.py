from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook
import time
import re

# Setup headless Chrome
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')

url = "https://gamep.org/meet-the-gamep-team/"

print(f"Fetching Georgia MEP team page with Selenium...")
driver = webdriver.Chrome(options=chrome_options)
driver.get(url)

# Wait for page to load
time.sleep(5)

# Scroll to load all content
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

html = driver.page_source
driver.quit()

# Save HTML for inspection
with open('georgia_rendered.html', 'w', encoding='utf-8') as f:
    f.write(html)
print("Saved rendered HTML to georgia_rendered.html")

soup = BeautifulSoup(html, 'html.parser')

staff_data = []

# Look for common staff container patterns
# Pattern 1: Look for divs with staff/team/member classes
containers = soup.find_all('div', class_=lambda x: x and ('team' in str(x).lower() or 'staff' in str(x).lower() or 'member' in str(x).lower() or 'person' in str(x).lower()))

print(f"\nFound {len(containers)} potential staff containers\n")

if containers:
    for container in containers:
        # Extract name
        name = ""
        name_elem = container.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if name_elem:
            name = name_elem.get_text(strip=True)

        # Extract title
        title = ""
        title_elem = container.find(['p', 'span', 'div'], class_=lambda x: x and 'title' in str(x).lower())
        if title_elem:
            title = title_elem.get_text(strip=True)

        # Extract email
        email = ""
        email_link = container.find('a', href=re.compile(r'mailto:'))
        if email_link:
            email = email_link.get('href', '').replace('mailto:', '').strip()

        # Extract phone
        phone = ""
        phone_link = container.find('a', href=re.compile(r'tel:', re.I))
        if phone_link:
            phone = phone_link.get('href', '').replace('tel:', '').replace('Tel:', '').strip()

        if name:
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
            print(f"  Email: {email if email else '(none found)'}")
            print(f"  Phone: {phone if phone else '(none found)'}")
            print()

else:
    print("No staff containers found with standard patterns.")
    print("Analyzing page structure...")

    # Try alternative patterns - look for any headings with emails nearby
    all_headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    print(f"Found {len(all_headings)} headings total")

    # Show sample of page structure for manual review
    print("\nSample headings:")
    for h in all_headings[:10]:
        print(f"  {h.name}: {h.get_text(strip=True)[:80]}")

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
    df = pd.DataFrame(staff_data)
    df.to_csv('ga_staff_temp.csv', index=False)
    print("Saved to ga_staff_temp.csv")

    # Update Excel
    print("\nUpdating GA tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        ga_sheet = wb['GA']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            ga_sheet[f'A{current_row}'] = staff['Name']
            ga_sheet[f'B{current_row}'] = staff['Title']
            ga_sheet[f'C{current_row}'] = staff['Phone']
            ga_sheet[f'D{current_row}'] = staff['Mobile']
            ga_sheet[f'E{current_row}'] = staff['Email']
            ga_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated GA tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted! Please review georgia_rendered.html manually.")
