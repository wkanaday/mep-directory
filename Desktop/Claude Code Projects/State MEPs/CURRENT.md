# Current Project Status

## Session Startup Instructions
When opening Claude Code: "Read PROJECT.md, CURRENT.md, and GITHUB-WORKFLOW.md. Summarize where we are."

## Session Ending Instructions  
When closing: "Update CURRENT.md and push to GitHub"

## What's Working

### Completed States (11/51) - 22% Complete

#### Alabama (AL)
- **Script**: `scrape_alabama_full.py`
- **Staff Count**: 378
- **Data Coverage**: Names, titles (all); emails, phones, bios (partial - only for detailed profiles)
- **Notes**: Two-phase scraping - detailed profiles + basic cards. Large dataset.
- **Status**: WORKING

#### Alaska (AK)
- **Script**: `scrape_alaska_final.py`
- **Staff Count**: 4
- **Data Coverage**: Names, titles, emails (all); phones (minimal); bios (none)
- **Notes**: Small team, simple text parsing from about page
- **Status**: WORKING

#### Arizona (AZ)
- **Script**: `scrape_arizona_final.py`
- **Staff Count**: 10
- **Data Coverage**: Names, titles, emails, bios (all); phones/mobile (most)
- **Notes**: Requires Selenium - JavaScript-rendered content
- **Dependencies**: Chrome, ChromeDriver
- **Status**: WORKING

#### Arkansas (AR)
- **Script**: `scrape_arkansas_staff.py`
- **Staff Count**: 8
- **Data Coverage**: Names, titles, emails (all); phones (most); bios (minimal)
- **Notes**: Standard team container pattern
- **Status**: WORKING

#### California (CA)
- **Script**: `scrape_california.py`
- **Staff Count**: 3
- **Data Coverage**: Names, titles, bios (all); emails, phones (limited)
- **Notes**: Leadership team only - confirmed this is all that's publicly available
- **Status**: WORKING (complete as possible)

#### Colorado (CO)
- **Script**: `scrape_colorado_simple.py`
- **Staff Count**: 7
- **Data Coverage**: Names, titles only - no contact info available
- **Notes**: Static HTML only has basic info - confirmed this is all publicly available
- **Status**: WORKING (complete as possible)

#### Connecticut (CT)
- **Script**: `scrape_connecticut.py`
- **Staff Count**: 29
- **Data Coverage**: Names, titles, emails, phones, bios (comprehensive)
- **Notes**: Profile page crawling with delays. Excellent coverage.
- **Status**: WORKING

#### Delaware (DE)
- **Script**: `scrape_delaware_final.py`
- **Staff Count**: 10
- **Data Coverage**: Names, titles, emails (all); phones (most); bios (none)
- **Notes**: Contact page parsing
- **Status**: WORKING

#### Florida (FL)
- **Script**: `scrape_florida.py`
- **Staff Count**: 7
- **Data Coverage**: Names, titles, emails, phones (all); LinkedIn profiles in bio (6/7)
- **Notes**: Clean structure with h3/h5 tags, phone links extracted successfully
- **Status**: WORKING

#### Georgia (GA)
- **Script**: `scrape_georgia_final.py`
- **Staff Count**: 25
- **Data Coverage**: Names, titles (all); no emails or phones publicly available
- **Notes**: Site has bot protection - used WebFetch tool to extract data
- **Status**: WORKING

#### Hawaii (HI)
- **Script**: `scrape_hawaii.py`
- **Staff Count**: 13
- **Data Coverage**: Names, titles (all); no individual emails or phones publicly available
- **Notes**: HTDC - Innovate Hawaii program, used WebFetch for extraction
- **Status**: WORKING

**Total Staff Collected**: 494 staff members

## What Needs Attention

### Experimental/Old Scripts to Clean Up

These intermediate scripts should be archived or deleted:
- `scrape_alabama.py`, `scrape_alabama_selenium.py`
- `scrape_alaska.py`, `scrape_alaska_selenium.py`
- `scrape_arizona.py`
- `scrape_colorado.py`
- `scrape_delaware.py`, `scrape_delaware_clean.py`

## What to Do Next

### Immediate Priority

**Continue in alphabetical order through remaining states:**

Next states to complete:
1. **Idaho (ID)** - https://www.techhelp.org/staff/
2. **Illinois (IL)** - https://www.imec.org/
3. **Indiana (IN)** - https://mep.purdue.edu/about-us/staff/
4. **Iowa (IA)** - https://www.ciras.iastate.edu/staff-directory/

Then continue through the alphabet...

### Process for Each New State

1. Try generic scraper first: `python scrape_state.py "State Name" XX "url"`
2. Review output CSV and Excel tab
3. If generic scraper fails or data incomplete, create custom scraper
4. Save final version as `scrape_statename_final.py`
5. Update this document with status

## Remaining Work

- **40 states still to complete**
- **Estimated 2,200-3,200 more staff to collect**
- **At current pace**: ~5-10 states per session

## Known Issues

1. **No version control** - should initialize git repository
2. **Code duplication** - each scraper repeats similar code
3. **No automated testing** - all verification is manual
4. **Excel file must be closed** - common source of errors
5. **Some sites may require Selenium** - adds complexity

## Files Generated Per State

- `{state}_staff_temp.csv` - Temporary CSV output
- Updated tab in `state_meps.xlsx` - Main data storage
- `{state}_page.html` - HTML snapshot (optional, for debugging)

## Git Status

**Current branch:** main
**Last commit:** 5b4621f Add existing MEP scraper code and data files
**Ready to merge:** N/A (on main branch)

---
Last Updated: November 2025
Next State to Complete: Idaho (ID)
