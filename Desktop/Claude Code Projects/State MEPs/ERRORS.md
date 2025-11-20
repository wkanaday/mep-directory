# Common Errors and Solutions

## Excel-Related Errors

### Error: "PermissionError: [Errno 13] Permission denied: 'state_meps.xlsx'"

**Cause**: Excel file is open in another program

**Solution**:
```
1. Close state_meps.xlsx in Excel
2. Re-run the scraper
```

**Prevention**: Always close Excel before running scrapers

---

### Error: "KeyError: 'XX'" (where XX is state abbreviation)

**Cause**: State tab doesn't exist in Excel workbook

**Solution**:
```python
# Check if sheet exists before accessing
if state_abbrev not in wb.sheetnames:
    print(f"Creating new sheet for {state_abbrev}")
    wb.create_sheet(state_abbrev)
```

Or manually create the tab in Excel before running scraper

---

## Python Dependency Errors

### Error: "ModuleNotFoundError: No module named 'requests'"

**Cause**: Required Python packages not installed

**Solution**:
```bash
pip install requests beautifulsoup4 pandas openpyxl selenium lxml
```

Or create and use requirements.txt:
```bash
pip install -r requirements.txt
```

---

### Error: "ModuleNotFoundError: No module named 'openpyxl'"

**Cause**: openpyxl not installed (needed for Excel operations)

**Solution**:
```bash
pip install openpyxl
```

---

## Selenium/ChromeDriver Errors

### Error: "selenium.common.exceptions.WebDriverException: Message: 'chromedriver' executable needs to be in PATH"

**Cause**: ChromeDriver not installed or not in system PATH

**Solution 1** (Automated):
```bash
pip install webdriver-manager
```

Update script to use:
```python
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
```

**Solution 2** (Manual):
```
1. Check Chrome version: chrome://version/
2. Download matching ChromeDriver: https://chromedriver.chromium.org/
3. Add to PATH or place in project directory
```

---

### Error: "selenium.common.exceptions.SessionNotCreatedException: Message: session not created: This version of ChromeDriver only supports Chrome version XX"

**Cause**: ChromeDriver version doesn't match Chrome browser version

**Solution**:
```
1. Update Chrome to latest version
2. Download matching ChromeDriver version
3. Or use webdriver-manager (auto-handles versions)
```

---

## Web Scraping Errors

### Error: "requests.exceptions.HTTPError: 403 Forbidden"

**Cause**: Website blocking request (no user-agent or detected as bot)

**Solution**:
```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
response = requests.get(url, headers=headers)
```

---

### Error: "requests.exceptions.HTTPError: 429 Too Many Requests"

**Cause**: Making requests too quickly, rate limited by server

**Solution**:
```python
import time

for profile_url in staff_urls:
    response = requests.get(profile_url, headers=headers)
    # Process response...
    time.sleep(1)  # Wait 1 second between requests
```

Increase delay if still getting 429 errors

---

### Error: "requests.exceptions.ConnectionError: Max retries exceeded"

**Cause**: Network issue or server down

**Solution**:
```
1. Check internet connection
2. Verify URL is correct
3. Try again later (server may be temporarily down)
4. Add retry logic:
```

```python
import time

max_retries = 3
for attempt in range(max_retries):
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        break
    except requests.exceptions.RequestException as e:
        if attempt < max_retries - 1:
            print(f"Attempt {attempt + 1} failed, retrying...")
            time.sleep(5)
        else:
            print(f"Failed after {max_retries} attempts: {e}")
            raise
```

---

### Error: "requests.exceptions.Timeout"

**Cause**: Request taking too long

**Solution**:
```python
# Increase timeout
response = requests.get(url, headers=headers, timeout=60)  # 60 seconds
```

---

## Data Extraction Issues

### Issue: "No staff data extracted" / Empty CSV file

**Cause**: Page structure doesn't match expected pattern

**Debugging Steps**:

1. **Save HTML for inspection**:
```python
with open('debug.html', 'w', encoding='utf-8') as f:
    f.write(response.text)
```

2. **Check if content is JavaScript-rendered**:
```python
# If HTML looks minimal/empty, content may load via JS
# Try with Selenium instead
```

3. **Inspect actual HTML structure**:
- Open saved HTML in browser
- Use browser DevTools to find staff containers
- Note CSS classes and element structure
- Update selectors accordingly

4. **Add debug prints**:
```python
print(f"Found {len(containers)} containers")
for container in containers:
    print(f"Container HTML: {container}")
```

---

### Issue: "Getting wrong data / names are gibberish"

**Cause**: Selecting wrong elements

**Solution**:
```python
# Be more specific with selectors
# Instead of:
name = soup.find('h3').get_text()

# Use:
name_elem = container.find('h3', class_='staff-name')
if name_elem:
    name = name_elem.get_text(strip=True)
```

---

### Issue: "Emails/phones not being extracted"

**Cause**: Different format than expected

**Debugging**:
```python
# Print the container text to see what's there
print(container.get_text())

# Try different patterns
email_link = container.find('a', href=lambda x: x and 'mailto:' in x)
phone_link = container.find('a', href=lambda x: x and 'tel:' in x)

# Or regex search in text
import re
email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
emails = re.findall(email_pattern, container.get_text())
```

---

## Data Quality Issues

### Issue: "Duplicate staff members in output"

**Cause**: Same person appearing in multiple page sections

**Solution**:
```python
# Use a set or dict to track unique names
seen_names = set()
staff_data = []

for container in containers:
    name = # ... extract name
    if name not in seen_names:
        seen_names.add(name)
        staff_data.append({...})
```

---

### Issue: "Phone numbers in inconsistent formats"

**Cause**: Different formatting on website

**Solution**: Normalize format
```python
import re

def normalize_phone(phone_str):
    # Remove all non-digits
    digits = re.sub(r'\D', '', phone_str)

    # Format as (XXX) XXX-XXXX
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    else:
        return phone_str  # Return original if unexpected format

phone = normalize_phone(raw_phone)
```

---

### Issue: "Bios are too long / truncated"

**Cause**: Excel cell has character limit

**Solution**:
```python
# Truncate bios to reasonable length
max_bio_length = 5000
if len(bio) > max_bio_length:
    bio = bio[:max_bio_length] + "..."
```

---

## Script Execution Issues

### Error: "IndentationError: unexpected indent"

**Cause**: Mixed tabs and spaces or incorrect indentation

**Solution**:
```
1. Use consistent indentation (4 spaces recommended)
2. Configure editor to show whitespace
3. Run: python -tt script.py (shows tab/space issues)
```

---

### Error: "SyntaxError: invalid syntax"

**Cause**: Typo or incorrect Python syntax

**Common causes**:
- Missing colon after if/for/while
- Mismatched parentheses/brackets
- Incorrect string quotes

**Solution**: Check the line number in error message, verify syntax

---

### Error: "NameError: name 'soup' is not defined"

**Cause**: Variable used before it's defined

**Solution**: Ensure code is in correct order
```python
# WRONG order:
staff = soup.find_all('div')
soup = BeautifulSoup(response.content, 'html.parser')

# CORRECT order:
soup = BeautifulSoup(response.content, 'html.parser')
staff = soup.find_all('div')
```

---

## Command Line Errors

### Error: "python: command not found" (Mac/Linux) or "'python' is not recognized" (Windows)

**Cause**: Python not installed or not in PATH

**Solution**:
```
1. Install Python from python.org
2. On Windows, check "Add Python to PATH" during installation
3. Try 'python3' instead of 'python' on Mac/Linux
```

---

### Error: "No such file or directory: 'state_meps.xlsx'"

**Cause**: Running script from wrong directory

**Solution**:
```bash
# Navigate to project directory first
cd "C:\Users\wkana\Desktop\Claude Code Projects\State MEPs"

# Then run script
python scrape_alabama_full.py
```

---

## Troubleshooting Process

When a scraper isn't working:

1. **Check basics**:
   - Is Excel file closed?
   - Are dependencies installed?
   - Are you in the right directory?

2. **Verify URL**:
   - Does URL still work in browser?
   - Did website structure change?

3. **Save and inspect HTML**:
   ```python
   with open('debug.html', 'w', encoding='utf-8') as f:
       f.write(response.text)
   ```

4. **Add debug output**:
   ```python
   print(f"Found {len(containers)} staff containers")
   for idx, container in enumerate(containers):
       print(f"\n[{idx}] Container preview:")
       print(container.get_text()[:200])
   ```

5. **Test extraction step-by-step**:
   - First just get names
   - Then add titles
   - Then add contact info
   - Then add bios

6. **Check for JavaScript rendering**:
   - If HTML looks empty/minimal, try Selenium

7. **Review similar state's scraper**:
   - Use working scraper as template
   - Adapt selectors to new site

---

## Getting Help

1. **Check this document** for your specific error
2. **Review ARCHITECTURE.md** for scraping patterns
3. **Check SETUP.md** for installation issues
4. **Inspect HTML** to understand site structure
5. **Test with saved HTML** before hitting live site repeatedly

---
Last Updated: November 2025
