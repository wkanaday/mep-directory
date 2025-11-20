from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd
from openpyxl import load_workbook
import re

print("Setting up Chrome WebDriver...")

chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--window-size=1920,1080')

try:
    driver = webdriver.Chrome(options=chrome_options)
except:
    print("Headless mode failed, trying with visible browser...")
    chrome_options = Options()
    driver = webdriver.Chrome(options=chrome_options)

url = "https://www.alaska-mep.org/team"
print(f"Loading page: {url}")
driver.get(url)

# Wait for page to fully load
time.sleep(5)

staff_data = []

# Scroll through page to ensure all content loads
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)
driver.execute_script("window.scrollTo(0, 0);")
time.sleep(1)

# Get page source after JavaScript rendering
html = driver.page_source
soup_after_js = BeautifulSoup(html, 'html.parser')

# Find all sections that might contain staff
# Look for email links
from bs4 import BeautifulSoup

email_links = driver.find_elements(By.CSS_SELECTOR, "a[href^='mailto:']")

print(f"\nFound {len(email_links)} email links")

# Track processed emails to avoid duplicates
processed = set()

for link in email_links:
    try:
        email = link.get_attribute('href').replace('mailto:', '').replace('?', '').strip()

        if '@alaska.edu' not in email or email in processed:
            continue

        processed.add(email)

        # Find parent elements to locate name and title
        parent = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'row')]")

        # Get all text blocks in this row
        text_elements = parent.find_elements(By.CSS_SELECTOR, "div.sqs-block-content")

        name = ""
        title = ""
        bio = ""
        phone = ""

        for elem in text_elements:
            text = elem.text.strip()

            if not text or text in ['MEET THE TEAM', 'PARTNERSHIPS', 'Subscribe']:
                continue

            # Look for phone
            if 'tel:' in elem.get_attribute('innerHTML'):
                phone_elem = elem.find_elements(By.CSS_SELECTOR, "a[href^='tel:']")
                if phone_elem:
                    phone = phone_elem[0].get_attribute('href').replace('tel:', '').strip()

            # Name is usually the first short text
            if not name and len(text) < 100 and len(text) > 3:
                name = text
            # Title is the second short text
            elif name and not title and len(text) < 100 and len(text) > 3:
                title = text
            # Bio is longer text
            elif name and title and len(text) > 100:
                bio = text

        if name:
            staff_data.append({
                'Name': name,
                'Title': title,
                'Phone': phone,
                'Mobile': '',
                'Email': email,
                'Bio': bio
            })

            print(f"\nFound: {name}")
            print(f"  Title: {title}")
            print(f"  Email: {email}")
            print(f"  Phone: {phone}")
            print(f"  Bio: {bio[:80]}..." if len(bio) > 80 else f"  Bio: {bio}")

    except Exception as e:
        print(f"  Error processing link: {e}")
        continue

driver.quit()

print(f"\n\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
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
        print("Please close the Excel file if it's open.")
else:
    print("No data extracted!")
