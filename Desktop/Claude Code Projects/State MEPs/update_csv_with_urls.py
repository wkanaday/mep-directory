import csv

# Staff page URLs found so far
staff_pages = {
    'Alabama': 'https://www.atn.org/about-atn/team-members/',
    'Alaska': 'https://alaska-mep.com/team-info-_1',
    'Arizona': 'https://www.azcommerce.com/programs/arizona-mep/who-we-are/our-expert-staff/',
    'Arkansas': 'https://www.mfgsolutions.org/our-team/',
    'California': 'https://www.cmtc.com/cmtc-board-of-directors',
    'Colorado': 'https://manufacturersedge.com/',
    'Connecticut': 'https://www.connstep.org/our-team/',
    'Delaware': 'https://www.demep.org/',
    'Florida': 'https://www.floridamakes.com/about-us/our-team/staff',
    'Georgia': 'https://gamep.org/meet-the-gamep-team/',
    'Hawaii': 'https://www.htdc.org/our-team/',
    'Idaho': 'https://www.techhelp.org/staff/',
    'Illinois': 'https://www.imec.org/',
    'Indiana': 'https://mep.purdue.edu/about-us/staff/',
    'Iowa': 'https://www.ciras.iastate.edu/staff-directory/',
    'Kansas': 'https://www.wearekms.com/about-us/meet-the-team',
    'Kentucky': 'https://www.advantageky.org/who-we-are',
    'Louisiana': 'https://mepol.org/about-mepol',
    'Maine': 'https://mainemep.org/who-we-are/team/',
    'Maryland': 'https://mdmep.org/our-team/',
    'Massachusetts': 'https://massmep.org/our-team/',
    'Michigan': 'https://www.the-center.org/About-The-Center/Who-We-Are',
    'Minnesota': 'https://www.enterpriseminnesota.org/leadership-staff/',
    'Mississippi': 'https://mma-web.org/About-Us/Staff',
    'Missouri': 'https://www.missourienterprise.org/about/people/leadership-manufacturers-improvement-quality-efficiency-nist-mep/',
    'Montana': 'https://www.montana.edu/mmec/about/contact.html',
    'Nebraska': 'https://nemep.unl.edu/nebraska-mep/staff/',
    'Nevada': 'https://www.manufacturenevada.com/team-and-advisors',
    'New Hampshire': 'https://www.nhmep.org/',
    'New Jersey': 'https://www.njmep.org/',
    'New Mexico': 'https://newmexicomep.org/contact/',
    'New York': 'https://fuzehub.com/our-team/',
    'North Carolina': 'https://ncmep.org/about/',
    'North Dakota': 'https://www.impactdakota.com/about-us/staff/',
    'Ohio': 'https://www.manufacturingsuccess.org/team',
    'Oklahoma': 'https://www.okalliance.com/about/our-team/',
    'Oregon': 'https://omep.org/about-omep/our-people/',
    'Pennsylvania': 'https://pamep.org/about-us/',
    'Rhode Island': 'https://polarismep.org/about-polaris-mep/team/',
    'South Carolina': 'https://scmep.org/team/',
    'South Dakota': 'http://www.sdmanufacturing.com/aboutus/staff/',
    'Tennessee': 'https://cis.tennessee.edu/about-us/our-team-directory',
    'Texas': 'https://tmac.org/tmac-team/',
    'Utah': 'https://mep.utah.edu/team/',
    'Vermont': 'https://vmec.org/about/our-team/',
    'Virginia': 'https://genedge.org/who-we-are/our-team/',
    'Washington': 'https://www.impactwashington.org/leadership-team',
    'West Virginia': 'https://industrialextension.statler.wvu.edu/',
    'Wisconsin': 'https://wmep.org/about/staff/',
    'Wyoming': 'https://manufacturing-works.com/about-us/team/',
    'Puerto Rico': 'https://primexpr.org/about/',
}

def update_csv(input_file, output_file):
    """Update the CSV with staff page URLs"""
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Update rows with staff pages
    for row in rows:
        state = row['State']
        if state in staff_pages and not row.get('Staff Page', '').strip():
            row['Staff Page'] = staff_pages[state]
            print(f"Updated {state}: {staff_pages[state]}")

    # Write updated CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['State', 'Program Name (MEP Center)', 'Host Organization', 'Staff Page']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nUpdated CSV saved to: {output_file}")

    # Show remaining states
    remaining = []
    for row in rows:
        if not row.get('Staff Page', '').strip():
            remaining.append(row['State'])

    print(f"\nRemaining states without staff pages ({len(remaining)}):")
    for state in remaining:
        print(f"  - {state}")

if __name__ == "__main__":
    update_csv("state meps.csv", "state meps.csv")
