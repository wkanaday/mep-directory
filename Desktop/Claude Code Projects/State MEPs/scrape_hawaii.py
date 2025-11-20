# Hawaii MEP (HTDC - Innovate Hawaii) Staff Data
# Note: This data was extracted using WebFetch
# The website does not provide individual email addresses or phone numbers publicly

import pandas as pd
from openpyxl import load_workbook

staff_data = [
    # Executive Leadership
    {'Name': 'Trung Lam', 'Title': 'Executive Director & CEO / Acting MEP Center Director', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # Economic Development
    {'Name': 'Matthew Kobayashi', 'Title': 'Project Development Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Sandi Kanemori', 'Title': 'Sr. Economic Program Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Umma Berkelman', 'Title': 'Economic Development Specialist', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Cindy Matsuki', 'Title': 'Economic Development Specialist - HSBIR', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Karlton Tomomitsu', 'Title': 'Economic Development Specialist', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # HCATT (Hawaiʻi Center for Advanced Transportation Technologies)
    {'Name': 'Dave Molinaro', 'Title': 'HCATT Director', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Kristy Carpio', 'Title': 'HCATT Project Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # HI-CAP (Hawaii Capital)
    {'Name': 'Tuan La', 'Title': 'HI-CAP Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # Innovate Hawaiʻi
    {'Name': 'Wayne Layugan', 'Title': 'Program Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Wendy Oshiro', 'Title': 'Project Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # Administrative and Operations
    {'Name': 'Ray Gomez', 'Title': 'Chief Financial Officer', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Stephanie Yuu-Sato', 'Title': 'Contracts & Project Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
]

print(f"Hawaii MEP (HTDC - Innovate Hawaii) Staff Data")
print(f"{'='*60}\n")
print(f"Organization: Hawaii Technology Development Corporation (HTDC)")
print(f"MEP Program: Innovate Hawaii")
print(f"Main Phone: (808) 539-3806")
print(f"General Email: info@htdc.org")
print()

for idx, staff in enumerate(staff_data, 1):
    print(f"[{idx}/{len(staff_data)}] {staff['Name']} - {staff['Title']}")

print(f"\nTotal: {len(staff_data)} staff members")

# Save to CSV
df = pd.DataFrame(staff_data)
df.to_csv('hi_staff_temp.csv', index=False)
print("\nSaved to hi_staff_temp.csv")

# Update Excel
print("\nUpdating HI tab in Excel...")
try:
    wb = load_workbook('state_meps.xlsx')
    hi_sheet = wb['HI']

    start_row = 4

    for idx, staff in enumerate(staff_data):
        current_row = start_row + idx
        hi_sheet[f'A{current_row}'] = staff['Name']
        hi_sheet[f'B{current_row}'] = staff['Title']
        hi_sheet[f'C{current_row}'] = staff['Phone']
        hi_sheet[f'D{current_row}'] = staff['Mobile']
        hi_sheet[f'E{current_row}'] = staff['Email']
        hi_sheet[f'F{current_row}'] = staff['Bio']

    wb.save('state_meps.xlsx')
    print(f"Successfully updated HI tab with {len(staff_data)} staff members!")
except Exception as e:
    print(f"Error updating Excel: {e}")
    print("Please close the Excel file and try again.")
