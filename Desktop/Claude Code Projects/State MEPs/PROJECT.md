# State MEP Staff Scraper Project

## Overview

This project scrapes staff contact information from all U.S. state Manufacturing Extension Partnership (MEP) centers. The goal is to compile a comprehensive database of MEP staff members across all 50 states, territories, and the District of Columbia, including their names, titles, contact details, and biographical information.

## What Are MEPs?

Manufacturing Extension Partnerships (MEPs) are part of a national network supported by the National Institute of Standards and Technology (NIST). Each state has its own MEP center that provides support, consulting, and resources to small and medium-sized manufacturers. These centers are hosted by various organizations including universities, nonprofits, and state agencies.

## Project Goals

1. **Comprehensive Coverage**: Scrape staff information from all 51+ MEP centers (50 states + DC + territories)
2. **Structured Data**: Extract standardized information for each staff member:
   - Name
   - Job Title
   - Phone Number
   - Mobile Number (when available)
   - Email Address
   - Bio/Description (when available)
3. **Centralized Storage**: Maintain data in both CSV and Excel formats for easy analysis and use
4. **Reusability**: Create scraper scripts that can be re-run to update information as needed

## Current Status

### Completed States (8/51)

| State | Status | Staff Count | Script | Notes |
|-------|--------|-------------|--------|-------|
| Alabama (AL) | Complete | 378 | `scrape_alabama_full.py` | Two-phase scrape: detailed profiles + basic cards |
| Alaska (AK) | Complete | 4 | `scrape_alaska_final.py` | Simple text parsing from about page |
| Arizona (AZ) | Complete | 10 | `scrape_arizona_final.py` | Requires Selenium (JS-rendered) |
| Arkansas (AR) | Complete | 8 | `scrape_arkansas_staff.py` | Basic team container parsing |
| California (CA) | Complete | 3 | `scrape_california.py` | Team member card structure |
| Colorado (CO) | Complete | 7 | `scrape_colorado_simple.py` | Name/title only, no contact info |
| Connecticut (CT) | Complete | 29 | `scrape_connecticut.py` | Profile page crawling with delays |
| Delaware (DE) | Complete | 10 | `scrape_delaware_final.py` | Paragraph-based parsing |

**Total Staff Collected**: 449+ staff members

### Remaining States (43)

All other states from the `state meps.csv` file need scrapers developed:
- DC, FL, GA, HI, ID, IL, IN, IA, KS, KY, LA, ME, MD, MA, MI, MN, MS, MO, MT, NE, NV, NH, NJ, NM, NY, NC, ND, OH, OK, OR, PA, RI, SC, SD, TN, TX, UT, VT, VA, WA, WV, WI, WY, Puerto Rico

## Data Organization

### Files Structure

- **`state meps.csv`**: Master list of all state MEP centers with their URLs
- **`state_meps.xlsx`**: Excel workbook with separate tabs for each state's staff data
- **`{state}_staff_temp.csv`**: Individual CSV files for each state (temporary/backup)
- **Scraper scripts**: State-specific Python scripts named `scrape_{state}.py`
- **HTML snapshots**: Saved HTML files used during development/debugging

### Data Schema

Each staff member record contains:
- **Name**: Full name of staff member
- **Title**: Job title/position
- **Phone**: Primary phone number
- **Mobile**: Mobile/cell phone number (if different from primary)
- **Email**: Email address
- **Bio**: Professional biography or description

## Technical Approach

The project uses Python with web scraping libraries to extract data from various MEP websites. Due to the diverse nature of these sites, each state often requires a customized scraping approach (see ARCHITECTURE.md for details).

## How to Work with Me
- Work autonomously on assigned tasks
- Only check in when complete or genuinely blocked
- Don't ask permission for routine steps
- Execute full tasks before reporting back

## Next Steps

1. Continue developing scrapers for remaining 43 states
2. Test and validate all existing scrapers
3. Set up automated refresh/update mechanism
4. Consolidate all data into final database format
5. Create analysis tools for the collected data

## Success Metrics

- **Completion**: Scrapers for all 51+ MEP centers
- **Data Quality**: >90% of records have email addresses
- **Maintainability**: Scripts can be re-run to update data
- **Documentation**: Clear instructions for running and maintaining scrapers

## Timeline

Project started: October 2025
Current completion: ~16% (8/51 states)

---
Last Updated: November 2025
