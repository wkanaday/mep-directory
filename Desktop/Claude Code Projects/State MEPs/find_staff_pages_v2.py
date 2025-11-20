import csv
import json

# We'll manually collect the staff page URLs using web searches
# This script will help format the results

def create_mep_list(input_csv):
    """Create a list of MEP centers for manual research"""
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    mep_list = []
    for row in rows:
        if not row.get('Staff Page', '').strip():
            mep_list.append({
                'state': row['State'],
                'name': row['Program Name (MEP Center)'],
                'host': row['Host Organization']
            })

    return mep_list

def save_mep_list(mep_list, output_file):
    """Save the MEP list to a JSON file for tracking"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(mep_list, f, indent=2)

    print(f"Saved {len(mep_list)} MEP centers to {output_file}")
    print("\nMEP Centers needing staff pages:")
    for mep in mep_list:
        print(f"  - {mep['state']}: {mep['name']}")

if __name__ == "__main__":
    input_file = "state meps.csv"
    output_file = "mep_list.json"

    mep_list = create_mep_list(input_file)
    save_mep_list(mep_list, output_file)
