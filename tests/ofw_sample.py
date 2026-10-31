SAMPLE_SOURCE_SHA256 = "a" * 64

SAMPLE_PERSON_IDS = {
    "Parent Alpha": "person_mitchel_watson",
    "Parent Beta": "person_lindsay_alene_mcclean",
    "Child Delta": "person_sofia_rae_watson",
    "Third Party Gamma": "person_laura_watson",
}

SAMPLE_OFW_PAGES = [
    """Message Report
Generated: 07/11/2026 6:04 AM by Example User
Timezone: America/Vancouver
Date Range: 06/19/2024 — 01/30/2026
Contains: 2 selected messages
Order: Chronological (oldest first, most recent last)
Message 1 of 2

Sent: 06/19/2024 2:37 PM
From: Parent Alpha
To: Parent Beta (First Viewed: 06/20/2024 10:18 AM)
Subject: Testing

Current message only.

Sent: 06/18/2024 1:00 PM
From: Parent Beta
To: Parent Alpha (First Viewed: 06/18/2024 1:01 PM)
Subject: Older quoted message

Quoted thread content.
""",
    """Message 2 of 2

Sent: 01/30/2026 3:25 PM
From: Third Party Gamma
To: Parent Alpha (First Viewed: Never)
    Child Delta (First Viewed: 01/30/2026 3:26 PM)
Subject: Test attachment

The second message.

See Attachments: example.pdf (1.6 MB),
photo, edited. JPG (200 KB)
    """,
]

SAMPLE_OFW_EDMONTON_PAGES = [
    page.replace("Timezone: America/Vancouver", "Timezone: America/Edmonton")
    .replace("06/19/2024 2:37 PM", "06/19/2024 3:37 PM")
    .replace("06/20/2024 10:18 AM", "06/20/2024 11:18 AM")
    .replace("01/30/2026 3:25 PM", "01/30/2026 4:25 PM")
    .replace("01/30/2026 3:26 PM", "01/30/2026 4:26 PM")
    for page in SAMPLE_OFW_PAGES
]
