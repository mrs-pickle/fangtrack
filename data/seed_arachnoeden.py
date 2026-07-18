"""Real ArachnoEden listing data captured 2026-07-11 via direct page verification.

Source: https://arachnoeden.org/product-category/{females,spiderlings}/
Females: complete (all 66). Spiderlings: page 1 of 4 (24 of 84).
Each tuple: (title, price_text, outofstock, category)
These are fed through the live ArachnoEdenVendor parser, so the same code path
that will run on your machine also produced the seeded rows.
"""

FEMALES = [
    ("Acanthoscurria geniculata female • 2 1/2 - 3 inches, 4 inches (Brazilian white knee)", "$150.00 – $200.00", False, "females"),
    ("Amazonius germani female • 1 1/2\" (orange chevron treespider)", "$150.00", True, "females"),
    ("Aphonopelma chalcodes female • 2 1/2\" (Arizona blonde)", "$125.00", True, "females"),
    ("Aphonopelma sp. \"El Grullo\" female • 1 3/4\" (dry cross tarantula)", "$200.00", False, "females"),
    ("Brachypelma albiceps female • 2\" (Mexican golden red rump)", "$180.00", False, "females"),
    ("Brachypelma boehmei female • 2\" (Mexican fireleg tarantula)", "$250.00", False, "females"),
    ("Brachypelma hamorii female • 2 1/2\" (Mexican red knee)", "$225.00", False, "females"),
    ("Brachypelma smithi female • 1 1/2 - 2\" (Mexican giant orange knee)", "$200.00", False, "females"),
    ("Bumba horrida female • 3\" (Maracá black rose)", "$175.00", False, "females"),
    ("Caribena versicolor female • 2 1/2\" (Martinique or Antilles pink toe)", "$275.00", False, "females"),
    ("Chaetopelma olivaceum female • 1 1/2\" (Middle Eastern olive)", "$125.00", False, "females"),
    ("Chromatopelma cyaneopubescens female • 2\" (GBB, green bottle blue)", "$200.00", False, "females"),
    ("Citharacanthus cyaneus female • 2\" (purple Zoro)", "$190.00", True, "females"),
    ("Crassicrus sp. \"Veracruz\" female • 1 1/2\"", "$150.00", False, "females"),
    ("Cyriopagopus lividus female • 3\" (colbalt blue earthtiger)", "$130.00", False, "females"),
    ("Davus pentaloris female • 2\" (Guatemalan tiger rump)", "$95.00", False, "females"),
    ("Davus ruficeps female • 2\" (Costa Rican tiger rump)", "$145.00", False, "females"),
    ("Davus sp. \"Panama\" female • 1 1/2\" (lava tarantula)", "$375.00", False, "females"),
    ("Eupalaestrus campestratus female • 4\" (pink zebra beauty)", "$500.00", True, "females"),
    ("Ewok pruriens female • 2 1/2\" (Peruvian green velvet)", "$165.00", True, "females"),
    ("Grammostola anthracina female • 3\" (tawny red tarantula)", "$350.00", True, "females"),
    ("Grammostola grossa female • 3\" (Guarani giant tarantula)", "$450.00", False, "females"),
    ("Grammostola pulchra female • 1 3/4 - 2\" (Brazilian black tarantula)", "$275.00", True, "females"),
    ("Grammostola pulchripes female • 4\" (Chaco golden knee)", "$400.00", False, "females"),
    ("Hapalopus formosus female • 1 3/4\" (pumpkin patch dwarf)", "$120.00", False, "females"),
    ("Haplocosmia himalayana female • 2\" (Himalayan earthtiger)", "$165.00", False, "females"),
    ("Holothele longipes female • 2 1/4\"", "$85.00", False, "females"),
    ("Kochiana brunnipes female • 1 1/4\" (dwarf pink leg)", "$125.00", False, "females"),
    ("Lasiocyano sazimai female • 2\" (Brazilian blue or Sazima's tarantula)", "$155.00", True, "females"),
    ("Lasiodora parahybana female • 1 3/4\" (salmon pink birdeater)", "$120.00", True, "females"),
    ("Lasiodora subcanens female • 1 1/2 - 2\" (silverback birdeater)", "$350.00", False, "females"),
    ("Lasiodorides striatus female • 1 3/4\" (Peruvian orange stripe)", "$125.00", False, "females"),
    ("Neoholothele incei female • 1 1/2\" (Trinidad olive dwarf)", "$80.00", False, "females"),
    ("Neoholothele incei gold female • 2\" (Trinidad gold dwarf)", "$85.00", True, "females"),
    ("Nhandu carapoensis female • 1 1/2 - 2\" (Brazilian red tarantula)", "$175.00", False, "females"),
    ("Nhandu tripepii female • 2 3/4\" (Brazilian giant blonde)", "$125.00", True, "females"),
    ("Pamphobeteus fortis female • 2 1/2\" (giant copper bloom)", "$250.00", False, "females"),
    ("Pamphobeteus sp. \"antinous big black\" female • 2 1/2\"", "$250.00", False, "females"),
    ("Pamphobeteus sp. \"cascada\" female • 2 1/2 - 3\"", "$250.00", False, "females"),
    ("Pamphobeteus sp. \"costa\" female • 2 1/2\"", "$250.00", False, "females"),
    ("Pamphobeteus sp. \"Durán\" female • 2 1/2\"", "$250.00", True, "females"),
    ("Pamphobeteus sp. \"Machala\" female • 3 1/2\"", "$275.00", False, "females"),
    ("Pamphobeteus sp. \"platyomma light\" female • 2 1/2\" (Ecuadorian light bloom)", "$300.00", False, "females"),
    ("Pamphobeteus sp. \"platyomma\" female • 3\" (Ecuadorian pink bloom)", "$250.00", False, "females"),
    ("Pamphobeteus sp. \"tigris\" female • 2 1/2 - 3\" (tiger birdeater)", "$250.00", False, "females"),
    ("Pamphobeteus sp. \"mascara\" female • 2.5\", 3.5-4\" (mascara giant birdeater)", "$200.00 – $300.00", True, "females"),
    ("Pamphobeteus ultramarinus female • 2 1/2\"", "$350.00", True, "females"),
    ("Phormictopus auratus female • 3\" (Cuban bronze tarantula)", "$190.00", True, "females"),
    ("Phormictopus cancerides female • 1 1/2 - 2\"", "$175.00", False, "females"),
    ("Psalmopoeus cambridgei female • 3 1/2\" (Trinidad chevron tarantula)", "$180.00", False, "females"),
    ("Psalmopoeus victori female • 2\" (Darth Maul fire & ice tarantula)", "$180.00", True, "females"),
    ("Sericopelma sp. \"Chica\" female • 2 1/2\"", "$150.00", False, "females"),
    ("Sericopelma sp. \"Chiriqui\" female • 2 1/2\"", "$125.00", False, "females"),
    ("Spinosatibiapalpus sp. \"Colombia\" female • 2\" (yellow-blue dwarf)", "$225.00", True, "females"),
    ("Tapinauchenius rasti female • 2\" (Caribbean diamond tarantula)", "$150.00", False, "females"),
    ("Theraphosa blondi female • 2\" (goliath birdeater)", "$300.00", True, "females"),
    ("Theraphosa stirmi female • 3 1/2\" (burgundy goliath birdeater)", "$250.00", True, "females"),
    ("Tliltocatl albopilosus female • 2\" (curly hair tarantula)", "$80.00", True, "females"),
    ("Tliltocatl kahlenbergi female • 2 1/2\" (Veracruz red rump)", "$95.00", False, "females"),
    ("Tliltocatl verdezi female • 2\" (Mexican rose grey)", "$125.00", False, "females"),
    ("Vitalius chromatus female • 3\" (Brazilian red and white tarantula)", "$135.00", True, "females"),
    ("Xenesthis immanis female • 3\" (Colombian lesserblack tarantula)", "$275.00", True, "females"),
    ("Xenesthis intermedia female • 3 - 3 1/2\" (Venezuelan blue bloom)", "$325.00", False, "females"),
    ("Xenesthis sp. \"blue\" female • 3\" (Colombian greater blue birdeater)", "$550.00", True, "females"),
    ("Xenesthis sp. \"bright\" female • 3 - 3 1/2\" (boxer-cut birdeater)", "$475.00", True, "females"),
    ("Xenesthis sp. \"megascopula\" female • 1 1/2 - 2\"", "$400.00", True, "females"),
]

SPIDERLINGS = [
    ("Acanthoscurria geniculata spiderling • 3/4 - 1 1/4\" (Brazilian white knee)", "$40.00", False, "spiderlings"),
    ("Amazonius germani spiderling • 1 - 1 1/4\" (orange chevron treespider)", "$35.00", True, "spiderlings"),
    ("Aphonopelma bicoloratum spiderling • 1/2 - 5/8\" (Mexican bloodleg)", "$75.00", False, "spiderlings"),
    ("Aphonopelma chalcodes spiderling • 1/2 - 5/8\" (Arizona blonde)", "$30.00", False, "spiderlings"),
    ("Aphonopelma seemanni spiderling • 1 - 1 1/2\" (Costa Rican zebra tarantula)", "$30.00", False, "spiderlings"),
    ("Avicularia purpurea spiderling • 5/8 - 3/4\" (Ecuadorian purple pink toe)", "$90.00", False, "spiderlings"),
    ("Birupes simoroxigorum spiderling • 5/8\" (Sarawakian neon blue leg)", "$55.00", False, "spiderlings"),
    ("Brachionopus sp. \"Limpopo\" spiderling • 1/2\" (Limpopo dwarf baboon)", "$40.00", False, "spiderlings"),
    ("Brachypelma albiceps spiderling • 3/4\" (Mexican golden red rump)", "$45.00", False, "spiderlings"),
    ("Brachypelma auratum spiderling • 5/8\" (Mexican flame knee)", "$55.00", False, "spiderlings"),
    ("Brachypelma boehmei • 1\" (Mexican fireleg tarantula)", "$45.00", False, "spiderlings"),
    ("Brachypelma emilia spiderling • 5/8\" (Mexican red leg)", "$45.00", False, "spiderlings"),
    ("Brachypelma hamorii (ex. smithi) spiderling • 5/8 - 3/4\" (Mexican red knee)", "$45.00", False, "spiderlings"),
    ("Brachypelma smithi spiderling • 5/8 - 3/4\" (Mexican giant orange knee)", "$55.00", True, "spiderlings"),
    ("Bumba horrida spiderling • 5/8 - 3/4\" (Maracá black rose)", "$35.00", False, "spiderlings"),
    ("Caribena versicolor spiderling • 1/2 - 5/8\" (Martinique or Antilles pink toe)", "$45.00", False, "spiderlings"),
    ("Ceratogyrus brachycephalus spiderling • 1+\" (greater horned baboon)", "$65.00", False, "spiderlings"),
    ("Ceratogyrus darlingi spiderling • 1\" (rear-horned baboon)", "$35.00", True, "spiderlings"),
    ("Chaetopelma lymberakisi spiderling • 5/8\" (Cretan rock dwarf)", "$35.00", False, "spiderlings"),
    ("Chaetopelma olivaceum spiderling • 5/8 - 3/4\" (Middle Eastern olive)", "$30.00", False, "spiderlings"),
    ("Chilobrachys fimbriatus spiderling • 3/4 - 1\"", "$40.00", False, "spiderlings"),
    ("Chilobrachys huahini spiderling • 3/4\"", "$40.00", False, "spiderlings"),
    ("Chilobrachys natanicharum spiderling • 3/4 - 1\" (electric blue earthtiger)", "$45.00", False, "spiderlings"),
    ("Chilobrachys sp. \"black satan\" • 1\" (black satan earthtiger)", "$40.00", False, "spiderlings"),
]

ALL_CARDS = FEMALES + SPIDERLINGS


def _slugify(title: str, category: str) -> str:
    import re
    head = re.split(r"[•·]", title)[0]
    head = re.sub(r"\b(female|male|spiderling|juvenile|adult)\b", "", head, flags=re.I)
    head = re.sub(r"[^a-z0-9]+", "-", head.lower()).strip("-")
    return f"https://arachnoeden.org/shop/{category}/{head}/"


def as_cards():
    """Yield card dicts matching ArachnoEdenVendor._parse_listing_page output."""
    for title, price_text, oos, category in ALL_CARDS:
        yield {
            "title": title,
            "url": _slugify(title, category),
            "price_text": price_text,
            "outofstock": oos,
            "_category": category,
        }
