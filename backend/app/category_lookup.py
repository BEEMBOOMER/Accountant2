"""Curated deterministic categories and Australian merchant keyword rules.

The order is significant for keyword rules. More specific descriptions appear
before broader brands (for example, UBER EATS before UBER).
"""

from __future__ import annotations


CURATED_CATEGORIES = [
    "Housing",
    "Groceries",
    "Eating Out",
    "Transport",
    "Phone & Subscriptions",
    "Utilities",
    "Health",
    "Personal Care",
    "Education",
    "Shopping",
    "Social",
    "Insurance",
    "Friends & Family",
    "Income",
    "Roommate Settlement",
    "Miscellaneous",
]


CURATED_RULES = [
    # Housing. RENT precedes personal names so rent paid to a housemate stays housing.
    ("keyword", "RENT", "Housing"),
    ("keyword", "RAY WHITE", "Housing"),
    ("keyword", "LJ HOOKER", "Housing"),
    ("keyword", "HARCOURTS", "Housing"),
    ("keyword", "REAL ESTATE", "Housing"),
    ("keyword", "BODY CORPORATE", "Housing"),
    ("keyword", "IKEA", "Housing"),
    ("keyword", "BUNNINGS", "Housing"),

    # Groceries.
    ("keyword", "WOOLWORTHS", "Groceries"),
    ("keyword", "COLES", "Groceries"),
    ("keyword", "ALDI", "Groceries"),
    ("keyword", "COSTCO", "Groceries"),
    ("keyword", "HARRIS FARM", "Groceries"),
    ("keyword", "FRESH & SAVE", "Groceries"),
    ("keyword", "FOODWORKS", "Groceries"),
    ("keyword", "FOODLAND", "Groceries"),
    ("keyword", "DRAKES", "Groceries"),
    ("keyword", "SPUDSHED", "Groceries"),
    ("keyword", "IGA", "Groceries"),
    # The supplied CommBank export uses this memo for a self-transfer made to
    # pay for groceries; the broader word "grocery" is intentionally avoided.
    ("keyword", "APP GROCERY", "Groceries"),

    # Dining and delivery. These must precede UBER and education keywords.
    ("keyword", "UBER EATS", "Eating Out"),
    ("keyword", "DOORDASH", "Eating Out"),
    ("keyword", "MENULOG", "Eating Out"),
    ("keyword", "DELIVEROO", "Eating Out"),
    ("keyword", "KEETA", "Eating Out"),
    ("keyword", "MCDONALD", "Eating Out"),
    ("keyword", "HUNGRY JACK", "Eating Out"),
    # This spelling is the merchant string present in the CommBank export.
    ("keyword", "HJS BEAK HOUSE", "Eating Out"),
    ("keyword", "RED ROOSTER", "Eating Out"),
    ("keyword", "ORIGIN KEBABS", "Eating Out"),
    ("keyword", "BOMBAY DHABA", "Eating Out"),
    ("keyword", "SOUTH SEOUL", "Eating Out"),
    ("keyword", "GLORIA JEAN", "Eating Out"),
    ("keyword", "THE COFFEE CLUB", "Eating Out"),
    ("keyword", "BOOST JUICE", "Eating Out"),
    ("keyword", "DOMINO", "Eating Out"),
    ("keyword", "GUZMAN", "Eating Out"),
    ("keyword", "ZAMBRERO", "Eating Out"),
    ("keyword", "STARBUCKS", "Eating Out"),
    ("keyword", "GRILL'D", "Eating Out"),
    ("keyword", "NANDO", "Eating Out"),
    ("keyword", "OPORTO", "Eating Out"),
    ("keyword", "SUBWAY", "Eating Out"),
    ("keyword", "SUSHI", "Eating Out"),
    ("keyword", "KFC", "Eating Out"),
    ("keyword", "GYG", "Eating Out"),

    # Phone, internet, software and entertainment subscriptions. AMAZON PRIME
    # precedes the broader AMAZON shopping rule below.
    ("keyword", "OPENAI", "Phone & Subscriptions"),
    ("keyword", "CHATGPT", "Phone & Subscriptions"),
    ("keyword", "YOUTUBE", "Phone & Subscriptions"),
    ("keyword", "GOOGLE ONE", "Phone & Subscriptions"),
    ("keyword", "GOOGLE PLAY", "Phone & Subscriptions"),
    ("keyword", "GOOGLE", "Phone & Subscriptions"),
    ("keyword", "NETFLIX", "Phone & Subscriptions"),
    ("keyword", "SPOTIFY", "Phone & Subscriptions"),
    ("keyword", "LEBARA", "Phone & Subscriptions"),
    ("keyword", "VODAFONE", "Phone & Subscriptions"),
    ("keyword", "TELSTRA", "Phone & Subscriptions"),
    ("keyword", "OPTUS", "Phone & Subscriptions"),
    ("keyword", "IINET", "Phone & Subscriptions"),
    ("keyword", "AUSSIE BROADBAND", "Phone & Subscriptions"),
    ("keyword", "AMAZON PRIME", "Phone & Subscriptions"),
    ("keyword", "DISNEY PLUS", "Phone & Subscriptions"),
    ("keyword", "DISNEY+", "Phone & Subscriptions"),
    ("keyword", "APPLE.COM/BILL", "Phone & Subscriptions"),
    ("keyword", "MICROSOFT", "Phone & Subscriptions"),
    ("keyword", "ADOBE", "Phone & Subscriptions"),
    ("keyword", "DROPBOX", "Phone & Subscriptions"),
    ("keyword", "AUDIBLE", "Phone & Subscriptions"),
    ("keyword", "CANVA", "Phone & Subscriptions"),
    ("keyword", "STAN", "Phone & Subscriptions"),
    ("keyword", "BINGE", "Phone & Subscriptions"),
    ("keyword", "KAYO", "Phone & Subscriptions"),
    # Memo labels in the supplied CommBank export, corroborated by the
    # labelled Expenses sheet. Keep these phrases specific: a bare transfer
    # recipient or a generic word such as "work" remains for manual review.
    ("keyword", "BRAIN AND BOTS", "Education"),

    # Transport and travel.
    ("keyword", "TRANSLINK", "Transport"),
    ("keyword", "13CABS", "Transport"),
    ("keyword", "CABCHARGE", "Transport"),
    ("keyword", "WILSON PARKING", "Transport"),
    ("keyword", "VIRGIN AUSTRALIA", "Transport"),
    ("keyword", "7-ELEVEN FUEL", "Transport"),
    # Bank export strings omit the separator in this merchant name; DIDI on
    # its own cannot match DIDIMOBILITY under token-aware matching.
    ("keyword", "DIDIMOBILITY", "Transport"),
    ("keyword", "APP TRANSPORT", "Transport"),
    ("keyword", "ENERGY AUSTRALIA", "Utilities"),
    ("keyword", "DIDI", "Transport"),
    ("keyword", "UBER", "Transport"),
    ("keyword", "MYKI", "Transport"),
    ("keyword", "OPAL", "Transport"),
    ("keyword", "LINKT", "Transport"),
    ("keyword", "AMPOL", "Transport"),
    ("keyword", "CALTEX", "Transport"),
    ("keyword", "SHELL", "Transport"),
    ("keyword", "QANTAS", "Transport"),
    ("keyword", "JETSTAR", "Transport"),
    ("keyword", "BP", "Transport"),

    # Household utilities.
    ("keyword", "ORIGIN ENERGY", "Utilities"),
    ("keyword", "ENERGYAUSTRALIA", "Utilities"),
    ("keyword", "URBAN UTILITIES", "Utilities"),
    ("keyword", "UNITYWATER", "Utilities"),
    ("keyword", "AGL", "Utilities"),
    ("keyword", "ERGON", "Utilities"),
    ("keyword", "SYNERGY", "Utilities"),
    ("keyword", "AUSNET", "Utilities"),
    ("keyword", "ELECTRIC BILL", "Utilities"),
    ("keyword", "2ELEC BILLS", "Utilities"),
    ("keyword", "WIFI BILL", "Utilities"),

    # Health.
    ("keyword", "CHEMIST WAREHOUSE", "Health"),
    ("keyword", "PRICELINE PHARMACY", "Health"),
    ("keyword", "TERRYWHITE", "Health"),
    ("keyword", "PATHOLOGY", "Health"),
    ("keyword", "PHARMACY", "Health"),
    ("keyword", "MEDICAL", "Health"),
    ("keyword", "DENTAL", "Health"),
    ("keyword", "AMCAL", "Health"),
    ("keyword", "CHEMPRO", "Health"),
    ("keyword", "CHEMPRQPS", "Health"),
    ("keyword", "SNAPFITNESS", "Health"),
    ("keyword", "SNAPFITNE", "Health"),
    ("keyword", "HOLLAND PARK FITNESS", "Health"),

    # The labelled June expense records this merchant as a haircut.
    ("keyword", "BARBER TEMPLE", "Personal Care"),

    # Education. Dining keywords appear first, so QUT Sushi remains Eating Out.
    ("keyword", "GRIFFITH UNIVERSITY", "Education"),
    ("keyword", "OFFICEWORKS", "Education"),
    ("keyword", "COURSERA", "Education"),
    ("keyword", "UNIVERSITY", "Education"),
    ("keyword", "RUBRIC", "Education"),
    ("keyword", "UDEMY", "Education"),
    ("keyword", "TAFE", "Education"),
    ("keyword", "QUT", "Education"),

    # General retail.
    ("keyword", "JB HI-FI", "Shopping"),
    ("keyword", "THE ICONIC", "Shopping"),
    ("keyword", "MINISO", "Shopping"),
    ("keyword", "KMART", "Shopping"),
    ("keyword", "BIG W", "Shopping"),
    ("keyword", "TARGET", "Shopping"),
    ("keyword", "AMAZON", "Shopping"),
    ("keyword", "EBAY", "Shopping"),
    ("keyword", "MYER", "Shopping"),
    ("keyword", "CATCH", "Shopping"),
    ("keyword", "TEMU", "Shopping"),
    ("keyword", "SHEIN", "Shopping"),
    # "Woolies" occurs in transfer memos in the supplied CommBank sample.
    ("keyword", "WOOLIES", "Groceries"),

    # Leisure and alcohol retailers.
    ("keyword", "EVENT CINEMAS", "Social"),
    ("keyword", "TICKETMASTER", "Social"),
    ("keyword", "TICKETEK", "Social"),
    ("keyword", "DAN MURPHY", "Social"),
    ("keyword", "LIQUORLAND", "Social"),
    ("keyword", "HOYTS", "Social"),
    ("keyword", "BWS", "Social"),

    # Insurance.
    ("keyword", "MEDIBANK", "Insurance"),
    ("keyword", "ALLIANZ", "Insurance"),
    ("keyword", "YOUI", "Insurance"),
    ("keyword", "AAMI", "Insurance"),
    ("keyword", "NRMA", "Insurance"),
    ("keyword", "RACQ", "Insurance"),
    ("keyword", "BUPA", "Insurance"),

    # People explicitly identified by the user. Token-aware keyword matching is
    # especially important for the short name PO.
    ("keyword", "DHANUK", "Friends & Family"),
    ("keyword", "D DE SILVA", "Friends & Family"),
    ("keyword", "M JALAL AHMED", "Friends & Family"),
    ("keyword", "MAHITH", "Friends & Family"),
    ("keyword", "MALIK", "Friends & Family"),
    ("keyword", "NIDHI", "Friends & Family"),
    ("keyword", "PO", "Friends & Family"),

    # Clear income descriptions. Ambiguous remittances remain for manual review.
    ("keyword", "SALARY", "Income"),
    ("keyword", "PAYROLL", "Income"),
    ("keyword", "INTEREST PAID", "Income"),
    ("keyword", "WAGES", "Income"),
]
