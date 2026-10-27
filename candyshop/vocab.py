"""Domain vocabulary: the "meaning" behind the fake data.

Everything here is hand-written so shops, products, leads and tickets read like a real
candy-shop SaaS business instead of lorem ipsum.
"""
from __future__ import annotations

import math
from datetime import date

# --------------------------------------------------------------------------- geography
# (city, state, tz, zip prefix)
CITIES = [
    ("Portland", "OR", "America/Los_Angeles", "972"), ("Seattle", "WA", "America/Los_Angeles", "981"),
    ("San Diego", "CA", "America/Los_Angeles", "921"), ("Sacramento", "CA", "America/Los_Angeles", "958"),
    ("Santa Cruz", "CA", "America/Los_Angeles", "950"), ("Las Vegas", "NV", "America/Los_Angeles", "891"),
    ("Boise", "ID", "America/Boise", "837"), ("Bend", "OR", "America/Los_Angeles", "977"),
    ("Phoenix", "AZ", "America/Phoenix", "850"), ("Scottsdale", "AZ", "America/Phoenix", "852"),
    ("Denver", "CO", "America/Denver", "802"), ("Colorado Springs", "CO", "America/Denver", "809"),
    ("Salt Lake City", "UT", "America/Denver", "841"), ("Albuquerque", "NM", "America/Denver", "871"),
    ("Austin", "TX", "America/Chicago", "787"), ("Dallas", "TX", "America/Chicago", "752"),
    ("Houston", "TX", "America/Chicago", "770"), ("San Antonio", "TX", "America/Chicago", "782"),
    ("Fredericksburg", "TX", "America/Chicago", "786"), ("Oklahoma City", "OK", "America/Chicago", "731"),
    ("Kansas City", "MO", "America/Chicago", "641"), ("St. Louis", "MO", "America/Chicago", "631"),
    ("Omaha", "NE", "America/Chicago", "681"), ("Minneapolis", "MN", "America/Chicago", "554"),
    ("Madison", "WI", "America/Chicago", "537"), ("Milwaukee", "WI", "America/Chicago", "532"),
    ("Chicago", "IL", "America/Chicago", "606"), ("Naperville", "IL", "America/Chicago", "605"),
    ("Indianapolis", "IN", "America/Indiana/Indianapolis", "462"), ("Columbus", "OH", "America/New_York", "432"),
    ("Cleveland", "OH", "America/New_York", "441"), ("Cincinnati", "OH", "America/New_York", "452"),
    ("Detroit", "MI", "America/Detroit", "482"), ("Traverse City", "MI", "America/Detroit", "496"),
    ("Louisville", "KY", "America/New_York", "402"), ("Nashville", "TN", "America/Chicago", "372"),
    ("Gatlinburg", "TN", "America/New_York", "377"), ("Memphis", "TN", "America/Chicago", "381"),
    ("Atlanta", "GA", "America/New_York", "303"), ("Savannah", "GA", "America/New_York", "314"),
    ("Charleston", "SC", "America/New_York", "294"), ("Charlotte", "NC", "America/New_York", "282"),
    ("Asheville", "NC", "America/New_York", "288"), ("Raleigh", "NC", "America/New_York", "276"),
    ("Richmond", "VA", "America/New_York", "232"), ("Virginia Beach", "VA", "America/New_York", "234"),
    ("Baltimore", "MD", "America/New_York", "212"), ("Philadelphia", "PA", "America/New_York", "191"),
    ("Pittsburgh", "PA", "America/New_York", "152"), ("Lancaster", "PA", "America/New_York", "176"),
    ("Hershey", "PA", "America/New_York", "170"), ("Buffalo", "NY", "America/New_York", "142"),
    ("Brooklyn", "NY", "America/New_York", "112"), ("Albany", "NY", "America/New_York", "122"),
    ("Providence", "RI", "America/New_York", "029"), ("Boston", "MA", "America/New_York", "021"),
    ("Burlington", "VT", "America/New_York", "054"), ("Portland", "ME", "America/New_York", "041"),
    ("Orlando", "FL", "America/New_York", "328"), ("Tampa", "FL", "America/New_York", "336"),
    ("Miami", "FL", "America/New_York", "331"), ("New Orleans", "LA", "America/Chicago", "701"),
    ("Birmingham", "AL", "America/Chicago", "352"), ("Anchorage", "AK", "America/Anchorage", "995"),
]
# city weights: tourist / foodie towns skew a little higher for candy
CITY_WEIGHTS = [
    2.0 if c[0] in {"Gatlinburg", "Hershey", "Savannah", "Charleston", "Santa Cruz", "Traverse City",
                    "Fredericksburg", "Asheville", "Lancaster", "Burlington", "Bend", "New Orleans"}
    else 1.0 for c in CITIES
]

STATE_NAMES = {
    "AK": "Alaska", "AL": "Alabama", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "FL": "Florida",
    "GA": "Georgia", "IA": "Iowa", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "KY": "Kentucky",
    "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "NC": "North Carolina", "NE": "Nebraska", "NM": "New Mexico",
    "NV": "Nevada", "NY": "New York", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VA": "Virginia", "VT": "Vermont", "WA": "Washington", "WI": "Wisconsin",
}
REGION = {}
for _s in "CT ME MA NH RI VT NJ NY PA".split():
    REGION[_s] = "Northeast"
for _s in "DE DC FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX".split():
    REGION[_s] = "South"
for _s in "IL IN MI OH WI IA KS MN MO NE ND SD".split():
    REGION[_s] = "Midwest"
for _s in "AK AZ CA CO HI ID MT NV NM OR UT WA WY".split():
    REGION[_s] = "West"

# state sales tax applied to SaaS subscriptions (only a few states tax software)
SAAS_TAX = {"NY": 0.04, "TX": 0.0625, "WA": 0.065, "PA": 0.06, "IL": 0.0625, "OH": 0.0575, "TN": 0.07}

# --------------------------------------------------------------------------- shops
SHOP_TYPES = [
    ("Retail candy store", 0.36), ("Bulk & nostalgic candy", 0.17), ("Chocolatier", 0.12),
    ("Candy & gift shop", 0.12), ("Ice cream & candy parlor", 0.08), ("Online-first candy shop", 0.08),
    ("Fudge & confection kitchen", 0.07),
]
SWEET_WORDS = [
    "Sugar Plum", "Sweet Tooth", "Gumdrop", "Jellybean", "Lollipop", "Caramel", "Honeycomb", "Peppermint",
    "Rock Candy", "Butterscotch", "Licorice", "Marshmallow", "Toffee", "Nougat", "Bonbon", "Taffy",
    "Fudge", "Cocoa", "Cherry Drop", "Maple Leaf", "Candy Cane", "Spun Sugar", "Sprinkle", "Rainbow Swirl",
    "Golden Ticket", "Old Fashioned", "Main Street", "Cinnamon Stick", "Peanut Brittle", "Wintergreen",
    "Sherbet", "Gummy Bear", "Cotton Candy", "Sour Apple",
    "Praline", "Truffle", "Butter Mint", "Candy Apple", "Bubblegum", "Sweet Pea", "Hot Cocoa",
]
SHOP_SUFFIXES = [
    "Sweets", "Candy Co.", "Confections", "Candy Shoppe", "Sweet Shop", "Candy Emporium", "Chocolates",
    "Candy Kitchen", "Treats", "Candy Barn", "Candy Corner", "Candy Jar", "Candy Cottage", "Candy Factory",
]
LEGAL_SUFFIXES = ["LLC", "Inc.", "Co.", "LLC", "LLC", ""]
FREE_MAIL = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "aol.com", "hotmail.com"]

# --------------------------------------------------------------------------- plans
PLANS = {
    "starter": dict(name="Starter", monthly=4900, annual=49000, lead_limit=150, campaign_limit=4, seat_limit=3),
    "growth": dict(name="Growth", monthly=14900, annual=149000, lead_limit=600, campaign_limit=20, seat_limit=8),
    "pro": dict(name="Pro", monthly=39900, annual=399000, lead_limit=3000, campaign_limit=999, seat_limit=25),
}
PLAN_ORDER = ["starter", "growth", "pro"]

# --------------------------------------------------------------------------- products
# (sku, name, category, list_price, season months or None)
PRODUCTS = [
    ("GUM-001", "Sour Gummy Worms 1lb", "gummies", 8.99, None), ("GUM-002", "Gummy Bears Assorted 1lb", "gummies", 7.99, None),
    ("GUM-003", "Peach Rings 1lb", "gummies", 8.49, None), ("GUM-004", "Gummy Sharks 1lb", "gummies", 8.49, None),
    ("GUM-005", "Cola Bottles 1lb", "gummies", 7.99, None),
    ("CHO-001", "Dark Chocolate Sea Salt Caramels 8oz", "chocolate", 12.99, None),
    ("CHO-002", "Milk Chocolate Pretzels 1lb", "chocolate", 11.99, None),
    ("CHO-003", "Chocolate Truffle Box 12pc", "chocolate", 24.99, None),
    ("CHO-004", "Chocolate Covered Cherries 8oz", "chocolate", 10.99, None),
    ("CHO-005", "Peanut Butter Cups 1lb", "chocolate", 11.49, None),
    ("CHO-006", "Toffee Almond Bark 1lb", "chocolate", 13.99, None),
    ("HRD-001", "Butterscotch Discs 1lb", "hard_candy", 6.99, None), ("HRD-002", "Cinnamon Hots 1lb", "hard_candy", 6.99, None),
    ("HRD-003", "Root Beer Barrels 1lb", "hard_candy", 6.49, None), ("HRD-004", "Rock Candy Sticks 12ct", "hard_candy", 9.99, None),
    ("HRD-005", "Swirl Lollipops 24ct", "lollipops", 14.99, None), ("HRD-006", "Peppermint Starlight Mints 1lb", "hard_candy", 6.99, None),
    ("SOR-001", "Sour Belts 1lb", "sour", 8.99, None), ("SOR-002", "Sour Watermelon Slices 1lb", "sour", 8.49, None),
    ("SOR-003", "Extreme Sour Candies 1lb", "sour", 9.49, None),
    ("LIC-001", "Black Licorice Twists 1lb", "licorice", 7.99, None), ("LIC-002", "Red Licorice Ropes 1lb", "licorice", 7.99, None),
    ("LIC-003", "Licorice Allsorts 1lb", "licorice", 8.99, None),
    ("RET-001", "Candy Buttons Sheets 12ct", "retro", 6.99, None), ("RET-002", "Wax Bottles 20ct", "retro", 9.99, None),
    ("RET-003", "Banana Taffy Chews 1lb", "retro", 7.49, None), ("RET-004", "Retro Candy Necklaces 12ct", "retro", 8.99, None),
    ("RET-005", "Candy Dot Strips 24ct", "retro", 9.49, None),
    ("TAF-001", "Saltwater Taffy Assorted 1lb", "taffy_fudge", 10.99, None), ("TAF-002", "Chocolate Walnut Fudge 8oz", "taffy_fudge", 9.99, None),
    ("TAF-003", "Maple Fudge 8oz", "taffy_fudge", 9.99, None), ("TAF-004", "Peanut Brittle 8oz", "taffy_fudge", 8.99, None),
    ("SFR-001", "Sugar-Free Gummy Bears 8oz", "sugar_free", 7.99, None), ("SFR-002", "Sugar-Free Peppermints 8oz", "sugar_free", 6.49, None),
    ("SFR-003", "Sugar-Free Chocolate Bar", "sugar_free", 4.99, None),
    ("SEA-001", "Candy Corn 1lb", "seasonal", 6.49, (9, 10)), ("SEA-002", "Halloween Treat Bags 50ct", "seasonal", 19.99, (9, 10)),
    ("SEA-003", "Pumpkin Spice Caramels 8oz", "seasonal", 9.99, (9, 10, 11)),
    ("SEA-004", "Heart-Shaped Chocolate Box", "seasonal", 21.99, (1, 2)), ("SEA-005", "Sweetheart Message Candies 1lb", "seasonal", 7.49, (1, 2)),
    ("SEA-006", "Marshmallow Chicks 12ct", "seasonal", 7.99, (3, 4)), ("SEA-007", "Easter Jelly Beans 1lb", "seasonal", 7.99, (3, 4)),
    ("SEA-008", "Red White & Blue Rock Candy", "seasonal", 8.99, (6, 7)),
    ("SEA-009", "Candy Canes 24ct", "seasonal", 6.99, (11, 12)), ("SEA-010", "Holiday Peppermint Bark 1lb", "seasonal", 15.99, (11, 12)),
    ("SEA-011", "Gingerbread Gummies 1lb", "seasonal", 8.99, (11, 12)), ("SEA-012", "Graduation Chocolate Coins 24ct", "seasonal", 12.99, (5, 6)),
    ("SEA-013", "Back-to-School Lollipop Bulk 100ct", "seasonal", 17.99, (8, 9)),
    ("GFT-001", "Birthday Candy Gift Box", "gift_box", 29.99, None), ("GFT-002", "Wedding Favor Tins 24ct", "gift_box", 54.99, None),
    ("GFT-003", "Corporate Thank-You Box", "gift_box", 39.99, None), ("GFT-004", "Get Well Candy Basket", "gift_box", 34.99, None),
    ("GFT-005", "Custom Message Candy Jar", "gift_box", 24.99, None),
]
CATEGORY_BASE_WEIGHT = {
    "gummies": 1.4, "chocolate": 1.5, "hard_candy": 0.8, "lollipops": 0.9, "sour": 0.9, "licorice": 0.6,
    "retro": 0.8, "taffy_fudge": 0.8, "sugar_free": 0.4, "seasonal": 1.3, "gift_box": 1.0,
}

# --------------------------------------------------------------------------- seasons / holidays
# (name, month, day, ramp-up width days, height) -- demand builds *before* the holiday
HOLIDAYS = [
    ("Valentine's Day", 2, 14, 14, 0.8), ("Easter", 4, 5, 12, 0.5), ("Mother's Day", 5, 10, 8, 0.3),
    ("Graduation Season", 5, 28, 10, 0.3), ("4th of July", 7, 4, 8, 0.25), ("Back to School", 8, 25, 14, 0.4),
    ("Halloween", 10, 31, 18, 1.25), ("Thanksgiving", 11, 26, 8, 0.25), ("Holiday Season", 12, 22, 20, 1.0),
]


def season_factor(d: date) -> float:
    """Relative retail/candy demand on a date (≈0.75 baseline, peaks before holidays)."""
    f = 0.75
    for _n, m, day, width, height in HOLIDAYS:
        for yr in (d.year - 1, d.year, d.year + 1):
            delta = (date(yr, m, day) - d).days  # >0 => holiday is ahead
            w = width if delta >= 0 else width / 3
            f += height * math.exp(-((delta / w) ** 2))
    return f


def upcoming_holiday(d: date, horizon: int = 35):
    best = None
    for n, m, day, *_ in HOLIDAYS:
        for yr in (d.year, d.year + 1):
            delta = (date(yr, m, day) - d).days
            if 0 <= delta <= horizon and (best is None or delta < best[1]):
                best = (n, delta)
    return best


def campaign_season_factor(d: date) -> float:
    """Shops launch campaigns 1-4 weeks before a holiday."""
    f = 0.45
    for _n, m, day, _w, height in HOLIDAYS:
        for yr in (d.year, d.year + 1):
            delta = (date(yr, m, day) - d).days
            if 0 <= delta <= 40:
                f += (height + 0.3) * math.exp(-(((delta - 18) / 10) ** 2))
    return f


# --------------------------------------------------------------------------- app: leads
# lead_type -> (weight, order_type, median order $, win prob, [month multipliers 1..12])
def _m(**kw):
    base = [1.0] * 12
    for k, v in kw.items():
        base[int(k[1:]) - 1] = v
    return base


LEAD_TYPES = {
    "school_pta": dict(w=1.4, order_type="bulk", value=380, win=0.30,
                       months=_m(m8=2.6, m9=3.0, m10=1.6, m11=1.3, m12=1.2, m1=0.6, m6=0.3, m7=0.3)),
    "corporate_office": dict(w=1.3, order_type="gift_box", value=520, win=0.22,
                             months=_m(m11=2.6, m12=3.2, m1=0.9, m2=1.0, m7=0.7)),
    "wedding_planner": dict(w=1.0, order_type="event", value=640, win=0.28,
                            months=_m(m4=1.6, m5=2.4, m6=2.6, m7=2.0, m8=2.0, m9=2.4, m10=2.0, m1=0.4, m2=0.4)),
    "church_nonprofit": dict(w=0.9, order_type="bulk", value=290, win=0.33,
                             months=_m(m10=2.2, m11=1.8, m12=2.4, m3=1.4, m4=1.8)),
    "birthday_party": dict(w=1.5, order_type="event", value=160, win=0.38, months=_m(m6=1.5, m7=1.5)),
    "hotel_restaurant": dict(w=0.7, order_type="wholesale", value=870, win=0.15,
                             months=_m(m5=1.3, m6=1.5, m7=1.6, m12=1.4)),
    "sports_team": dict(w=0.8, order_type="bulk", value=240, win=0.30, months=_m(m3=1.5, m4=1.7, m5=1.7, m9=1.4)),
    "realtor": dict(w=0.5, order_type="gift_box", value=310, win=0.20, months=_m(m4=1.4, m5=1.6, m6=1.6, m12=1.4)),
    "festival_vendor": dict(w=0.6, order_type="wholesale", value=1150, win=0.18,
                            months=_m(m6=1.8, m7=1.8, m8=1.6, m9=1.6, m10=2.0, m12=1.5, m1=0.3, m2=0.3)),
}
LEAD_SOURCES = [("local_search", 0.34), ("event_calendar", 0.18), ("csv_import", 0.14), ("referral", 0.12),
                ("website_form", 0.16), ("social_dm", 0.06)]
MASCOTS = ["Tigers", "Lions", "Bulldogs", "Hawks", "Rockets", "Mustangs", "Panthers", "Wildcats", "Eagles", "Comets"]
WORDS_BIZ = ["Summit", "Harbor", "Maple", "Brightside", "Cornerstone", "Willow", "Riverbend", "Oakridge", "Lakeview", "Pioneer"]
BIZ_KINDS = ["Law Office", "Dental Group", "Insurance Partners", "Accounting", "Tech Solutions", "Realty Group",
             "Family Medicine", "Architects", "Credit Union", "Engineering"]
PARTY_TYPES = ["Birthday Party", "Baby Shower", "Retirement Party", "Reunion", "Graduation Party"]

# --------------------------------------------------------------------------- app: campaigns
CAMPAIGN_OFFERS = ["Bulk Bag Specials", "Gift Box Preorders", "Fundraiser Packs", "Weekend Sweet Deals",
                   "New Arrivals", "Loyalty Club Perk", "Party Favor Bundles", "Taste-Test Giveaway"]
CAMPAIGN_CHANNELS = [("email", 0.55), ("sms", 0.28), ("social", 0.12), ("direct_mail", 0.05)]
POS_INTEGRATIONS = ["square", "shopify", "clover", "lightspeed", "toast", "none"]
CHURN_REASONS = [("too_expensive", 0.20), ("not_enough_leads", 0.22), ("closing_shop", 0.12),
                 ("switched_to_competitor", 0.14), ("seasonal_pause", 0.12), ("missing_pos_integration", 0.10),
                 ("no_time_to_use", 0.10)]

# --------------------------------------------------------------------------- crm
SALES_REPS = ["Marcus Bell", "Priya Nair", "Dana Whitfield", "Luis Ortega", "Hannah Cho", "Tyrell Jackson"]
CRM_SOURCES = {  # name: (weight, conversion probability, median days to convert, plan skew)
    "Cold Outreach": (0.29, 0.20, 36), "Inbound Web": (0.20, 0.40, 18), "Trade Show": (0.13, 0.50, 24),
    "Webinar": (0.12, 0.47, 20), "Referral": (0.09, 0.62, 12), "Partner - Distributor": (0.09, 0.45, 28),
    "Paid Social": (0.08, 0.27, 16),
}
CRM_JOB_TITLES = [("Owner", 0.5), ("Co-Owner", 0.1), ("General Manager", 0.14), ("Store Manager", 0.12),
                  ("Marketing Manager", 0.06), ("Buyer", 0.05), ("Operations Manager", 0.03)]
NICKNAMES = {"Michael": "Mike", "Jennifer": "Jen", "Robert": "Bob", "William": "Bill", "Elizabeth": "Liz",
             "Katherine": "Kate", "Christopher": "Chris", "Jessica": "Jess", "Daniel": "Dan", "Matthew": "Matt",
             "Richard": "Rick", "Patricia": "Pat", "Samantha": "Sam", "Nicholas": "Nick", "Rebecca": "Becky"}

# --------------------------------------------------------------------------- support
AGENTS = [("Sofia Ramirez", "tier1"), ("Jonah Park", "tier1"), ("Amara Okafor", "tier1"),
          ("Ethan Brooks", "tier2"), ("Mei Lin", "tier2"), ("Carla Dominguez", "billing"),
          ("Owen Fitzgerald", "billing"), ("Nadia Haddad", "tier2")]

INCIDENTS = [  # (date, area, title)
    (date(2025, 11, 18), "campaigns", "SMS delivery delays on carrier route"),
    (date(2026, 3, 12), "campaigns", "Email sending queue backlog"),
    (date(2026, 8, 4), "lead_finder", "Lead Finder map results not loading"),
]

AREA_WEIGHTS = {"onboarding": 0.14, "lead_finder": 0.22, "campaigns": 0.20, "orders": 0.13,
                "integrations": 0.11, "billing": 0.10, "reports": 0.10}

# subject, description; placeholders: {city} {lead_type} {pos} {campaign} {n} {month} {plan}
TICKET_TEMPLATES = {
    "onboarding": [
        ("How do I set up my shop profile?", "Just signed up for SweetReach. Where do I enter our shop hours, delivery radius and the kinds of candy we specialize in so the lead suggestions make sense?"),
        ("Can't invite my store manager", "I tried adding my store manager as a user but the invite email never arrived. Her address is correct. We are on the {plan} plan."),
        ("Import my existing customer list?", "We have about {n} past customers in a spreadsheet. Is there a way to bring them into SweetReach so we don't re-market to people who already buy from us?"),
        ("Which plan is right for a small shop?", "We are a small candy shop in {city}. I can't tell whether {plan} gives us enough lead credits for the holiday season. Can someone walk me through it?"),
        ("Need help with first campaign", "I'm ready to send my first campaign but I'm nervous about the audience settings. Can someone review it before it goes out?"),
        ("Trial ends soon, can I extend?", "Our trial ends this week and I haven't had time to test the Lead Finder. Could the trial be extended a few days?"),
    ],
    "lead_finder": [
        ("No {lead_type} leads showing for {city}", "Lead Finder returns zero {lead_type} leads for {city} even though I know there are several in the area. My radius is set to 25 miles."),
        ("Lead scores look wrong", "Leads I would never close are scored 90+, and a local {lead_type} that already ordered from us shows a score of 20. How is the score calculated?"),
        ("Duplicate leads appearing", "I'm seeing the same {lead_type} listed three times with slightly different names. Can these be merged?"),
        ("Can't export leads to CSV", "The export button on my leads list spins forever when I select more than {n} leads."),
        ("Lead contact info is out of date", "Several leads have phone numbers that are disconnected. Is there a way to flag bad data so it gets corrected?"),
        ("How do I filter leads by event date?", "I want to see only wedding and party leads with events in {month}. I don't see a date filter on the Lead Finder."),
        ("Leads from the wrong state", "We're in {city} but I keep getting leads from the next state over. Is my service area saved correctly?"),
    ],
    "campaigns": [
        ("Campaign emails going to spam", "Customers tell us our '{campaign}' email landed in their spam folder. Open rate was far below normal."),
        ("SMS campaign stuck on 'sending'", "My text campaign has been stuck on sending for over an hour. The audience is {n} people."),
        ("Unsubscribe link missing in template", "The seasonal template I picked doesn't show an unsubscribe link in the preview. Is that required?"),
        ("Can't schedule campaign for next week", "The scheduler won't let me pick a date more than 3 days out for the {campaign} campaign."),
        ("Wrong audience size", "My audience says {n} contacts but I only imported about half that. I think duplicates are being counted."),
        ("Clicks not matching my orders", "Report shows lots of clicks on '{campaign}' but zero attributed orders, and I know at least a few people ordered."),
        ("Can I A/B test subject lines?", "Is there a way to test two subject lines for the {campaign} email before sending to everyone?"),
    ],
    "orders": [
        ("Order total doesn't add up", "A bulk order for a {lead_type} shows a subtotal that's off by about $40 compared with what I quoted. Discount seems to be applied twice."),
        ("Can't mark order as fulfilled", "The Fulfill button is greyed out on several orders from last week."),
        ("Refund didn't update inventory", "I refunded an order but the candy didn't go back into stock counts."),
        ("Order attributed to wrong campaign", "An order from a {lead_type} is credited to the wrong campaign in the report."),
        ("Need to split one order into two pickups", "A {lead_type} wants half their order now and half before their event. Can an order be split?"),
        ("Missing items on order confirmation", "The confirmation email for a gift box order leaves off two of the items."),
    ],
    "integrations": [
        ("{pos} sync is failing", "Our {pos} integration shows 'connection error' and inventory hasn't synced since yesterday."),
        ("Can SweetReach connect to {pos}?", "We just moved to {pos}. Is there an integration so sales flow into SweetReach automatically?"),
        ("Products imported twice from {pos}", "After connecting {pos} every product appears twice in the catalog."),
        ("Calendar sync for event leads", "Is it possible to push upcoming event-lead dates to Google Calendar?"),
        ("Zapier trigger not firing", "My Zap that fires on 'lead won' has not triggered since last {month}."),
    ],
    "billing": [
        ("Card declined but I updated it", "I got a payment failed email, but our card was already updated last week. Please retry the {plan} charge."),
        ("Charged twice this month", "I see two charges for SweetReach on my statement this month. Can you check?"),
        ("Need invoice for accounting", "Our bookkeeper needs invoices for the past {n} months with our legal business name on them."),
        ("Switch to annual billing", "We'd like to move from monthly to annual billing. Do we keep the discount?"),
        ("Downgrade my plan after the holidays", "We're slowing down after the season. How do I downgrade from {plan} without losing our leads?"),
        ("Sales tax on my invoice", "Why is there sales tax on our invoice this month? It wasn't there before."),
    ],
    "reports": [
        ("Revenue report missing last month", "The Sales by Campaign report stops at the 15th of {month}."),
        ("Can I see which candy sells best by season?", "I'd like a report of top categories by month so I can plan buying for the holidays."),
        ("Report totals differ from my POS", "Revenue in SweetReach is a few hundred dollars less than {pos} for the same dates."),
        ("How is win rate calculated?", "Dashboard says our win rate is {n}% but I count more wins than that. What's included?"),
        ("Download report as PDF", "My accountant wants the quarterly campaign report as a PDF. Is that available?"),
        ("Benchmark vs other shops", "Is there a way to see how our lead conversion compares with similar candy shops in our region?"),
    ],
    "presales": [
        ("Does SweetReach work with {pos}?", "Before we commit I need to know if you integrate with {pos} and how long setup takes."),
        ("Pricing for multiple locations", "We have {n} shops in the {city} area. Is there multi-location pricing?"),
        ("Can I get a demo this week?", "We saw your booth and would like a walkthrough focused on finding school fundraiser buyers."),
    ],
}
INCIDENT_TEMPLATES = {
    "campaigns": ("Campaign not delivered - {title}", "Our scheduled campaign never went out. Is there a known issue? ({title})"),
    "lead_finder": ("Lead Finder broken - {title}", "The Lead Finder is not loading any results for us right now. ({title})"),
}
AGENT_REPLIES = [
    "Thanks for reaching out, {name}. I'm looking into this now and will update you shortly.",
    "Hi {name}, I've reproduced what you're seeing. I've passed it to our engineers and I'll follow up as soon as I have news.",
    "Hi {name}, could you send a screenshot and the approximate time this happened? That will help me trace it.",
    "Thanks {name}. I checked your account settings and found the cause. I've made a change on our side - please try again and let me know.",
    "Hi {name}, this is a known issue and a fix is rolling out. I'll keep this ticket open until it's confirmed on your account.",
]
AGENT_SOLVED = [
    "That should be fixed now. Please let us know if anything looks off, otherwise I'll mark this solved.",
    "I've refreshed your data and everything is syncing. Marking this as solved - reply any time to reopen.",
    "We've applied the correction and sent you a confirmation email. Closing this out for now.",
    "Thanks for your patience. The issue was on our side and is resolved. Happy selling!",
]
REQUESTER_FOLLOWUPS = [
    "Here's a screenshot of what I'm seeing. It started a couple of days ago.",
    "Still happening on my end. I tried logging out and back in.",
    "Yes, that's the right account. Please go ahead.",
    "It's urgent - we have an event order due this weekend.",
]
REQUESTER_THANKS = ["That fixed it, thank you!", "Works now, thanks for the quick help.", "Thanks - appreciated."]
CSAT_COMMENTS_GOOD = ["Fast and friendly!", "Solved my problem right away.", "Great support.", ""]
CSAT_COMMENTS_BAD = ["Took too long to resolve.", "Had to explain the problem three times.", "Issue came back.", ""]
TICKET_FAILURE_CODES = [("card_declined", 0.45), ("expired_card", 0.30), ("insufficient_funds", 0.20), ("processing_error", 0.05)]

# --------------------------------------------------------------------------- marketing
WEB_PAGES = ["/", "/pricing", "/features/lead-finder", "/features/campaigns", "/blog/halloween-candy-sales-tips",
             "/blog/find-school-fundraiser-buyers", "/case-studies/gumdrop-corner", "/integrations", "/demo", "/signup"]
CONTENT_ASSETS = ["Holiday Candy Sales Playbook (PDF)", "Wedding & Event Candy Buyers Checklist", "Back-to-School Fundraiser Guide",
                  "Candy Shop Marketing Calendar 2026", "How to Price Bulk Candy Orders"]
AD_CREATIVES = ["find-your-sweet-tooth-crowd", "sell-more-candy-this-halloween", "fill-your-holiday-calendar", "fundraiser-buyers-nearby"]


# =========================================================================== free text
COMPETITORS = ["ConfectConnect", "LeadLoop", "SweetPipe", "Mailbloom", "ShopSpark", "a spreadsheet"]
FEATURES = ["the lead search", "campaign reporting", "the SMS tool", "inventory sync", "the scheduling feature"]

# What a shop writes when it cancels. Keys are the TRUE reason; the dropdown code the shop picks may differ.
EXIT_TEXT = {
    "too_expensive": [
        "Just couldn't justify ${price}/month when we only closed {n} orders from the leads. Might come back if there is a cheaper tier.",
        "price. we're a tiny shop and the {plan} plan was too much after the holidays",
        "Loved the idea but the cost didn't work for us. {competitor} is cheaper per lead.",
        "Budget got cut and subscriptions had to go. Nothing wrong with the product.",
        "Hard to see the return at ${price} a month - three or four wedding orders in {months} months isn't enough to cover it.",
    ],
    "not_enough_leads": [
        "The Lead Finder kept showing {leadtype} leads in {city} that were stale or had disconnected phone numbers. We only had {n} real conversations.",
        "Not enough local leads for a small town. Most of what it found was outside our delivery radius.",
        "We expected a steady stream of school and wedding buyers. It was a trickle, honestly.",
        "leads dried up after the first month, same names over and over",
        "I wanted more corporate gift buyers around {city} and kept getting birthday parties for $40. Not worth it for us.",
    ],
    "closing_shop": [
        "We're closing the shop at the end of the month after {years} years. Thanks for everything.",
        "Lease wasn't renewed and we're shutting the store. Sad to go.",
        "Retiring! Selling the building. SweetReach was great while it lasted.",
        "Business is closing, please delete our data.",
    ],
    "switched_to_competitor": [
        "Moved to {competitor} - their {feature} works better with {pos}.",
        "Our distributor bundled {competitor} for free so we switched.",
        "Found {competitor}, similar leads at lower cost, and they sync with {pos}.",
        "Switching providers. {competitor} offered a better onboarding.",
    ],
    "seasonal_pause": [
        "We're a seasonal shop, open September through January. Will restart in the fall.",
        "Pausing until Halloween prep starts. Please keep our data!",
        "Slow season. We'll be back before the holidays.",
        "summer is dead for us, canceling until september",
    ],
    "missing_pos_integration": [
        "Couldn't get {pos} to sync inventory and entering products by hand was killing us.",
        "No real integration with {pos}. Support said it's on the roadmap but we couldn't wait.",
        "Our {pos} sales never showed up in SweetReach so the reports were useless.",
    ],
    "trial_expired": [
        "Didn't have time to try it during the 14 days.",
        "The trial was too short to see any leads come in. Maybe extend it for seasonal shops?",
        "Wasn't sure how to get started and never heard back on my setup question.",
        "just kicking the tires, not ready to commit to a plan yet",
        "Looked good but we're slammed with {holiday} orders. Maybe after the rush.",
    ],
    "no_time_to_use": [
        "Honestly never had time to log in. I run the counter myself.",
        "Too busy with the shop to run campaigns. My fault, not yours.",
        "We kept meaning to set up campaigns and never did. Not using it so no point paying.",
    ],
}
EXIT_CODES = {  # the dropdown on the cancellation form
    "too_expensive": "too_expensive", "not_enough_leads": "poor_lead_quality", "closing_shop": "closing_business",
    "switched_to_competitor": "switched_provider", "seasonal_pause": "seasonal", "missing_pos_integration": "missing_feature",
    "no_time_to_use": "not_using", "trial_expired": "just_trying_it",
}
EXIT_CODE_FALLBACK = "other"
# billing portal (Stripe-like) cancellation reasons
BILLING_CANCEL_ENUM = {
    "too_expensive": "too_expensive", "not_enough_leads": "low_quality", "closing_shop": "other",
    "switched_to_competitor": "switched_service", "seasonal_pause": "unused", "missing_pos_integration": "missing_features",
    "no_time_to_use": "unused",
}
BILLING_COMMENTS = {
    "too_expensive": ["too pricey", "cost", "can't afford it right now"], "not_enough_leads": ["leads weren't good", "not enough leads"],
    "closing_shop": ["closing", "going out of business"], "switched_to_competitor": ["using something else now", "switched"],
    "seasonal_pause": ["seasonal", "will be back"], "missing_pos_integration": ["no integration", "doesnt sync"],
    "no_time_to_use": ["not using it", "no time"],
}
NPS_TEXT = {
    "promoter": [
        "The Lead Finder found a {leadtype} that turned into a ${amount} order. Paid for itself in a month.",
        "Campaigns are so easy. Our {holiday} promo was our best week all year.",
        "Love it. Support answered within the hour when I got stuck.",
        "Finally something built for candy shops, not generic marketing software.",
    ],
    "passive": [
        "It's fine. Leads are decent but I wish it connected better to {pos}.",
        "Does what it says. Reporting could be clearer about which campaign made the sale.",
        "Okay so far, still figuring out the best way to use the SMS campaigns.",
    ],
    "detractor": [
        "Leads were mostly low value. I expected more {leadtype} buyers near {city}.",
        "Support was slow when billing got messed up. Took days.",
        "Too many features I don't need and the ones I do (inventory sync) don't work well.",
        "Hard to tell if it's actually bringing in orders.",
    ],
}
LEAD_NOTES = [
    "Called {first}, wants about {qty} {product} for the {event}. Call back after the {day}.",
    "Left voicemail. They did a {product} order last year through someone else.",
    "emailed quote for {qty} {product}, waiting on approval",
    "{first} asked for sample bags first. Will drop off Friday.",
    "Wants {qty} favors for a {event} on the {day}, budget around ${amount}",
    "not interested this year, maybe next spring",
    "very interested - needs invoice net 30 (PTA treasurer)",
    "Referred by a customer. Wants a gift box for {n} employees.",
    "wrong number",
]
LEAD_NOTE_EVENTS = ["fall festival", "fundraiser", "wedding", "office party", "bake sale", "holiday party", "team banquet"]
CALL_NOTES = {
    "Lead": ["Sent intro email. No response yet.", "Left voicemail with the owner.", "Connected on LinkedIn."],
    "MQL": ["Opened our playbook email twice. Reached out for a quick call.", "Downloaded the holiday guide. Owner mentioned using {pos}.",
            "Owner replied - busy season, call back in two weeks."],
    "SQL": ["Discovery call: currently uses a spreadsheet and {pos}. Main goal is more {leadtype} orders.", "Spoke with owner, concerned about price vs. a slow summer.",
            "Wants a demo with the store manager present."],
    "Opportunity": ["Demo went well. Sending {plan} proposal.", "Asked about discount - offered {discount}% for annual.", "Comparing us with {competitor}."],
}
LOST_REASONS = [
    "Went with {competitor}.", "No budget until after the holidays.", "Shop closing / owner retiring.", "Not the decision maker, owner unreachable.",
    "Wants to try a free tool first.", "Too small - only open weekends.", "No POS integration for {pos}.",
]
FORM_MESSAGES = [
    "We have a candy shop in {city} and want to sell more bulk orders to schools.",
    "How does the lead search work? We do mostly weddings and corporate gifts.",
    "Looking for help filling our calendar for the holidays.",
    "Do you integrate with {pos}? Setup time?",
    "Saw you at the show. Interested in the fundraiser leads.",
    "just curious about pricing",
]
WEBINAR_QUESTIONS = ["Does this work for a shop with only one location?", "Can I target daycares and preschools?",
                     "How do you find the leads - scraped or opt-in?", "What does the Starter plan include?"]
