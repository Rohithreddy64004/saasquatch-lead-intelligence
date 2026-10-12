from pymongo.asynchronous.collection import AsyncCollection

from app.schemas import LeadInput
from app.services.leads import build_document


COMPANY_PREFIXES = [
    "Alder", "Blue Peak", "Brightpath", "Cairn", "Clearwater", "Copperline",
    "Daybreak", "Everwell", "Fieldnote", "Finch", "Foundry", "Foxglove",
    "Good Harbor", "Granite Row", "Greenlight", "Hearthside", "Highland",
    "Juniper", "Keystone", "Kindred", "Lighthouse", "Maple Street",
    "Meadowlark", "Meridian", "New Harbor", "Northwind", "Oakwell", "Openfield",
    "Orbit Grove", "Papertrail", "Pinecone", "Redwood", "Rivermark", "Rosewood",
    "Sagewell", "Silverline", "Stonecrop", "Summit Grove", "Three Oaks", "TrueNorth",
    "Valley Forge", "Waypoint", "Westward", "Wildwood", "Willowbend", "Windrow",
    "Yellowbrick", "Zephyr Lane",
]
INDUSTRIES = ["SaaS", "Software", "IT Services", "Healthcare Technology", "Logistics", "Financial Services"]
LOCATIONS = ["Austin, TX", "Denver, CO", "Raleigh, NC", "Portland, OR", "Madison, WI", "Tampa, FL", "Columbus, OH", "Boise, ID"]
CONTACTS = ["Alex Morgan", "Jordan Lee", "Taylor Reed", "Casey Brooks", "Riley Quinn", "Morgan Ellis", "Jamie Park", "Avery Chen"]
TITLES = ["Founder & CEO", "Chief Executive Officer", "Founder", "VP of Operations", "Managing Director", "Director of Partnerships", "Owner", "Head of Growth"]


async def seed_demo_data(collection: AsyncCollection) -> int:
    if await collection.count_documents({}):
        return 0
    documents = []
    for index, prefix in enumerate(COMPANY_PREFIXES):
        has_signal = index % 4 != 3
        missing_contact = index % 9 == 0
        record = LeadInput(
            company_name=f"{prefix} {['Systems', 'Collective', 'Works', 'Labs'][index % 4]}",
            industry=INDUSTRIES[index % len(INDUSTRIES)],
            location=LOCATIONS[index % len(LOCATIONS)],
            estimated_revenue=float((index % 12 + 1) * 1_250_000),
            employee_count=(index % 18 + 2) * 10,
            domain=f"{prefix.lower().replace(' ', '')}.example",
            contact_name=None if missing_contact else CONTACTS[index % len(CONTACTS)],
            contact_title=None if missing_contact else TITLES[index % len(TITLES)],
            contact_email=None if missing_contact else f"contact{index + 1}@example.invalid",
            growth_signal="Synthetic hiring signal for demonstration only." if has_signal else None,
            growth_signal_source="Synthetic demo record; not independently researched." if has_signal else None,
            source="Synthetic demo data",
            is_synthetic=True,
        )
        documents.append(build_document(record, saved=index in (2, 10, 21)))
    try:
        result = await collection.insert_many(documents, ordered=False)
        return len(result.inserted_ids)
    except Exception as exc:
        if exc.__class__.__name__ == "BulkWriteError":
            return 0
        raise