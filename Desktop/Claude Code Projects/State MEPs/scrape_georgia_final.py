# Georgia MEP Staff Data
# Note: This data was extracted using WebFetch since the site blocks automated requests
# The website does not provide email addresses or phone numbers publicly

import pandas as pd
from openpyxl import load_workbook

staff_data = [
    # Leadership
    {'Name': 'Tim Israel', 'Title': 'Director', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # Project Managers
    {'Name': 'Cassia Baker', 'Title': 'Project Manager, Cybersecurity', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Michael Barker', 'Title': 'Project Manager, Cybersecurity', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Sam Darwin', 'Title': 'Project Manager, Process Improvement', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Sandra Enciso', 'Title': 'Project Manager, Energy and Sustainability', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Alfred Gardner', 'Title': 'Project Manager, Human Resources', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Bogna Grabicka', 'Title': 'Project Manager, Safety and Sustainability', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Kelly Grissom', 'Title': 'Project Manager, Energy and Sustainability', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Andy Helm', 'Title': 'Project Manager, Strategy and Leadership Development', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Dean Hettenbach', 'Title': 'Project Manager, Supply Chain and Technology', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Katie Hines', 'Title': 'Project Manager, Process Improvement', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Andrea Hines', 'Title': 'Project Manager, Food and Beverage', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Andrew Krejci', 'Title': 'Project Manager, Technology', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # Region Managers
    {'Name': 'Ben Cheeks', 'Title': 'Region Manager, Coastal Georgia', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Jason Clarke', 'Title': 'Region Manager, Northeast Georgia', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Hank Hobbs', 'Title': 'Region Manager, South Georgia', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Paul LaVigna', 'Title': 'Region Manager, South Metro Atlanta', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # Operations & Support
    {'Name': 'Jay Boudreaux', 'Title': 'Senior Program and Operations Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Anna Cali', 'Title': 'Instructional Systems Designer', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Jasmyn Green', 'Title': 'Program and Operations Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},

    # Marketing & Communications
    {'Name': 'Raine Hyde', 'Title': 'Marketing Strategist', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Megan Johnson', 'Title': 'Marketing Manager, Outreach', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Ieasha Jones', 'Title': 'Special Events', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Amber Kasselman', 'Title': 'Marketing Manager', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
    {'Name': 'Caley Landau', 'Title': 'Marketing Strategist', 'Phone': '', 'Mobile': '', 'Email': '', 'Bio': ''},
]

print(f"Georgia MEP Staff Data")
print(f"{'='*60}\n")

for idx, staff in enumerate(staff_data, 1):
    print(f"[{idx}/{len(staff_data)}] {staff['Name']} - {staff['Title']}")

print(f"\nTotal: {len(staff_data)} staff members")

# Save to CSV
df = pd.DataFrame(staff_data)
df.to_csv('ga_staff_temp.csv', index=False)
print("\nSaved to ga_staff_temp.csv")

# Update Excel
print("\nUpdating GA tab in Excel...")
try:
    wb = load_workbook('state_meps.xlsx')
    ga_sheet = wb['GA']

    start_row = 4

    for idx, staff in enumerate(staff_data):
        current_row = start_row + idx
        ga_sheet[f'A{current_row}'] = staff['Name']
        ga_sheet[f'B{current_row}'] = staff['Title']
        ga_sheet[f'C{current_row}'] = staff['Phone']
        ga_sheet[f'D{current_row}'] = staff['Mobile']
        ga_sheet[f'E{current_row}'] = staff['Email']
        ga_sheet[f'F{current_row}'] = staff['Bio']

    wb.save('state_meps.xlsx')
    print(f"Successfully updated GA tab with {len(staff_data)} staff members!")
except Exception as e:
    print(f"Error updating Excel: {e}")
    print("Please close the Excel file and try again.")
