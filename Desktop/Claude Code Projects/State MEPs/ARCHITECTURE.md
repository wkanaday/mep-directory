# State MEP Scraper Architecture

## Overview

This document describes the technical architecture of the State MEP staff scraping system, including different scraping patterns, common utilities, and design decisions.

## Core Technologies

- **Python 3.x**: Main programming language
- **BeautifulSoup4**: HTML parsing and DOM traversal
- **requests**: HTTP requests for static pages
- **Selenium**: Browser automation for JavaScript-rendered pages
- **pandas**: Data manipulation and CSV export
- **openpyxl**: Excel file reading and writing
- **re**: Regular expressions for pattern matching (emails, phones, etc.)

## Scraping Patterns

Due to the diverse nature of MEP websites, several distinct scraping patterns have emerged:

### Pattern 1: Static HTML Parsing (Basic)

**Used by**: Alaska, Delaware, Arkansas, California, Colorado

**Characteristics**:
- Content is in the initial HTML response
- No JavaScript rendering required
- Simple DOM structure with clear CSS classes

**Process**:
1. Make HTTP request with user-agent header
2. Parse HTML with BeautifulSoup
3. Find staff containers using CSS selectors
4. Extract name, title, email, phone from container

**Example** (Alaska - `scrape_alaska_final.py:23-82`):
```python
# Find the "OUR TEAM" section
team_section = soup.find('h3', string=re.compile(r'OUR TEAM', re.I))
# Get parent container
parent = team_section.find_parent('div', class_='sqs-html-content')
# Find all names in <strong> tags
strongs = p.find_all('strong')
# Extract email using regex pattern
email_match = re.search(r'[\s\n]([a-zA-Z0-9._%+-]+@alaska\.edu)', remaining_text)
```

### Pattern 2: Multi-Phase Scraping

**Used by**: Alabama

**Characteristics**:
- Multiple data sources on same page
- Some staff have detailed profiles, others have basic info
- Need to merge data from different sections

**Process** (Alabama - `scrape_alabama_full.py:19-105`):
1. **Phase 1**: Extract detailed staff from tab-panes (full contact info + bios)
2. **Phase 2**: Extract basic staff from diamond cards (name + title only)
3. Merge both datasets ensuring no duplicates

**Code Flow**:
```python
# Phase 1: Detailed profiles
tab_panes = soup.find_all('div', class_='tab-pane')
detailed_staff[name] = {...}  # Store in dict by name

# Phase 2: Basic cards
items = soup.find_all('div', class_='item')
# Add to list if not already in detailed_staff

# Result: Complete list with mixed detail levels
```

### Pattern 3: JavaScript-Rendered Content (Selenium)

**Used by**: Arizona

**Characteristics**:
- Content loads via JavaScript after page load
- Initial HTML response is incomplete
- Requires browser automation

**Process** (Arizona - `scrape_arizona_final.py:17-40`):
1. Initialize headless Chrome browser
2. Load page and wait for JavaScript execution
3. Scroll to trigger lazy-loading
4. Extract rendered HTML
5. Parse with BeautifulSoup

**Code**:
```python
chrome_options = Options()
chrome_options.add_argument('--headless')
driver = webdriver.Chrome(options=chrome_options)
driver.get(url)
time.sleep(5)  # Wait for JS
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
html = driver.page_source
driver.quit()
```

### Pattern 4: Profile Page Crawling

**Used by**: Connecticut

**Characteristics**:
- Staff list page contains links to individual profiles
- Detailed information only on profile pages
- Requires multiple HTTP requests

**Process** (Connecticut - `scrape_connecticut.py:12-107`):
1. Fetch team listing page
2. Extract all profile URLs (using regex `/staff/`)
3. Visit each profile page sequentially
4. Extract details from individual pages
5. Add delay between requests (politeness)

**Code Flow**:
```python
# Step 1: Get all profile links
staff_links = soup.find_all('a', href=re.compile(r'/staff/'))
staff_urls = list(set([link.get('href') for link in staff_links]))

# Step 2: Visit each profile
for profile_url in staff_urls:
    profile_response = requests.get(profile_url, headers=headers)
    profile_soup = BeautifulSoup(profile_response.content, 'html.parser')
    # Extract name, title, email, phone, bio
    time.sleep(0.5)  # Be polite
```

### Pattern 5: Generic/Flexible Scraping

**Used by**: scrape_state.py (general purpose)

**Characteristics**:
- Attempts multiple extraction strategies
- Falls back gracefully if one approach fails
- Can handle various site structures

**Strategy** (`scrape_state.py:96-106`):
1. Try finding team containers
2. If not found, try staff/member cards
3. If not found, try card/profile sections
4. For each container:
   - Look for name in heading tags
   - Look for title in various locations
   - Extract contact info using regex
   - Follow profile links if available

## Data Extraction Patterns

### Name Extraction

**Priority order**:
1. Text from `<h1>`, `<h2>`, `<h3>` tags
2. Text from elements with class containing "name"
3. Strong/bold text at start of section
4. Link text to profile pages

**Cleaning**:
- Remove "Ph.D.", "PhD" suffixes
- Strip extra whitespace
- Validate length < 100 characters

### Title Extraction

**Priority order**:
1. Elements with class containing "title", "position", "role"
2. `<em>` or `<small>` tags near name
3. Next sibling of name element
4. First paragraph after name

### Email Extraction

**Methods**:
1. `<a href="mailto:...">` links
2. Regex pattern: `[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`
3. Search in visible text

### Phone Extraction

**Methods**:
1. `<a href="tel:...">` links
2. Regex patterns:
   - `\(?(\d{3})\)?[-.\s]?\d{3}[-.\s]?\d{4}` (standard)
   - Look for "Phone:", "Tel:", "Office:" labels
   - Distinguish "Mobile" vs regular phone

**Formatting**: Normalized to `(XXX) XXX-XXXX`

### Bio Extraction

**Methods**:
1. Look for `<div>` with class containing "bio", "content", "description"
2. Collect paragraph text (skip short ones < 50 chars)
3. Join multiple paragraphs with spaces
4. Extract from profile pages when available

## Excel Integration

All scrapers update the `state_meps.xlsx` workbook:

**Process** (`scrape_state.py:203-237`):
1. Load existing workbook with `openpyxl`
2. Access state tab by abbreviation (e.g., 'AL', 'AK')
3. Write data starting at row 4:
   - Column A: Name
   - Column B: Title
   - Column C: Phone
   - Column D: Mobile
   - Column E: Email
   - Column F: Bio
4. Save workbook

**Error Handling**:
- Check if state tab exists
- Handle file being open (can't save)
- Preserve existing formatting

## Utility Scripts

### convert_to_excel.py

Converts CSV files to Excel format
- Creates tabs for each state
- Applies basic formatting

### update_csv_with_urls.py

Updates the master state list with URLs
- Adds/updates staff page URLs
- Maintains state information

### find_staff_pages.py / mep_search_helper.py

Helper scripts for finding staff page URLs
- Automated search and URL discovery
- Used during initial setup

## Design Decisions

### Why State-Specific Scripts?

**Pros**:
- Optimized for each site's structure
- Easier to debug and maintain
- Can handle special cases
- No complex conditional logic

**Cons**:
- Code duplication
- More files to manage

**Decision**: Use state-specific scripts for completed states, generic script for initial attempts.

### Why Both CSV and Excel?

- **CSV**: Easy to inspect, version control, backup
- **Excel**: Better for human review, multiple tabs, preserves formatting

### Why Selenium Only When Needed?

- **Performance**: HTTP requests much faster than browser automation
- **Reliability**: Fewer dependencies, less likely to break
- **Resources**: Chrome/Selenium more resource intensive

**Rule**: Try requests + BeautifulSoup first, use Selenium only if content is JavaScript-rendered.

### Why Delays Between Requests?

- **Politeness**: Avoid overwhelming target servers
- **Reliability**: Reduces chance of rate limiting
- **Ethics**: Respectful scraping practices

**Standard delays**:
- 0.5-1 second between profile pages
- 2-5 seconds for Selenium page loads

## Common Patterns Reference

### Basic Template

```python
import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook

headers = {'User-Agent': 'Mozilla/5.0 ...'}
url = "..."

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

staff_data = []
# ... extraction logic ...

# Save to CSV
df = pd.DataFrame(staff_data)
df.to_csv('xx_staff_temp.csv', index=False)

# Update Excel
wb = load_workbook('state_meps.xlsx')
state_sheet = wb['XX']
# ... write data ...
wb.save('state_meps.xlsx')
```

### Error Handling Pattern

```python
try:
    # Scraping logic
    pass
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
```

## Testing Approach

1. **HTML Snapshots**: Save page HTML to files for offline testing
2. **CSV Validation**: Check output CSV for correct formatting
3. **Manual Review**: Spot-check Excel output
4. **Count Validation**: Compare scraped count to expected count

## Future Improvements

1. **Unified Framework**: Create base scraper class with common methods
2. **Configuration Files**: JSON/YAML config for each state instead of separate scripts
3. **Automated Testing**: Unit tests for extraction functions
4. **Change Detection**: Alert when site structure changes
5. **Parallel Processing**: Scrape multiple states concurrently
6. **Database Integration**: Store in SQLite/PostgreSQL instead of Excel
7. **API Layer**: Expose data via REST API

---
Last Updated: November 2024
