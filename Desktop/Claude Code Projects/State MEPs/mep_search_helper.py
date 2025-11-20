import csv

def read_mep_centers(csv_file):
    """Read MEP centers that need staff pages"""
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Filter rows that don't have staff pages
    needs_research = []
    for row in rows:
        if not row.get('Staff Page', '').strip():
            needs_research.append({
                'state': row['State'],
                'name': row['Program Name (MEP Center)'],
                'host': row['Host Organization']
            })

    return needs_research, rows

def update_csv_with_url(csv_file, state, staff_url):
    """Update the CSV with a staff URL for a specific state"""
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Find and update the row
    for row in rows:
        if row['State'] == state:
            row['Staff Page'] = staff_url
            break

    # Write back
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['State', 'Program Name (MEP Center)', 'Host Organization', 'Staff Page']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated {state}: {staff_url}")

if __name__ == "__main__":
    csv_file = "state meps.csv"
    needs_research, all_rows = read_mep_centers(csv_file)

    print(f"Total MEP Centers: {len(all_rows)}")
    print(f"Need staff pages: {len(needs_research)}")
    print("\nMEP Centers needing research:")
    for i, mep in enumerate(needs_research, 1):
        print(f"{i}. {mep['state']}: {mep['name']}")
