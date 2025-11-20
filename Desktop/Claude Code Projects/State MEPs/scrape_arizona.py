from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd
from openpyxl import load_workbook
from bs4 import BeautifulSoup

print("Setting up Chrome WebDriver for Arizona...")

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

url = "https://www.azcommerce.com/programs/arizona-mep/who-we-are/our-expert-staff/"
print(f"Loading page: {url}")
driver.get(url)

# Wait for page to fully load
time.sleep(5)

# Scroll to ensure all content loads
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)
driver.execute_script("window.scrollTo(0, 0);")
time.sleep(1)

staff_data = []

# Get page source after JavaScript rendering
html = driver.page_source
soup = BeautifulSoup(html, 'html.parser')

# Look for staff members in the directorsList
directors_list = soup.find('div', class_='directorsList')

if directors_list:
    print("Found directorsList")

    # Look for individual staff cards/sections
    # Try finding all clickable staff elements
    staff_elements = driver.find_elements(By.CSS_SELECTOR, ".directorsList .director, .directorsList .staff-member, .directorsList [class*='staff'], .directorsList [class*='member']")

    if not staff_elements:
        # Try finding by name links or any clickable elements
        staff_elements = driver.find_elements(By.CSS_SELECTOR, ".directorsList a, .directorsList div[onclick]")

    print(f"Found {len(staff_elements)} potential staff elements")

    # If we found clickable elements, click each one to get details
    if staff_elements:
        for idx, element in enumerate(staff_elements, 1):
            try:
                # Get the name from the element
                name = element.text.strip()

                if not name or len(name) < 3:
                    continue

                print(f"\n{idx}. Clicking on: {name}")

                # Click the element
                driver.execute_script("arguments[0].click();", element)
                time.sleep(2)

                # Look for modal or expanded section with details
                # Check for common modal/popup patterns
                modal_selectors = [
                    ".modal-content",
                    ".popup-content",
                    ".director-details",
                    ".staff-details",
                    "[class*='modal']",
                    "[class*='popup']",
                    "[class*='detail']"
                ]

                title = ""
                bio = ""
                phone = ""
                mobile = ""
                email = ""

                # Try to find the details in modal/popup
                for selector in modal_selectors:
                    try:
                        detail_element = driver.find_element(By.CSS_SELECTOR, selector)
                        if detail_element.is_displayed():
                            detail_html = detail_element.get_attribute('innerHTML')
                            detail_soup = BeautifulSoup(detail_html, 'html.parser')

                            # Extract title
                            title_elem = detail_soup.find(['h3', 'h4', 'span'], class_=lambda x: x and ('title' in x.lower() or 'position' in x.lower()))
                            if title_elem:
                                title = title_elem.get_text(strip=True)

                            # Extract bio
                            bio_elem = detail_soup.find(['p', 'div'], class_=lambda x: x and ('bio' in x.lower() or 'description' in x.lower()))
                            if bio_elem:
                                bio = bio_elem.get_text(strip=True)
                            else:
                                # Get all paragraph text
                                paragraphs = detail_soup.find_all('p')
                                if paragraphs:
                                    bio = ' '.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50])

                            # Extract email
                            email_link = detail_soup.find('a', href=lambda x: x and 'mailto:' in x)
                            if email_link:
                                email = email_link.get('href', '').replace('mailto:', '').strip()

                            # Extract phone numbers
                            phone_links = detail_soup.find_all('a', href=lambda x: x and 'tel:' in x)
                            for phone_link in phone_links:
                                phone_text = phone_link.get_text(strip=True).lower()
                                phone_num = phone_link.get('href', '').replace('tel:', '').strip()

                                if 'mobile' in phone_text or 'cell' in phone_text:
                                    mobile = phone_num
                                else:
                                    phone = phone_num

                            break
                    except:
                        continue

                # Close modal if there's a close button
                try:
                    close_buttons = driver.find_elements(By.CSS_SELECTOR, ".close, [class*='close'], .modal-close, [aria-label='Close']")
                    for btn in close_buttons:
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(0.5)
                            break
                except:
                    pass

                # Add staff data
                staff_data.append({
                    'Name': name,
                    'Title': title,
                    'Phone': phone,
                    'Mobile': mobile,
                    'Email': email,
                    'Bio': bio
                })

                print(f"  Title: {title}")
                print(f"  Email: {email}")
                print(f"  Mobile: {mobile}")
                print(f"  Bio: {bio[:80]}..." if len(bio) > 80 else f"  Bio: {bio}")

            except Exception as e:
                print(f"  Error processing staff member: {e}")
                continue

    # If no clickable elements found, try parsing static content
    if not staff_data:
        print("\nNo clickable elements found, trying static content parsing...")

        # Get all text and look for patterns
        all_text = soup.get_text()

        # Look for email addresses
        import re
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', all_text)

        print(f"Found {len(emails)} email addresses")
        for email in emails:
            print(f"  - {email}")

driver.quit()

print(f"\n\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
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
        print("Please close the Excel file if it's open.")
else:
    print("\nNo data extracted. Manual inspection needed.")
