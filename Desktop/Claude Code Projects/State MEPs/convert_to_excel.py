import pandas as pd
import openpyxl
from openpyxl import Workbook

# State name to abbreviation mapping
state_abbrev = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
    'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
    'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID',
    'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS',
    'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
    'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS',
    'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK',
    'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
    'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT',
    'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV',
    'Wisconsin': 'WI', 'Wyoming': 'WY', 'Puerto Rico': 'PR'
}

# Read the CSV file
df = pd.read_csv('state meps.csv')

# Remove any completely empty rows
df = df.dropna(how='all')

# Create Excel writer object
with pd.ExcelWriter('state_meps.xlsx', engine='openpyxl') as writer:
    # First, create the master list sheet with all data
    df.to_excel(writer, sheet_name='Master List', index=False)
    print("Created sheet: Master List (all states)")

    # Then create a sheet for each state
    for state in df['State'].unique():
        if pd.notna(state) and state in state_abbrev:
            state_data = df[df['State'] == state]
            sheet_name = state_abbrev[state]
            state_data.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"Created sheet: {sheet_name} for {state}")

print("\nExcel file 'state_meps.xlsx' created successfully!")
