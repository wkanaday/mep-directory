from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import pandas as pd
from openpyxl import load_workbook

print("Setting up Chrome WebDriver...")

# Setup Chrome options
chrome_options = Options()
chrome_options.add_argument('--headless')  # Run in background
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--window-size=1920,1080')

# Initialize the driver
try:
    driver = webdriver.Chrome(options=chrome_options)
except Exception as e:
    print(f"Error initializing Chrome driver: {e}")
    print("\nTrying without headless mode...")
    chrome_options = Options()
    chrome_options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(options=chrome_options)

url = "https://www.atn.org/about-atn/team-members/"
print(f"Loading page: {url}")
driver.get(url)

# Wait for page to load
time.sleep(5)

staff_data = []

# Find all team member cards with class="item"
items = driver.find_elements(By.CLASS_NAME, "item")
print(f"\nFound {len(items)} staff members")

for idx, item in enumerate(items, 1):
    try:
        # Find the clickable link within the item
        link = item.find_element(By.CLASS_NAME, "team-trigger")

        # Get the name from the diamond title
        try:
            name_elem = item.find_element(By.CLASS_NAME, "diamond__title")
            name_text = name_elem.text.strip()
            # Name is on first line, title is on subsequent lines
            lines = name_text.split('\n')
            name = lines[0] if lines else name_text
        except:
            name = "Unknown"

        print(f"\n[{idx}/{len(items)}] Processing: {name}")

        # Scroll element into view
        driver.execute_script("arguments[0].scrollIntoView(true);", link)
        time.sleep(0.5)

        # Click on the team member
        try:
            link.click()
        except:
            # If regular click doesn't work, try JavaScript click
            driver.execute_script("arguments[0].click();", link)

        # Wait for modal to appear
        time.sleep(2)

        try:
            # Wait for modal content to load
            wait = WebDriverWait(driver, 10)
            modal_name = wait.until(EC.presence_of_element_located((By.ID, "teamModal-name")))

            # Extract information from modal
            name = modal_name.text.strip()

            try:
                title_elem = driver.find_element(By.ID, "teamModal-position")
                title = title_elem.text.strip()
            except:
                title = ""

            # Extract email
            email = ""
            try:
                email_elem = driver.find_element(By.ID, "teamModal-email")
                email_link = email_elem.find_element(By.TAG_NAME, "a")
                email = email_link.text.strip()
            except:
                pass

            # Extract phone
            phone = ""
            try:
                phone_elem = driver.find_element(By.ID, "teamModal-phone")
                phone_link = phone_elem.find_element(By.TAG_NAME, "a")
                phone = phone_link.text.strip()
            except:
                pass

            # Extract bio
            bio = ""
            try:
                bio_elem = driver.find_element(By.ID, "teamModal-content")
                bio = bio_elem.text.strip()
            except:
                pass

            staff_data.append({
                'Name': name,
                'Title': title,
                'Phone': phone,
                'Mobile': '',
                'Email': email,
                'Bio': bio
            })

            print(f"  Name: {name}")
            print(f"  Title: {title}")
            print(f"  Email: {email}")
            print(f"  Phone: {phone}")
            print(f"  Bio: {bio[:80]}..." if len(bio) > 80 else f"  Bio: {bio}")

            # Close modal - try multiple methods
            try:
                close_button = driver.find_element(By.CSS_SELECTOR, "button.close")
                close_button.click()
            except:
                try:
                    # Try clicking backdrop
                    driver.find_element(By.CLASS_NAME, "modal-backdrop").click()
                except:
                    # Press ESC key
                    from selenium.webdriver.common.keys import Keys
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)

            time.sleep(1)

        except Exception as e:
            print(f"  Error extracting modal data: {e}")
            # Try to close any open modal
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except:
                pass

    except Exception as e:
        print(f"  Error processing item: {e}")
        continue

print(f"\n\nSuccessfully extracted {len(staff_data)} staff members with details")

# Close browser
driver.quit()

# Save to CSV
if staff_data:
    df = pd.DataFrame(staff_data)
    df.to_csv('al_staff_selenium.csv', index=False)
    print("Saved to al_staff_selenium.csv")

    # Update Excel
    print("\nUpdating AL tab in Excel...")
    try:
        wb = load_workbook('state_meps.xlsx')
        al_sheet = wb['AL']

        start_row = 4

        for idx, staff in enumerate(staff_data):
            current_row = start_row + idx
            al_sheet[f'A{current_row}'] = staff['Name']
            al_sheet[f'B{current_row}'] = staff['Title']
            al_sheet[f'C{current_row}'] = staff['Phone']
            al_sheet[f'D{current_row}'] = staff['Mobile']
            al_sheet[f'E{current_row}'] = staff['Email']
            al_sheet[f'F{current_row}'] = staff['Bio']

        wb.save('state_meps.xlsx')
        print(f"Successfully updated AL tab with {len(staff_data)} staff members!")
    except Exception as e:
        print(f"Error updating Excel: {e}")
        print("Please close the Excel file and run the update script separately.")
else:
    print("No data extracted!")
