import pandas as pd
from openpyxl import load_workbook

# Read the scraped staff data
staff_df = pd.read_csv('arkansas_staff_temp.csv')

print(f"Loaded {len(staff_df)} staff members from CSV")
print(staff_df[['Name', 'Title', 'Phone', 'Mobile', 'Email']])

# Load the Excel workbook
wb = load_workbook('state_meps.xlsx')

# Access the AR (Arkansas) sheet
ar_sheet = wb['AR']

# Starting at Row 4
# Column A: Name
# Column B: Title
# Column C: Phone
# Column D: Mobile
# Column E: Email
# Column F: Bio
start_row = 4

for idx, row in staff_df.iterrows():
    current_row = start_row + idx
    ar_sheet[f'A{current_row}'] = row['Name']
    ar_sheet[f'B{current_row}'] = row['Title']
    ar_sheet[f'C{current_row}'] = row['Phone'] if pd.notna(row['Phone']) else ""
    ar_sheet[f'D{current_row}'] = row['Mobile'] if pd.notna(row['Mobile']) else ""
    ar_sheet[f'E{current_row}'] = row['Email'] if pd.notna(row['Email']) else ""
    ar_sheet[f'F{current_row}'] = row['Bio'] if pd.notna(row['Bio']) else ""
    print(f"Row {current_row}: {row['Name']} - Phone: {row['Phone']} - Mobile: {row['Mobile']}")

# Save the workbook
wb.save('state_meps.xlsx')
print("\nSuccessfully updated AR tab in state_meps.xlsx with all fields!")
