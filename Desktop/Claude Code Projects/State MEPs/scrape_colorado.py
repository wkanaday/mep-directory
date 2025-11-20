from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd
from openpyxl import load_workbook
from bs4 import BeautifulSoup

print("Setting up Chrome WebDriver for Colorado...")

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

url = "https://manufacturersedge.com/about/#team"
print(f"Loading page: {url}")
driver.get(url)

# Wait for page to fully load
time.sleep(5)

# Scroll to team section
try:
    team_section = driver.find_element(By.ID, "team")
    driver.execute_script("arguments[0].scrollIntoView();", team_section)
    time.sleep(2)
except:
    print("Could not find team section, continuing anyway...")

staff_data = []

# Look for team member cards/elements
# Try different selectors
selectors_to_try = [
    ".team-member",
    ".staff-member",
    "[class*='team']",
    "[class*='staff']",
    "[class*='member']",
    ".et_pb_team_member",
    ".wpb_wrapper .team",
]

team_elements = []
for selector in selectors_to_try:
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        if elements and len(elements) > 2:  # Need at least a few team members
            print(f"Found {len(elements)} elements with selector: {selector}")
            team_elements = elements
            break
    except:
        continue

# If no specific team elements found, look for clickable profile images/cards
if not team_elements:
    print("Trying to find clickable profile elements...")

    # Get page source and analyze
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Look for profile images or cards that might be clickable
    profile_selectors = [
        "img[alt*='team']",
        "img[alt*='staff']",
        "a[href*='#']",
        ".profile-card",
        ".bio-card"
    ]

    for selector in profile_selectors:
        elements = soup.select(selector)
        if elements:
            print(f"Found {len(elements)} elements with selector: {selector}")
            # Try to click these elements
            try:
                clickable_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if clickable_elements:
                    team_elements = clickable_elements
                    break
            except:
                continue

# If still no elements, try finding all clickable elements in the team section
if not team_elements:
    print("Looking for clickable elements in page...")
    try:
        # Get all elements that might trigger a modal
        clickable = driver.find_elements(By.CSS_SELECTOR, "[data-toggle='modal'], [data-target], [onclick*='modal'], [onclick*='popup']")
        if clickable:
            print(f"Found {len(clickable)} potentially clickable elements")
            team_elements = clickable
    except:
        pass

print(f"\nFound {len(team_elements)} team member elements to process")

# Process each team member
for idx, element in enumerate(team_elements, 1):
    try:
        print(f"\n{idx}. Processing team member...")

        # Try to get name from element first
        try:
            name_text = element.text.strip()
            if name_text and len(name_text) < 100:
                print(f"   Element text: {name_text[:50]}")
        except:
            name_text = ""

        # Click the element
        try:
            driver.execute_script("arguments[0].click();", element)
            time.sleep(2)
        except:
            # Try regular click
            try:
                element.click()
                time.sleep(2)
            except:
                print(f"   Could not click element {idx}")
                continue

        # Look for modal/popup with details
        modal_found = False
        modal_selectors = [
            ".modal-content",
            ".popup-content",
            "[role='dialog']",
            ".modal",
            ".popup",
            ".fancybox-content",
            ".mfp-content"
        ]

        for modal_selector in modal_selectors:
            try:
                modal = WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, modal_selector))
                )

                if modal.is_displayed():
                    modal_html = modal.get_attribute('innerHTML')
                    modal_soup = BeautifulSoup(modal_html, 'html.parser')

                    # Extract name
                    name = ""
                    name_tags = modal_soup.find_all(['h1', 'h2', 'h3', 'h4'])
                    for tag in name_tags:
                        text = tag.get_text(strip=True)
                        if text and len(text) < 100 and len(text) > 3:
                            name = text
                            break

                    # Extract title
                    title = ""
                    # Look for title patterns
                    title_patterns = [
                        modal_soup.find(class_=lambda x: x and 'title' in x.lower()),
                        modal_soup.find(class_=lambda x: x and 'position' in x.lower()),
                        modal_soup.find('p', class_=lambda x: x and 'job' in str(x).lower())
                    ]

                    for pattern in title_patterns:
                        if pattern:
                            title = pattern.get_text(strip=True)
                            break

                    # If no title found with class, look for text after name
                    if not title and name:
                        # Find all text and look for patterns
                        all_text = modal_soup.get_text()
                        lines = [l.strip() for l in all_text.split('\n') if l.strip()]
                        # Title is usually right after name
                        for i, line in enumerate(lines):
                            if name in line and i + 1 < len(lines):
                                potential_title = lines[i + 1]
                                if len(potential_title) < 100:
                                    title = potential_title
                                    break

                    # Extract bio
                    bio = ""
                    bio_paragraphs = modal_soup.find_all('p')
                    bio_parts = []
                    for p in bio_paragraphs:
                        text = p.get_text(strip=True)
                        # Skip if it's the name or title
                        if text and text != name and text != title and len(text) > 50:
                            bio_parts.append(text)

                    bio = ' '.join(bio_parts)

                    if name:
                        staff_data.append({
                            'Name': name,
                            'Title': title,
                            'Phone': '',
                            'Mobile': '',
                            'Email': '',
                            'Bio': bio
                        })

                        print(f"   Found: {name}")
                        print(f"   Title: {title}")
                        print(f"   Bio: {bio[:80]}..." if len(bio) > 80 else f"   Bio: {bio}")

                        modal_found = True

                    # Close modal
                    try:
                        close_buttons = driver.find_elements(By.CSS_SELECTOR, ".close, [aria-label='Close'], .modal-close, .mfp-close")
                        for btn in close_buttons:
                            if btn.is_displayed():
                                btn.click()
                                time.sleep(1)
                                break
                    except:
                        # Try pressing ESC key
                        from selenium.webdriver.common.keys import Keys
                        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                        time.sleep(1)

                    break

            except Exception as e:
                continue

        if not modal_found:
            print(f"   No modal found for element {idx}")

    except Exception as e:
        print(f"   Error processing element {idx}: {e}")
        continue

driver.quit()

print(f"\n\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    df = pd.DataFrame(staff_data)
    df.to_csv('co_staff_temp.csv', index=False)
    print("Saved to co_staff_temp.csv")

    # Update Excel
    print("\nUpdating CO tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        co_sheet = wb['CO']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            co_sheet[f'A{current_row}'] = staff['Name']
            co_sheet[f'B{current_row}'] = staff['Title']
            co_sheet[f'C{current_row}'] = staff['Phone']
            co_sheet[f'D{current_row}'] = staff['Mobile']
            co_sheet[f'E{current_row}'] = staff['Email']
            co_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated CO tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file if it's open.")
else:
    print("\nNo data extracted. Manual inspection needed.")
