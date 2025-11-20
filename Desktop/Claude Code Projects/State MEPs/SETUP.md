# State MEP Scraper Setup Guide

## Prerequisites

- **Python 3.7+**: Required for all scripts
- **Google Chrome**: Required if running scrapers that use Selenium
- **ChromeDriver**: Must match your Chrome version (for Selenium scrapers)

## Installation

### 1. Install Python Dependencies

Create a virtual environment (recommended):
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate

# On Mac/Linux:
source venv/bin/activate
```

Install required packages:
```bash
pip install requests beautifulsoup4 pandas openpyxl selenium lxml
```

Or create a `requirements.txt` with the following and install:
```
requests>=2.28.0
beautifulsoup4>=4.11.0
pandas>=1.5.0
openpyxl>=3.0.0
selenium>=4.0.0
lxml>=4.9.0
```

Install with:
```bash
pip install -r requirements.txt
```

### 2. Install ChromeDriver (Only for Selenium Scrapers)

**Automated Method**:
```bash
pip install webdriver-manager
```

Then update Selenium scripts to use:
```python
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
```

**Manual Method**:
1. Check your Chrome version: `chrome://version/`
2. Download matching ChromeDriver from: https://chromedriver.chromium.org/
3. Add ChromeDriver to your system PATH

### 3. Verify Excel File

Ensure `state_meps.xlsx` exists in the project directory with:
- Tabs for each state (AL, AK, AZ, etc.)
- Headers in rows 1-3
- Data starting at row 4

## Running Scrapers

### State-Specific Scrapers

Each completed state has its own scraper script. Run them directly:

```bash
# Alabama
python scrape_alabama_full.py

# Alaska
python scrape_alaska_final.py

# Arizona (requires Selenium/Chrome)
python scrape_arizona_final.py

# Arkansas
python scrape_arkansas_staff.py

# California
python scrape_california.py

# Colorado
python scrape_colorado_simple.py

# Connecticut
python scrape_connecticut.py

# Delaware
python scrape_delaware_final.py
```

**Expected Behavior**:
- Progress messages print to console
- Creates `{state}_staff_temp.csv` with scraped data
- Updates corresponding tab in `state_meps.xlsx`
- Excel file must be closed before running

### Generic Scraper

For states without custom scrapers, use the generic script:

```bash
python scrape_state.py <state_name> <state_abbrev> <staff_url>
```

**Example**:
```bash
python scrape_state.py Florida FL "https://www.floridamakes.com/about-us/our-team/staff"
```

**Parameters**:
- `state_name`: Full state name (e.g., "Florida")
- `state_abbrev`: Two-letter abbreviation (e.g., "FL")
- `staff_url`: URL to the staff/team page

**Note**: Generic scraper attempts multiple patterns but may require customization for each state.

## Testing Scrapers

### 1. Test Individual Scraper

```bash
python scrape_alabama_full.py
```

Check console output for:
- Number of staff found
- Names and titles being extracted
- Any error messages

### 2. Verify CSV Output

```bash
# View first few lines
head -5 al_staff_temp.csv

# Count records (subtract 1 for header)
wc -l al_staff_temp.csv
```

### 3. Verify Excel Output

Open `state_meps.xlsx` and check the state tab:
- Data starts at row 4
- All columns populated correctly
- No formatting issues

### 4. Test Without Updating Excel

Comment out the Excel update section in the script temporarily:
```python
# # Update Excel
# print("\nUpdating AL tab in Excel...")
# try:
#     wb = load_workbook('state_meps.xlsx')
#     ...
```

This allows you to test extraction without modifying the Excel file.

## Common Issues and Solutions

### Issue: "Excel file is locked"

**Solution**: Close `state_meps.xlsx` in Excel before running scraper

### Issue: "ModuleNotFoundError: No module named 'requests'"

**Solution**: Install dependencies with `pip install -r requirements.txt`

### Issue: "selenium.common.exceptions.WebDriverException"

**Solution**:
- Install ChromeDriver matching your Chrome version
- Or use webdriver-manager (see Installation section)

### Issue: "No staff data extracted"

**Solution**:
- Website structure may have changed
- Save page HTML for inspection:
  ```python
  with open('debug.html', 'w', encoding='utf-8') as f:
      f.write(response.text)
  ```
- Adjust CSS selectors/regex patterns as needed

### Issue: Rate limiting / 429 errors

**Solution**: Increase delays between requests
```python
time.sleep(2)  # Increase from 0.5 to 2 seconds
```

## Development Workflow

### Creating a New State Scraper

1. **Find the staff page URL**:
   - Look in `state meps.csv` for the URL
   - Or visit the MEP website and find the team/staff page

2. **Save page HTML for analysis**:
   ```bash
   curl "https://example.com/staff" -o state_page.html
   ```

3. **Inspect HTML structure**:
   - Open in browser dev tools
   - Identify CSS classes/IDs for staff containers
   - Note where name, title, email, phone are located

4. **Start with generic scraper**:
   ```bash
   python scrape_state.py "State Name" XX "https://example.com/staff"
   ```

5. **If generic fails, create custom scraper**:
   - Copy a similar state's scraper
   - Modify CSS selectors and extraction logic
   - Test iteratively

6. **Save final script**:
   - Name: `scrape_statename_final.py`
   - Update CURRENT.md with status

### Saving HTML Snapshots

For offline testing and debugging:

```python
# Add to scraper
with open('statename_page.html', 'w', encoding='utf-8') as f:
    f.write(response.text)
```

Or use curl:
```bash
curl -A "Mozilla/5.0" "https://example.com/staff" -o statename_page.html
```

## File Organization

```
State MEPs/
├── scrape_state.py              # Generic scraper
├── scrape_alabama_full.py       # State-specific scrapers
├── scrape_alaska_final.py
├── scrape_arizona_final.py
├── ...
├── state meps.csv               # Master state list
├── state_meps.xlsx              # Output workbook
├── al_staff_temp.csv            # Temporary CSV outputs
├── ak_staff_temp.csv
├── ...
├── alabama_page.html            # HTML snapshots (optional)
├── alaska_page.html
├── ...
├── PROJECT.md                   # Documentation
├── ARCHITECTURE.md
├── SETUP.md
├── CURRENT.md
└── ERRORS.md
```

## Utility Scripts

### convert_to_excel.py

Converts CSV files to Excel format:
```bash
python convert_to_excel.py
```

### update_csv_with_urls.py

Updates master state list:
```bash
python update_csv_with_urls.py
```

## Best Practices

1. **Always close Excel file** before running scrapers
2. **Test with HTML snapshots** before hitting live sites repeatedly
3. **Use delays** between requests (0.5-1 second minimum)
4. **Check robots.txt** on target sites
5. **Save CSV backups** before re-running scrapers
6. **Version control** your scripts and data
7. **Document special cases** in comments

## Running All Completed States

Create a batch script to run all completed scrapers:

**Windows (run_all.bat)**:
```batch
@echo off
echo Running all state scrapers...
python scrape_alabama_full.py
python scrape_alaska_final.py
python scrape_arizona_final.py
python scrape_arkansas_staff.py
python scrape_california.py
python scrape_colorado_simple.py
python scrape_connecticut.py
python scrape_delaware_final.py
echo Done!
```

**Mac/Linux (run_all.sh)**:
```bash
#!/bin/bash
echo "Running all state scrapers..."
python scrape_alabama_full.py
python scrape_alaska_final.py
python scrape_arizona_final.py
python scrape_arkansas_staff.py
python scrape_california.py
python scrape_colorado_simple.py
python scrape_connecticut.py
python scrape_delaware_final.py
echo "Done!"
```

Make executable: `chmod +x run_all.sh`

## Updating Data

To refresh data for all states:
1. Close `state_meps.xlsx`
2. Run all scrapers (or use batch script)
3. Review changes in Excel
4. Backup updated file

## Getting Help

- Review ERRORS.md for common issues
- Check ARCHITECTURE.md for technical details
- Inspect HTML snapshots when debugging
- Test with saved HTML files first

---
Last Updated: November 2025
