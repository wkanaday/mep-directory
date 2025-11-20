import requests
from bs4 import BeautifulSoup
import pandas as pd
from openpyxl import load_workbook

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

url = "https://manufacturersedge.com/about/#team"

print(f"Fetching Colorado MEP team page...")
response = requests.get(url, headers=headers)
response.raise_for_status()

soup = BeautifulSoup(response.content, 'html.parser')

staff_data = []

# Find all team items
items = soup.find_all('div', class_='item')

print(f"\nFound {len(items)} team members\n")

for item in items:
    # Get name
    name_div = item.find('div', class_='name')
    name = name_div.get_text(strip=True) if name_div else ""

    # Get title/role
    role_div = item.find('div', class_='role')
    title = role_div.get_text(strip=True) if role_div else ""

    if name:
        staff_data.append({
            'Name': name,
            'Title': title,
            'Phone': '',
            'Mobile': '',
            'Email': '',
            'Bio': ''  # Bio data requires JavaScript interaction, not available in static HTML
        })

        print(f"Found: {name}")
        print(f"  Title: {title}")
        print()

print(f"\nSuccessfully extracted {len(staff_data)} staff members")

if staff_data:
    # Save to CSV
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
        print("Please close the Excel file and try again.")
else:
    print("\nNo staff data extracted!")
