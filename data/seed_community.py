#!/usr/bin/env python3
"""
Community price seeder for the Tarantula Market Tracker.

Parses price lists from private sellers, wholesalers, and The Spider Room reference list,
then inserts them into price_history with appropriate verification levels.

Run from inside the tarantula_market_tracker/ directory:
    python data/seed_community.py [--dry-run]
"""

import sys
import os
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_connection, init_db, upsert_vendor, DB_PATH
from normalize.species import normalize_species_key
from normalize.size import parse_size

# ---------------------------------------------------------------------------
# RAW DATA FORMAT
# Each entry: (scientific_name, common_name, size_str, sex, price, qty, notes, category)
#
#   sex:      None=unsexed/unknown  |  "F"=confirmed female  |  "M"=confirmed male
#              "PF"=probable female  |  "PM"=probable male
#   size_str: string in inches, e.g. "0.5", "1.5", "2-3", None
#   category: "T"=tarantula  "S"=spider  "SC"=scorpion  "C"=centipede
#              "M"=millipede  "O"=other
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# UNNAMED FACEBOOK SELLER — UPDATED LIST
# ---------------------------------------------------------------------------
FB_SELLER_UPDATED = [
    # Tarantulas
    ("Cyriocosmus aueri",                    "Peruvian Dwarf Red Leg",          "0.25", None,  50.0,  2, None,                        "T"),
    ("Cyriocosmus leetzi",                   "Colombian Dwarf",                 "0.25", None,  60.0,  3, None,                        "T"),
    ("Homoeomma chilense",                   "Chilean Flame",                   "0.25", None, 120.0,  1, None,                        "T"),
    ("Tliltocatl albopilosus",               "Curly Hair",                      "0.5",  None,  10.0, 10, None,                        "T"),
    ("Grammostola quirogai",                 "Uruguayan Black",                 "0.75", None, 100.0,  6, None,                        "T"),
    ("Davus sp. Panama",                     "Lava Tarantula",                  "0.75", None, 170.0,  1, None,                        "T"),
    ("Anqasha sp. Blue",                     None,                              "1.0",  None, 250.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden Knee",               "1.0",  None,  45.0,  1, None,                        "T"),
    ("Ceratogyrus brachycephalus",           "Greater Horned Baboon",           "2.0",  None, 150.0,  1, None,                        "T"),
    ("Hapalopus formosus",                   "Pumpkin Patch",                   "2.0",  None, 100.0,  2, None,                        "T"),
    ("Tliltocatl sabulosus",                 "Guatemalan Tiger Rump",           "2.0",  None,  80.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden Knee",               "2.5",  None, 135.0,  1, None,                        "T"),
    ("Davus pentaloris",                     "Guatemalan Tiger Rump",           "2.5",  "PF", 125.0,  1, "probable female",            "T"),
    ("Tliltocatl verdezi",                   "Mexican Grey Rose",               "2.5",  None,  80.0,  1, None,                        "T"),
    ("Cyriopagopus lividus",                 "Cobalt Blue",                     "3.0",  None, 100.0,  2, None,                        "T"),
    ("Phormictopus sp. Dominican Purple",    None,                              "3.0",  "F",  300.0,  1, None,                        "T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "3.0",  None, 125.0,  2, None,                        "T"),
    ("Selenocosmia javanensis",              None,                              "3.0",  None,  65.0,  3, "2.5-3.5 in",                "T"),
    ("Aphonopelma chalcodes",                "Arizona Blonde",                  "4.0",  None,  90.0,  1, None,                        "T"),
    ("Phormictopus auratus",                 "Cuban Bronze",                    "4.5",  "F",  200.0,  1, None,                        "T"),
    # True spiders
    ("Phoneutria depilata",                  "Brazilian Wandering Spider",      "0.125",None,  30.0,  1, "CB",                        "S"),
    ("Latrodectus mactans",                  "Black Widow",                     "1.0",  "F",   25.0,  1, None,                        "S"),
    ("Latrodectus mactans",                  "Black Widow",                     "1.5",  "F",   15.0,  1, "2 missing legs",            "S"),
    ("Heteropoda lunula",                    None,                              "0.33", None,  35.0,  3, "CBB",                       "S"),
    ("Hogna maderiana",                      None,                              "1.0",  None,  55.0,  1, None,                        "S"),
    ("Hogna miami",                          None,                              "0.33", None,   5.0, 10, "CB",                        "S"),
    ("Hogna miami",                          None,                              "1.25", None,  15.0,  1, None,                        "S"),
    ("Hogna miami",                          None,                              "2.0",  "F",   25.0,  1, None,                        "S"),
    ("Hogna lenta",                          None,                              "1.0",  None,  35.0,  5, "White",                     "S"),
    ("Hogna osceola",                        None,                              "1.0",  None,  30.0,  1, None,                        "S"),
    ("Ohvida sp. Cuba",                      None,                              "0.75", None,  80.0,  1, "CBB",                       "S"),
    ("Gigathele hungae",                     None,                              "0.75", None, 150.0,  2, None,                        "S"),
    ("Holconia murrayensis",                 "Murray Banded Huntsman",          "1.0",  None,  75.0,  1, "CBB",                       "S"),
    ("Cyclocosmia latusicosta",              None,                              "2.0",  None,  80.0,  4, None,                        "S"),
    ("Sicarius gracilis",                    None,                              "0.75", None, 100.0,  1, "CB",                        "S"),
    ("Heteropoda javana",                    None,                              "3.0",  "F",   60.0,  1, None,                        "S"),
    ("Heteropoda tetrica",                   None,                              "3.0",  "F",   85.0,  1, "Borneo",                    "S"),
    ("Heteropoda tetrica",                   None,                              "4.0",  "F",   75.0,  1, "China",                     "S"),
    ("Heteropoda davidbowie",                None,                              "0.25", None,  15.0, 10, "CB",                        "S"),
    ("Heteropoda sp. Malay Ocelot",          None,                              "5.0",  None, 100.0,  1, None,                        "S"),
    ("Heteropoda pingtungensis",             None,                              "0.25", None,  25.0,  6, "CB",                        "S"),
    ("Heteropoda davidbowie",                None,                              "2.0",  "M",   70.0,  1, "mature male",               "S"),
    ("Linothele sericata",                   None,                              "4.0",  "F",  250.0,  1, "CB",                        "S"),
    ("Platythomisus sp. Indonesia",          None,                              "0.5",  None,  70.0,  1, "undescribed",               "S"),
    ("Typopeltis laurentianus",              None,                              "2.5",  None,  50.0,  2, "amblypygi; 2-3 in",        "S"),
    # Scorpions
    ("Pandinus imperator",                   "Emperor Scorpion",                None,   None,  75.0,  5, "subadults",                 "SC"),
    ("Pandinus imperator",                   "Emperor Scorpion",                None,   None,  40.0,  5, "CB babies",                 "SC"),
    ("Heterometrus silenus",                 None,                              None,   None,  25.0,  1, "adult",                     "SC"),
    ("Heteroctonus junceus",                 None,                              None,   None, 100.0,  1, "adult probable female",     "SC"),
    # Centipedes
    ("Thereuopoda longicornis",              None,                              "2.5",  None, 150.0,  5, "2-3 in",                   "C"),
    ("Scolopendra cingulata",                None,                              "2.5",  None,  35.0,  6, "2-3 in",                   "C"),
    ("Scolopendra sp. Toraja Red",           None,                              "6.0",  None, 250.0,  1, None,                        "C"),
    ("Scolopendra subspinipes piceoflava",   None,                              "6.5",  None, 250.0,  1, None,                        "C"),
    ("Scolopendra longipes",                 None,                              "6.0",  None,  50.0,  1, None,                        "C"),
    ("Scolopendra sp. Sumatran Purple",      None,                              "6.0",  None, 250.0,  4, None,                        "C"),
    ("Scolopendra dehaani",                  None,                              "6.0",  None, 100.0,  1, "Thai Cherry",               "C"),
    ("Scolopendra sp. Java Black",           None,                              "7.0",  None, 190.0,  1, None,                        "C"),
    ("Scolopendra dehaani",                  None,                              "4.0",  None,  80.0,  2, "Indo Black Cherry",         "C"),
]

# ---------------------------------------------------------------------------
# ERIC MADRID — SEXED
# ---------------------------------------------------------------------------
ERIC_MADRID_SEXED = [
    ("Brachypelma hamorii",                  "Mexican Red Knee",                "2.5",  "F",  140.0,  1, None,                        "T"),
    ("Cyriopagopus lividus",                 "Cobalt Blue",                     "3.5",  "F",  100.0,  1, None,                        "T"),
    ("Cyriopagopus lividus",                 "Cobalt Blue",                     "6.0",  "F",  120.0,  1, None,                        "T"),
    ("Phormingochilus hati hati",            "Borneo Purple Earth Tiger",       "4.0",  "F",  160.0,  1, None,                        "T"),
    ("Dolichothele diamantinensis",          "Brazilian Blue Dwarf Beauty",     "2.0",  "F",  180.0,  3, None,                        "T"),
    ("Dolichothele diamantinensis",          "Brazilian Blue Dwarf Beauty",     "2.5",  "F",  200.0,  2, None,                        "T"),
    ("Davus pentaloris",                     "Guatemalan Tiger Rump",           "3.5",  "F",  160.0,  1, None,                        "T"),
    ("Euathlus truculentus",                 "Chilean Blue Femur",              "3.5",  "F",  450.0,  1, "pair w/ 2\" male",          "T"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "1.5",  "F",  200.0,  1, "listed as pulchra/quirogai","T"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "5.5",  "F",  550.0,  1, None,                        "T"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "5.0",  "M",  300.0,  1, None,                        "T"),
    ("Grammostola rosea",                    "Rose Hair RCF",                   "2.0",  "F",  200.0,  2, "RCF",                       "T"),
    ("Homoeomma chilenense",                 "Chilean Flame",                   "1.5",  "F",  500.0,  1, "pair price",                "T"),
    ("Hapalopus formosus",                   "Pumpkin Patch",                   "1.5",  "F",  100.0,  1, None,                        "T"),
    ("Hapalopus guerreroi",                  "Guerrero Pumpkin Patch",          "1.75", "F",  120.0,  1, None,                        "T"),
    ("Hapalopus guerreroi",                  "Guerrero Pumpkin Patch",          "2.5",  "F",  200.0,  1, None,                        "T"),
    ("Hysterocrates gigas",                  "Cameroon Red Baboon",             "4.0",  "F",  125.0,  1, None,                        "T"),
    ("Lasiodora klugi",                      "Bahia Scarlet",                   "5.0",  "F",  200.0,  1, None,                        "T"),
    ("Lasiocyaneo sazimai",                  "Brazilian Blue",                  "2.5",  "F",  140.0,  1, None,                        "T"),
    ("Nhandu carapoensis",                   "Brazilian Red",                   "3.5",  "F",  175.0,  1, None,                        "T"),
    ("Nhandu tripepii",                      "Brazilian Giant Blonde",          "7.0",  "F",  350.0,  1, None,                        "T"),
    ("Omothymus violaceopes",                "Singapore Blue",                  "5.5",  "F",  200.0,  1, None,                        "T"),
    ("Poecilotheria fasciata",               "Sri Lanka Ornamental",            "3.75", "F",  350.0,  1, "3.5-4 in",                 "T"),
    ("Pamphobeteus sp. Mascara",             "Mascara Bird Eater",              "6.0",  "F",  275.0,  1, None,                        "T"),
    ("Poecilotheria metallica",              "Gooty Sapphire",                  "2.5",  "F",  200.0,  1, None,                        "T"),
    ("P. ultramarinus",                      None,                              "4.0",  "F",  750.0,  1, "species unclear",           "T"),
    ("Psalmopoeus victori",                  "Darth Maul",                      "2.0",  "F",  140.0,  1, None,                        "T"),
    ("Sericopelma sp. Santa Catalina",       "Santa Catalina Bird Eater",       "3.75", "F",  200.0,  1, "3.5-4 in",                 "T"),
    ("Tliltocatl albopilosus",               "Curly Hair",                      "4.0",  "F",  100.0,  1, None,                        "T"),
    ("Tliltocatl albopilosus",               "Curly Hair",                      "4.5",  "F",  125.0,  1, None,                        "T"),
    ("Tliltocatl epicureanus",               "Yucatan Rust Rump",               "4.5",  "F",  150.0,  1, None,                        "T"),
    ("Tliltocatl sp. Lagunas",               None,                              "5.5",  "F",  450.0,  1, None,                        "T"),
    ("Thrixopelma ockerti",                  "Peruvian Red Rump",               "5.5",  "F",  250.0,  1, None,                        "T"),
    ("Tliltocatl vagans",                    "Mexican Red Rump",                "5.0",  "F",  150.0,  1, None,                        "T"),
    ("Chromatopelma cyaneopubescens",        "Green Bottle Blue",               "5.0",  "F",  250.0,  1, None,                        "T"),
    ("Chromatopelma cyaneopubescens",        "Green Bottle Blue",               "4.0",  "F",  200.0,  1, None,                        "T"),
    ("Xenesthis intermedia",                 "Amazon Blue Bloom",               "6.0",  "F",  450.0,  1, None,                        "T"),
    ("Xenesthis sp. Blue",                   "Blue Bloom",                      "4.0",  "F",  550.0,  1, None,                        "T"),
    ("Xenesthis sp. Blue",                   "Blue Bloom",                      "4.0",  "M",  300.0,  1, None,                        "T"),
    ("Pandinus imperator",                   "Emperor Scorpion",                "4.0",  "M",   80.0,  1, None,                        "SC"),
    ("Pandinus imperator",                   "Emperor Scorpion",                "4.0",  "F",   80.0,  1, None,                        "SC"),
]

# ---------------------------------------------------------------------------
# ERIC MADRID — SLINGS / JUVIES
# ---------------------------------------------------------------------------
ERIC_MADRID_SLINGS = [
    ("Acanthoscurria geniculata",            "Brazilian White Knee",            "0.5",  None,  25.0,  1, None,                        "T"),
    ("Amazonius germani",                    "Orange Tree Spider",              "0.75", None,  35.0,  1, None,                        "T"),
    ("Augacephalus rufus",                   "Peach Earth Tiger",               "0.5",  None,  40.0,  1, None,                        "T"),
    ("Augacephalus rufus",                   "Peach Earth Tiger",               "2.5",  None,  65.0,  1, None,                        "T"),
    ("Aphonopelma seemanni",                 "Costa Rican Stripe Knee",         "0.75", None,  30.0,  1, None,                        "T"),
    ("Brachypelma emilia",                   "Mexican Red Leg",                 "0.5",  None,  45.0,  1, None,                        "T"),
    ("Cyriopagopus lividus",                 "Cobalt Blue",                     "0.5",  None,  35.0,  1, None,                        "T"),
    ("Chilobrachys huahini",                 "Asian Giant Fawn",                "1.75", None,  35.0,  1, "1.5-2 in",                 "T"),
    ("Dolichothele diamantinensis",          "Brazilian Blue Dwarf Beauty",     "1.5",  None,  80.0,  1, None,                        "T"),
    ("Euathlus truculentus",                 "Chilean Blue Femur",              "1.0",  None, 140.0,  1, "blue form",                 "T"),
    ("Grammostola anthracina",               "Uruguayan Black",                 "0.875",None, 100.0,  1, "0.75-1 in",                "T"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "0.75", None,  80.0,  1, None,                        "T"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "1.25", None, 100.0,  1, None,                        "T"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "2.0",  "M",  150.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden Knee",               "0.5",  None,  40.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden Knee",               "1.25", None,  65.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden Knee",               "1.5",  None,  70.0,  1, None,                        "T"),
    ("Grammostola rosea",                    "Common Rose Hair",                "1.0",  None,  80.0,  1, None,                        "T"),
    ("Hapalopus formosus",                   "Pumpkin Patch",                   "0.75", None,  50.0,  1, None,                        "T"),
    ("Heteroscodra maculata",                "Togo Starburst Baboon",           "2.0",  None,  50.0,  4, None,                        "T"),
    ("Hysterocrates sp. Niger Delta",        None,                              "2.5",  None,  70.0,  1, None,                        "T"),
    ("Lasiodora klugi",                      "Bahia Scarlet",                   "0.5",  None,  35.0,  1, None,                        "T"),
    ("Lasiodora parahybana",                 "Brazilian Salmon Pink",           "0.75", None,  30.0,  1, None,                        "T"),
    ("Lasiodora parahybana",                 "Brazilian Salmon Pink",           "2.0",  None,  45.0,  1, None,                        "T"),
    ("Neoholothele incei",                   "Trinidad Olive Gold",             "1.5",  None,  50.0,  1, "gold form",                 "T"),
    ("Pterinochilus murinus",                "Orange Baboon (OBT)",             "1.75", None,  40.0,  1, "1.5-2 in",                 "T"),
    ("Phormictopus sp. Dominican Purple",    None,                              "1.0",  None,  60.0,  1, None,                        "T"),
    ("Pamphobeteus ecclesiasticus",          None,                              "1.75", "M",  100.0,  1, "1.5-2 in; male",           "T"),
    ("Phormingochilus hati hati",            "Borneo Purple Earth Tiger",       "1.75", None,  50.0,  1, "1.5-2 in",                 "T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "2.5",  None,  60.0,  1, None,                        "T"),
    ("Poecilotheria metallica",              "Gooty Sapphire",                  "0.75", None, 100.0,  1, None,                        "T"),
    ("Pelinobius muticus",                   "King Baboon",                     "0.75", None,  60.0,  1, None,                        "T"),
    ("Poecilotheria ornata",                 "Fringed Ornamental",              "1.0",  None,  80.0,  1, "IL residents only",         "T"),
    ("Poecilotheria regalis",                "Indian Ornamental",               "1.5",  None,  50.0,  1, None,                        "T"),
    ("Poecilotheria regalis",                "Indian Ornamental",               "0.875",None,  35.0,  1, "0.75-1 in",                "T"),
    ("Poecilotheria tigrinawesseli",         "Tiger Ornamental",                "1.75", None,  90.0,  1, "1.5-2 in",                 "T"),
    ("Poecilotheria vittata",                "Ghost Ornamental",                "1.0",  None,  70.0,  1, "IL residents only",         "T"),
    ("Tapinauchenius seladonia",             None,                              "0.5",  None, 275.0,  1, None,                        "T"),
    ("Tliltocatl kahlenbergi",               "Veracruz Red Rump",              "2.0",  None,  60.0,  1, None,                        "T"),
    ("Theraphosa blondi",                    "Goliath Bird Eating",             "1.5",  None, 120.0,  1, None,                        "T"),
    ("Tliltocatl vagans",                    "Mexican Red Rump",                "2.5",  None,  50.0,  1, None,                        "T"),
    ("Ybyrapora sooretama",                  "Amazon Purple Sapphire",          "0.875",None, 120.0,  1, "0.75-1 in",                "T"),
]

# ---------------------------------------------------------------------------
# GOOD GUY REPTILES — WHOLESALE (updated list with scientific names)
# $500 minimum order
# ---------------------------------------------------------------------------
GOOD_GUY_WHOLESALE = [
    ("Phidippus audax",                      "Bold Jumping Spider",             None,   None,  10.0,  1, "wholesale; all sizes; $500 min",   "S"),
    ("Phidippus regius",                     "Regal Jumping Spider",            None,   None,  18.0,  1, "wholesale; 12/$15; $500 min",      "S"),
    ("Archispirostreptus gigas",             "African Giant Millipede",         "7.0",  None,  35.0,  1, "wholesale; 6-8in; 10/$30; $500 min","M"),
    ("Pandinus imperator",                   "True Emperor Scorpion",           "4.0",  None,  35.0,  1, "wholesale; 3-5 in; $500 min",      "SC"),
    ("Heterometrus sp.",                     "Asian Forest Scorpion",           "4.0",  None,  12.0,  1, "wholesale; 3-5 in; $500 min",      "SC"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "1.0",  None,  50.0,  1, "wholesale; 1in+; $500 min",         "T"),
    ("Grammostola rosea",                    "Rose Hair Red",                   "1.5",  None,  49.0,  1, "wholesale; 1-2 in; $500 min",       "T"),
    ("Tliltocatl albopilosus",               "Curly Hair",                      "0.5",  None,   8.0,  1, "wholesale; 0.5in+; $500 min",       "T"),
    ("Tliltocatl schroederi",                "Mexican Black Velvet",            "1.0",  None,  39.0,  1, "wholesale; $500 min",               "T"),
    ("Theraphosinae sp. Roatan",             "Roatan Island Purple",            "0.3",  None,  19.0,  1, "wholesale; $500 min",               "T"),
    ("Theraphosa apophysis",                 "Goliath Pink Foot",               "1.5",  None,  65.0,  1, "wholesale; $500 min",               "T"),
    ("Phormingochilus hati hati",            "Borneo Purple Earth Tiger",       "1.0",  None,  24.0,  1, "wholesale; $500 min",               "T"),
    ("Phormingochilus arboricola",           "Borneo Black",                    "1.0",  None,  29.0,  1, "wholesale; $500 min",               "T"),
    ("Phormictopus atrichomatus",            "Red Island Birdeater",            "1.0",  None,  49.0,  1, "wholesale; 1in+; $500 min",         "T"),
    ("Pamphobeteus sp. Platyomma",           "Pink Bloom",                      "1.0",  None,  75.0,  1, "wholesale; $500 min",               "T"),
    ("Orphnaecus sp. Negros",               "Negros Island Earth Tiger",        "1.0",  None,  29.0,  1, "wholesale; $500 min",               "T"),
    ("Orphnaecus dichromatus",               "New Guinea Two-Toned Earth Tiger","1.0",  None,  39.0,  1, "wholesale; $500 min",               "T"),
    ("Ornithoctoninae sp. Ranong Blue",      "Ranong Blue Earth Tiger",         "1.0",  None,  50.0,  1, "wholesale; $500 min",               "T"),
    ("Ornithoctoninae sp. Long Na",          "Long Na Earth Tiger",             "1.5",  None,  50.0,  1, "wholesale; $500 min",               "T"),
    ("Omothymus violaceopes",                "Singapore Blue",                  "1.0",  None,  35.0,  1, "wholesale; $500 min",               "T"),
    ("Omothymus schioedtei",                 "Malaysian Earth Tiger",           "1.0",  None,  39.0,  1, "wholesale; $500 min",               "T"),
    ("Monocentropus balfouri",               "Socotra Island Blue Baboon",      "1.5",  None,  39.0,  1, "wholesale; 1-2 in; $500 min",       "T"),
    ("Megaphobema robustum",                 "Colombian Giant Red-Leg",         "1.0",  None,  45.0,  1, "wholesale; 1in+; $500 min",         "T"),
    ("Magnacrus tongmianensis",              "Chinese Stout Leg",               "1.5",  None,  50.0,  1, "wholesale; $500 min",               "T"),
    ("Magnacrus taynguyenensis",             "Vietnam Highland",                "1.5",  None,  50.0,  1, "wholesale; $500 min",               "T"),
    ("Lasiodorides striatus",                "Peruvian Orange Stripe",          "0.75", None,  32.0,  1, "wholesale; $500 min",               "T"),
    ("Lasiodorides polycuspulatus",          "Peruvian Giant Blonde",           "0.5",  None,  32.0,  1, "wholesale; $500 min",               "T"),
    ("Lasiodora klugi",                      "Bahia Scarlet Bird Eater",        "1.0",  None,  25.0,  1, "wholesale; $500 min",               "T"),
    ("Lasiocyaneo sazimai",                  "Brazilian Blue",                  "1.0",  None,  29.0,  1, "wholesale; $500 min",               "T"),
    ("Hysterocrates gigas",                  "Cameroon Red Baboon",             "1.5",  None,  26.0,  1, "wholesale; $500 min",               "T"),
    ("Harpactira pulchripes",                "Golden Blue-Legged Baboon",       "1.0",  None,  50.0,  1, "wholesale; $500 min",               "T"),
    ("Harpactira namaquensis",               "Bronze Baboon",                   "1.25", None,  49.0,  1, "wholesale; 1-1.5 in; $500 min",     "T"),
    ("Hapalopus sp. Colombia Large",         "Pumpkin Patch",                   "0.33", None,  19.0,  1, "wholesale; $500 min",               "T"),
    ("Guyruita cerrado",                     "Brazilian Savannah Dwarf",        "0.5",  None,  30.0,  1, "wholesale; $500 min",               "T"),
    ("Grammostola pulchripes",               "Chaco Golden-Knee",               "0.75", None,  20.0,  1, "wholesale; 0.5-1 in; $500 min",     "T"),
    ("Davus pentaloris",                     "Guatemalan Tiger Rump",           "0.5",  None,  19.0,  1, "wholesale; $500 min",               "T"),
    ("Cyriopagopus sp. Bach Ma",             "Bach Ma Earth Tiger",             "2.0",  None,  50.0,  1, "wholesale; $500 min",               "T"),
    ("Cilantica psychedelicus",              "LSD Earth Tiger",                 "1.0",  None,  79.0,  1, "wholesale; $500 min",               "T"),
    ("Chilobrachys sp. Kaeng Krachen",       "Dark Earth Tiger",                "1.0",  None,  22.0,  1, "wholesale; $500 min",               "T"),
    ("Chilobrachys natanicharum",            "Electric Blue",                   "1.0",  None,  35.0,  1, "wholesale; $500 min",               "T"),
    ("Chilobrachys huahini",                 "Asian Giant Fawn",                "1.0",  None,  19.0,  1, "wholesale; $500 min",               "T"),
    ("Chilobrachys dyscolus",                "Vietnam Blue",                    "1.0",  None,  39.0,  1, "wholesale; $500 min",               "T"),
    ("Ceratogyrus sanderi",                  "Namibia Horned Baboon",           "0.75", None,  39.0,  1, "wholesale; 0.5-1 in; $500 min",     "T"),
    ("Ceratogyrus meridionalis",             "Zimbabwe Grey Baboon",            "1.0",  None,  29.0,  1, "wholesale; $500 min",               "T"),
    ("Ceratogyrus darlingi",                 "Rear-Horned Baboon",              "1.0",  None,  25.0,  1, "wholesale; 1in+; $500 min",         "T"),
    ("Ceratogyrus brachycephalus",           "Greater Horned Baboon (Wild)",    "1.0",  None,  45.0,  1, "wholesale; wild form; $500 min",    "T"),
    ("Catumiri argentinense",                "Dwarf Argentine Bronze",          "1.0",  None,  29.0,  1, "wholesale; $500 min",               "T"),
    ("Brachypelma albiceps",                 "Mexican Golden Red Rump",         "0.5",  None,  29.0,  1, "wholesale; 0.5in+; $500 min",       "T"),
    ("Bonnetina tanzeri",                    "Michoacan Red Rump",              "5.0",  None,  29.0,  1, "wholesale; 5in+; $500 min",         "T"),
    ("Augacephalus breyeri",                 "Lowveld Golden Baboon",           "1.0",  None,  60.0,  1, "wholesale; 1in+; $500 min",         "T"),
    ("Aspinochilus rufus",                   "Peach Earth Tiger",               "1.0",  None,  29.0,  1, "wholesale; $500 min",               "T"),
    ("Acanthoscurria maga",                  "Antilles Pink Patch",             "0.5",  None,  29.0,  1, "wholesale; 0.5in+; $500 min",       "T"),
    ("Aphonopelma bicoloratum",              "Mexican Bloodleg",                "0.5",  None,  35.0,  1, "wholesale; 0.5in+; $500 min",       "T"),
    ("Poecilotheria regalis",                "Indian Ornamental",               "2.0",  None,  45.0,  1, "wholesale; few; $500 min",          "T"),
    ("Theraphosa blondi",                    "Goliath Bird Eating",             "2.5",  None,  65.0,  1, "wholesale; 2-3 in; $500 min",       "T"),
]

# ---------------------------------------------------------------------------
# EMIL
# ---------------------------------------------------------------------------
EMIL_LISTINGS = [
    # Females
    ("Bonnetina minax",                      None,                              "1.25", "F",   65.0,  1, None,                        "T"),
    ("Eupalaestrus campestratus",            "Pink Zebra Beauty",               "1.25", "F",  100.0,  1, None,                        "T"),
    ("Thrixopelma pruriens",                 "Peruvian Green Velvet",           "5.0",  "F",  150.0,  1, "MF (mature female)",        "T"),
    ("Cyriopagopus lividus",                 "Cobalt Blue",                     "1.75", "F",   70.0,  1, None,                        "T"),
    ("Ornithoctoninae sp. Veronica",         "Veronica Dwarf",                  "3.0",  "F",  225.0,  1, None,                        "T"),
    ("Phormictopus sp.",                     None,                              "5.5",  "F",  150.0,  1, "unknown sp.",               "T"),
    # Males
    ("Caribena versicolor",                  "Antilles Pink Toe",               "2.75", "M",   75.0,  1, "2.5-3 in",                 "T"),
    ("Cyclosternum schmardae",               None,                              "2.5",  "M",   55.0,  1, None,                        "T"),
    ("Ephebopus cyanognathus",               "Blue Fang Skeleton",              "2.0",  "M",   65.0,  1, None,                        "T"),
    ("Euathlus truculentus",                 "Chilean Blue Femur",              "1.0",  "M",   70.0,  1, None,                        "T"),
    ("Grammostola pulchra",                  "Brazilian Black",                 "3.0",  "M",  120.0,  1, None,                        "T"),
    ("Monocentropus balfouri",               "Socotra Island Blue Baboon",      "3.0",  "M",   70.0,  1, None,                        "T"),
    ("Nhandu tripepii",                      "Brazilian Giant Blonde",          "2.5",  "M",   50.0,  1, None,                        "T"),
    ("Poecilotheria striata",                "Mysore Ornamental",               "3.0",  "M",   65.0,  1, None,                        "T"),
    ("Poecilotheria vittata",                "Ghost Ornamental",                "2.75", "M",   55.0,  1, "2.5-3 in; MO sales only",  "T"),
    ("Selenobrachys philippinus",            "Philippine Tangerine",            "4.0",  "M",   70.0,  1, None,                        "T"),
    ("Tliltocatl verdezi",                   "Mexican Grey Rose",               "2.5",  "M",   50.0,  1, None,                        "T"),
    ("Xenesthis intermedia",                 "Amazon Blue Bloom",               "4.25", "M",  130.0,  1, "4-4.5 in",                 "T"),
    # Unsexed
    ("Aphonopelma seemanni",                 "Costa Rican Stripe Knee",         "0.5",  None,  25.0,  1, None,                        "T"),
    ("Chilobrachys natanicharum",            "Electric Blue",                   "0.5",  None,  35.0,  1, None,                        "T"),
    ("Chromatopelma cyaneopubescens",        "Green Bottle Blue",               "0.75", None,  45.0,  1, None,                        "T"),
    ("Citharacanthus cyaneus",               "Cuban Dwarf Violet",              "0.875",None,  65.0,  1, "0.75-1 in",                "T"),
    ("Davus pentaloris",                     "Guatemalan Tiger Rump",           "0.5",  None,  25.0,  1, None,                        "T"),
    ("Dolichothele diamantinensis",          "Brazilian Blue Dwarf Beauty",     "0.875",None,  50.0,  1, "0.75-1 in",                "T"),
    ("Thrixopelma pruriens",                 "Peruvian Green Velvet",           "0.625",None,  35.0,  1, "0.5-0.75 in",              "T"),
    ("Nhandu tripepii",                      "Brazilian Giant Blonde",          "0.5",  None,  35.0,  1, None,                        "T"),
    ("Phlogiellus johnreylazoi",             None,                              "1.75", None,  50.0,  1, "1.5-2 in",                 "T"),
    ("Psalmopoeus cambridgei",               "Trinidad Chevron",                "0.75", None,  25.0,  1, None,                        "T"),
    ("Pterinochilus murinus",                "Orange Baboon",                   "0.625",None,  25.0,  1, "0.5-0.75 in",              "T"),
    ("Selenocosmia sp. Kordillera",          None,                              "1.375",None,  50.0,  1, "1.25-1.5 in",              "T"),
    ("Spinosatibiapalpus sp. Colombia y/b",  None,                              "0.25", None,  45.0,  1, "yellow/blue; wholesale avail","T"),
    ("Tliltocatl vagans",                    "Mexican Red Rump",                "1.125",None,  30.0,  1, "1-1.25 in",                "T"),
]

# ---------------------------------------------------------------------------
# AARON ROGERS
# ---------------------------------------------------------------------------
AARON_ROGERS = [
    # Females
    ("Birupes simoroxigorum",                "Borneo Neon Blue Leg",            "4.0",  "F",  350.0,  2, None,                        "T"),
    ("Bumba horrida",                        "Brazilian Red Head",              "3.0",  "F",  150.0,  1, None,                        "T"),
    ("Chilobrachys natanicharum",            "Electric Blue Earth Tiger",       "3.0",  "F",  125.0,  1, None,                        "T"),
    ("Chilobrachys sp. Kaeng Krachen",       "Dark Earth Tiger",                "4.0",  "F",  100.0,  1, None,                        "T"),
    ("Ephebopus uataman",                    "Emerald Skeleton",                "2.5",  "F",  140.0,  1, None,                        "T"),
    ("Guyruita cerrado",                     "Brazilian Savannah Dwarf",        "2.0",  "F",  150.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden-Knee",               "2.5",  "F",  100.0,  1, None,                        "T"),
    ("Hysterocrates gigas",                  "Cameroon Red Baboon",             "4.0",  "F",  145.0,  1, None,                        "T"),
    ("Heteroscodra maculata",                "Togo Starburst Baboon",           "5.0",  "F",  175.0,  1, None,                        "T"),
    ("Lasiocyaneo sazimai",                  "Brazilian Blue",                  "2.5",  "F",  150.0,  1, None,                        "T"),
    ("Orphnaecus sp. Quezon Blue",           "Quezon Blue Earth Tiger",         "3.5",  "F",  125.0,  1, None,                        "T"),
    ("Psalmopoeus cambridgei",               "Trinidad Chevron",                "2.5",  "F",  100.0,  1, None,                        "T"),
    ("Psalmopoeus reduncus",                 "Costa Rican Orange Mouth",        "4.0",  "F",  150.0,  1, None,                        "T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "2.5",  "F",   85.0,  1, None,                        "T"),
    ("Psalmopoeus victori",                  "Darth Maul",                      "2.75", "F",  230.0,  4, "2.5-3 in",                 "T"),
    ("Pterinochilus murinus",                "Orange Starburst Baboon",         "1.0",  "F",   75.0,  2, "1in+",                     "T"),
    ("Phormingochilus sp. Akcaya",           "Akcaya Earth Tiger",              "4.0",  "F",  250.0,  1, None,                        "T"),
    # Juvies
    ("Dolichothele diamantinensis",          "Brazilian Blue Dwarf Beauty",     "2.25", None,  85.0,  5, "juvie",                     "T"),
    ("Dolichothele rufoniger",               "Brazilian Purple Beauty",         "2.25", None, 125.0,  2, "juvie",                     "T"),
    ("Poecilotheria vittata",                "Ghost Ornamental",                "3.0",  None, 100.0,  4, "juvie",                     "T"),
    ("Psalmopoeus victori",                  "Darth Maul",                      "2.75", None,  85.0,  5, "juvie; 2.5-3 in",          "T"),
    # Well Started
    ("Birupes simoroxigorum",                "Borneo Neon Blue Leg",            "1.0",  None,  75.0,  4, "1in+",                     "T"),
    ("Dolichothele rufoniger",               "Brazilian Purple Beauty",         "1.0",  None,  85.0, 51, None,                        "T"),
    ("Ephebopus uataman",                    "Emerald Skeleton",                "1.5",  None,  65.0,  1, None,                        "T"),
    ("Harpactira pulchripes",                "Golden Blue-Legged Baboon",       "1.0",  None,  50.0, 19, None,                        "T"),
    ("Pterinochilus murinus",                "Orange Starburst Baboon",         "1.0",  None,  40.0,  7, "1in+",                     "T"),
    ("Phormingochilus hati hati",            "Borneo Purple Earth Tiger",       "1.0",  None,  40.0,  5, None,                        "T"),
    ("Psalmopoeus cambridgei",               "Trinidad Chevron",                "2.5",  None,  45.0,  2, None,                        "T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "2.5",  None,  45.0,  1, None,                        "T"),
    ("Selenobrachys philippinus",            "Philippine Tangerine",            "1.0",  None,  45.0,  4, None,                        "T"),
    # Slings
    ("Aphonopelma seemanni",                 "Costa Rican Zebra Knee",          "0.5",  None,  20.0,  7, None,                        "T"),
    ("Caribena versicolor",                  "Antilles Pink Toe",               "0.33", None,  40.0,  5, None,                        "T"),
    ("Chilobrachys natanicharum",            "Electric Blue Earth Tiger",       "0.75", None,  25.0, 20, None,                        "T"),
    ("Cyriocosmus elegans",                  "Trinidad Dwarf",                  "0.33", None,  40.0,  6, None,                        "T"),
    ("Dolichothele rufoniger",               "Brazilian Purple Beauty",         "0.5",  None,  75.0, 10, None,                        "T"),
    ("Dolichothele mineirum",                "Brazilian Black Dwarf Beauty",    "0.75", None,  80.0,  5, None,                        "T"),
    ("Ephebopus rufescens",                  "Red Skeleton",                    "0.75", None,  55.0,  1, None,                        "T"),
    ("Lasiocyaneo sazimai",                  "Brazilian Blue",                  "0.25", None,  20.0,  5, None,                        "T"),
    ("Psalmopoeus cambridgei",               "Trinidad Chevron",                "0.75", None,  25.0, 20, None,                        "T"),
    ("Pterinochilus murinus",                "Kigoma Baboon",                   "0.5",  None,  30.0,  6, "Kigoma locale",             "T"),
    ("Tliltocatl albopilosus",               "Curly Hair",                      "0.5",  None,  15.0,  1, None,                        "T"),
    # Males
    ("Avicularia bicegoi",                   "Brazilian Wooly Pink-Toe",        "4.0",  "M",  150.0,  1, "penultimate?",              "T"),
    ("Dolichothele diamantinensis",          "Brazilian Blue Dwarf Beauty",     "2.25", "M",   50.0,  9, None,                        "T"),
    ("Dolichothele rufoniger",               "Brazilian Purple Beauty",         "2.25", "M",   75.0,  2, None,                        "T"),
    ("Heteroscodra maculata",                "Togo Starburst Baboon",           "3.5",  "M",   50.0,  2, None,                        "T"),
    ("Psalmopoeus victori",                  "Darth Maul",                      "2.75", "M",   65.0,  5, "2.5-3 in",                 "T"),
    ("Psalmopoeus cambridgei",               "Trinidad Chevron",                "2.5",  "M",   40.0,  2, None,                        "T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "2.5",  "M",   40.0,  1, None,                        "T"),
    ("Theraphosinae sp. Roatan",             "Roatan Island Purple",            "2.5",  "M",   80.0,  1, None,                        "T"),
    ("Poecilotheria hanumavilasumica",       "Rameshwaram Ornamental",          "4.0",  "M",  125.0,  1, None,                        "T"),
    ("Xenesthis intermedia",                 "Amazon Blue Bloom",               "6.0",  "M",  150.0,  1, "penultimate?",              "T"),
    ("Linothele fallax",                     "Tiger Funnel Web",                "2.5",  "F",  140.0,  1, None,                        "S"),
]

# ---------------------------------------------------------------------------
# JUSTIN ARRAS
# ---------------------------------------------------------------------------
JUSTIN_ARRAS = [
    ("Stromatopelma calceatum",              "Featherleg Baboon",               "1.25", None,  30.0,  1, "1-1.5 in",                 "T"),
    ("Pterinochilus murinus",                "Orange Baboon",                   "1.0",  None,  35.0,  1, None,                        "T"),
    ("Psalmopoeus pulcher",                  "Panama Blonde",                   None,   None,  30.0,  1, None,                        "T"),
    ("Hapalopus formosus",                   "Pumpkin Patch",                   None,   None,  35.0,  1, None,                        "T"),
    ("Heterothele villosella",               None,                              None,   None,  25.0,  1, None,                        "T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "0.625",None,  35.0,  1, "0.5-0.75 in",              "T"),
    ("Tliltocatl kahlenbergi",               "Veracruz Red Rump",              None,   None,  25.0,  1, None,                        "T"),
    ("Heteroscodra maculata",                "Togo Starburst Baboon",           "0.33", None,  25.0,  1, None,                        "T"),
    ("Pterinochilus lugardi",                "Dodoma Baboon",                   None,   None,  30.0,  1, None,                        "T"),
    ("Holothele longipes",                   "Trinidad Pink",                   None,   None,  30.0,  1, None,                        "T"),
    ("Acanthoscurria geniculata",            "Brazilian White Knee",            "1.25", None,  45.0,  1, None,                        "T"),
    ("Hapalopus guerreroi",                  "Guerrero Pumpkin Patch",          None,   None,  45.0,  1, None,                        "T"),
    ("Amazonius germani",                    "Orange Tree Spider",              None,   None,  40.0,  1, None,                        "T"),
    ("Psalmopoeus victori",                  "Darth Maul",                      None,   None,  60.0,  1, None,                        "T"),
    ("Lasiodora parahybana",                 "Brazilian Salmon Pink",           "0.5",  None,  25.0,  1, None,                        "T"),
    ("Neoholothele incei",                   "Trinidad Olive",                  "0.875",None,  35.0,  1, "0.75-1 in",                "T"),
    ("Augacephalus rufus",                   "Peach Earth Tiger",               "0.875",None,  40.0,  1, "0.75-1 in",                "T"),
]

# ---------------------------------------------------------------------------
# UNNAMED WHOLESALE (10-pack pricing, converted to per-unit)
# ---------------------------------------------------------------------------
UNNAMED_WHOLESALE = [
    ("Amazonius germani",                    "Orange Tree Spider",              "0.625",None,  15.0, 10, "wholesale; 10/$150; 0.5-0.75 in","T"),
    ("Lasiodora parahybana",                 "Brazilian Salmon Pink",           "0.375",None,  10.0, 10, "wholesale; 10/$100; 0.25-0.5 in","T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "0.625",None,  12.5, 10, "wholesale; 10/$125; 0.5-0.75 in","T"),
    ("Tliltocatl vagans",                    "Mexican Red Rump",                "0.5",  None,  10.0, 10, "wholesale; 10/$100",            "T"),
]

# ---------------------------------------------------------------------------
# THE SPIDER ROOM — REFERENCE LIST (tarantulas)
# ---------------------------------------------------------------------------
SPIDER_ROOM_REF = [
    ("Acanthoscurria geniculata",            "Brazilian White Knee",            "2.0",  None,  46.0,  1, None,                        "T"),
    ("Acanthoscurria maga",                  "Antilles Pink Patch",             "0.25", None,  31.0,  1, None,                        "T"),
    ("Amazonius germani",                    "Orange Tree Spider",              "0.75", None,  25.0,  1, None,                        "T"),
    ("Anqasha minaperinensis",               "Mina Perina Tiger",               "0.25", None, 121.0,  1, None,                        "T"),
    ("Anqasha sp. Canto",                    None,                              "0.33", None, 115.0,  1, None,                        "T"),
    ("Antikuna sp. Fenix",                   "Andes Purple Flame",              "0.5",  None, 151.0,  1, None,                        "T"),
    ("Aphonopelma bicoloratum",              "Mexican Blood Leg",               "0.25", None,  34.0,  1, None,                        "T"),
    ("Aphonopelma bicoloratum",              "Mexican Blood Leg",               "1.375",None,  94.0,  1, "1.25-1.5 in",              "T"),
    ("Aphonopelma crinirufum",               "Costa Rican Blue Front",          "0.25", None,  31.0,  1, None,                        "T"),
    ("Aphonopelma moderatum",                "Rio Grande Gold",                 "2.5",  None,  85.0,  1, "WC; 2-3 in",               "T"),
    ("Aphonopelma seemanni",                 "Costa Rican Stripe Knee",         "0.5",  None,  22.0,  1, None,                        "T"),
    ("Aspinochilus rufus",                   "Peach Earth Tiger",               "0.5",  None,  25.0,  1, None,                        "T"),
    ("Augacephalus junodi",                  "Golden Baboon",                   "1.25", None, 154.0,  1, "1-1.5 in",                 "T"),
    ("Avicularia avicularia",                "Guyana Pink Toe",                 "0.5",  None,  33.0,  1, "M1 locale",                 "T"),
    ("Avicularia avicularia",                "Guyana Pink Toe (WC)",            "1.5",  None,  25.0,  1, "M1 WC; 1-2 in",            "T"),
    ("Avicularia avicularia",                "Guyana Pink Toe (WC)",            "2.5",  None,  31.0,  1, "M1 WC; 2-3 in",            "T"),
    ("Avicularia avicularia",                "Metallic Pink Toe",               "1.125",None,  57.0,  1, "M6 locale; 1-1.25 in",     "T"),
    ("Avicularia huriana",                   "Ecuadorian Wooly Pink Toe",       "1.0",  None, 105.0,  1, None,                        "T"),
    ("Avicularia merianae",                  "Peruvian Cinnamon Pink Toe",      "0.625",None,  61.0,  1, "0.5-0.75 in",              "T"),
    ("Birupes simoroxigorum",                "Bornean Neon Blue Leg",           "0.875",None,  69.0,  1, "0.75-1 in",                "T"),
    ("Bonnetina tanzeri",                    "Michoacan Red Rump",              "1.375",None,  71.0,  1, "1.25-1.5 in",              "T"),
    ("Brachinopus sp. Limpopo",              "Limpopo Dwarf",                   "1.0",  None,  53.0,  1, None,                        "T"),
    ("Brachypelma albiceps",                 "Mexican Golden Red Rump",         "0.25", None,  28.0,  1, None,                        "T"),
    ("Brachypelma albiceps",                 "Mexican Golden Red Rump",         "1.5",  None,  71.0,  1, None,                        "T"),
    ("Brachypelma auratum",                  "Mexican Flame Knee",              "1.5",  None, 101.0,  1, None,                        "T"),
    ("Brachypelma auratum",                  "Mexican Flame Knee",              "2.5",  "F",  235.0,  1, "2-3 in",                   "T"),
    ("Brachypelma baumgarteni",              "Mexican Orange Beauty",           "1.5",  None, 131.0,  1, None,                        "T"),
    ("Brachypelma boehmei",                  "Mexican Fire Leg",                "1.5",  None,  40.0,  1, None,                        "T"),
    ("Brachypelma emilia",                   "Mexican Red Leg",                 "0.5",  None,  46.0,  1, None,                        "T"),
    ("Brachypelma emilia",                   "Mexican Red Leg",                 "1.5",  None,  71.0,  1, None,                        "T"),
    ("Brachypelma hamorii",                  "Mexican Red Knee",                "0.25", None,  31.0,  1, None,                        "T"),
    ("Brachypelma hamorii",                  "Mexican Red Knee",                "1.5",  None,  43.0,  1, None,                        "T"),
    ("Brachypelma klaasi",                   "Mexican Pink",                    "1.5",  None, 116.0,  1, None,                        "T"),
    ("Brachypelma smithi",                   "Mexican Giant Red Knee",          "1.5",  None,  87.0,  1, None,                        "T"),
    ("Bumba horrida",                        "Brazilian Red Head",              "1.375",None,  49.0,  1, "1.25-1.5 in",              "T"),
    ("Caribena laeta",                       "Puerto Rican Pink Toe",           "0.5",  None,  28.0,  1, None,                        "T"),
    ("Catumiri argentinense",                "Dwarf Argentine Bronze",          "0.25", None,  25.0,  1, None,                        "T"),
    ("Ceratogyrus brachycephalus",           "Greater Horned Baboon",           "0.5",  None,  34.0,  1, None,                        "T"),
    ("Ceratogyrus darlingi",                 "Rear Horned Baboon",              "1.5",  None,  49.0,  1, None,                        "T"),
    ("Ceratogyrus marshalli",                "Straight Horned Baboon",          "0.5",  None,  22.0,  1, None,                        "T"),
    ("Ceratogyrus marshalli",                "Straight Horned Baboon",          "1.5",  None,  49.0,  1, None,                        "T"),
    ("Ceratogyrus meridionalis",             "Zimbabwe Grey Baboon",            "0.5",  None,  25.0,  1, None,                        "T"),
    ("Ceratogyrus sanderi",                  "Namibia Horned Baboon",           "0.5",  None,  34.0,  1, None,                        "T"),
    ("Chaetopelma olivaceum",                "Middle East Gold",                "1.0",  None,  31.0,  1, None,                        "T"),
    ("Chilobrachys dyscolus",                "Vietnam Blue",                    "0.5",  None,  22.0,  1, None,                        "T"),
    ("Chilobrachys fimbriatus",              "Indian Violet",                   "0.625",None,  31.0,  1, "0.5-0.75 in",              "T"),
    ("Chilobrachys fimbriatus",              "Indian Violet",                   "1.25", None,  37.0,  1, None,                        "T"),
    ("Chilobrachys huahini",                 "Asian Giant Fawn",                "0.5",  None,  19.0,  1, None,                        "T"),
    ("Chilobrachys natanicharum",            "Electric Blue",                   "0.75", None,  22.0,  1, None,                        "T"),
    ("Chilobrachys sp. Kaeng Krachen",       "Dark Earth Tiger",                "0.5",  None,  25.0,  1, None,                        "T"),
    ("Chilobrachys sp. Kaeng Krachen",       "Dark Earth Tiger",                "1.25", None,  31.0,  1, "1-1.5 in",                 "T"),
    ("Chilobrachys sp. Saraburi",            "Saraburi Earth Tiger",            "0.5",  None,  31.0,  1, None,                        "T"),
    ("Chromatopelma cyaneopubescens",        "Green Bottle Blue",               "1.0",  None,  46.0,  1, None,                        "T"),
    ("Chromatopelma cyaneopubescens",        "Green Bottle Blue",               "1.5",  None,  94.0,  1, None,                        "T"),
    ("Cilantica sp. Kali",                   "Kali Earth Tiger",                "0.75", None,  97.0,  1, None,                        "T"),
    ("Citharacanthus cyaneus",               "Cuban Dwarf Violet",              "0.5",  None,  70.0,  1, None,                        "T"),
    ("Coremiocnemis hoggi",                  "Malaysia Purple Femur",           "1.0",  None,  67.0,  1, None,                        "T"),
    ("Cyclosternum sp. Aureum",              "Blue Lightning",                  "0.25", None,  58.0,  1, None,                        "T"),
    ("Cyriocosmus aueri",                    "Peruvian Dwarf Red Leg",          "0.125",None,  34.0,  1, None,                        "T"),
    ("Cyriocosmus elegans",                  "Trinidad Dwarf Beauty",           "0.125",None,  22.0,  1, None,                        "T"),
    ("Cyriocosmus leetzi",                   "Colombian Dwarf",                 "0.25", None,  49.0,  1, None,                        "T"),
    ("Cyriocosmus perezmilesi",              "Bolivian Dwarf Beauty",           "0.25", None,  40.0,  1, None,                        "T"),
    ("Cyriocosmus ritae",                    "Peruvian Black White",            "0.25", None,  91.0,  1, None,                        "T"),
    ("Cyriocosmus sp. Oronegro",             "Black & Gold Dwarf",              "0.125",None,  58.0,  1, None,                        "T"),
    ("Cyriocosmus sp. Pinturas",             None,                              "0.25", None,  52.0,  1, None,                        "T"),
    ("Cyriocosmus sp. Primavera",            None,                              "0.25", None,  55.0,  1, None,                        "T"),
    ("Cyriopagopus robustus",                "Malaysian Blue Femur",            "0.75", None,  91.0,  1, None,                        "T"),
    ("Cyriopagopus sp. Bach Ma",             "Bach Ma Earth Tiger",             "1.25", None,  40.0,  1, None,                        "T"),
    ("Cyriopagopus sp. Bach Ma",             "Bach Ma Earth Tiger",             "2.0",  None,  52.0,  1, None,                        "T"),
    ("Cyriopagopus sp. Lam Dong",            "Lam Dong Earth Tiger",            "1.0",  None,  40.0,  1, None,                        "T"),
    ("Cyrtopholis sp. Peravia",              None,                              "1.0",  None,  58.0,  1, None,                        "T"),
    ("Davus pentaloris",                     "Guatemalan Tiger Rump",           "0.25", None,  19.0,  1, None,                        "T"),
    ("Davus pentaloris",                     "Guatemalan Tiger Rump",           "1.5",  None,  57.0,  1, None,                        "T"),
    ("Davus pentaloris",                     "Guatemalan Tiger Rump",           "2.0",  "F",  100.0,  1, None,                        "T"),
    ("Davus sp. Panama",                     "Lava Tarantula",                  "0.375",None, 124.0,  1, "0.25-0.5 in",              "T"),
    ("Devicarina guidonae",                  "Saffron Dwarf Pumpkin",           "0.1875",None,416.0, 1, "0.125-0.25 in",             "T"),
    ("Dolichothele exilis",                  "Exilis Bronze",                   "0.375",None,  32.0,  1, "0.25-0.5 in",              "T"),
    ("Ephebopus cyanognathus",               "Blue Fang",                       "0.75", None,  55.0,  1, None,                        "T"),
    ("Ephebopus murinus",                    "Skeleton Tarantula",              "0.75", None,  61.0,  1, None,                        "T"),
    ("Euathlus manicata",                    "Chilean Black Burst",             "0.5",  None,  94.0,  1, "Black form",                "T"),
    ("Euathlus manicata",                    "Chilean Green",                   "0.5",  None,  85.0,  1, "Green form",                "T"),
    ("Euathlus sp. Bronce",                  "Chilean Bronze",                  "0.375",None, 163.0,  1, "0.25-0.5 in",              "T"),
    ("Euathlus sp. Hermosa",                 "Chilean Emerald Beauty",          "0.375",None, 132.0,  1, "0.25-0.5 in",              "T"),
    ("Euathlus sp. Smarged Tiger",           "Chilean Emerald Tiger",           "0.375",None, 279.0,  1, "0.25-0.5 in",              "T"),
    ("Euathlus truculentus",                 "Chilean Blue Femur",              "0.5",  None,  86.0,  1, "Blue form",                 "T"),
    ("Euathlus valparaiso",                  "Valparaiso Tarantula",            "0.33", None,  46.0,  1, None,                        "T"),
    ("Eupalaestrus larae",                   "Golden Zebra Beauty",             "0.25", None,  58.0,  1, None,                        "T"),
    ("Thrixopelma pruriens",                 "Peruvian Green Velvet",           "0.25", None,  22.0,  1, "listed as Ewok pruriens",   "T"),
    ("Grammostola grossa",                   "Guarani Giant",                   "0.75", None,  91.0,  1, None,                        "T"),
    ("Grammostola grossa",                   "Guarani Giant",                   "1.5",  None, 101.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden Knee",               "0.5",  None,  31.0,  1, None,                        "T"),
    ("Grammostola pulchripes",               "Chaco Golden Knee",               "1.5",  None,  71.0,  1, None,                        "T"),
    ("Grammostola quirogai",                 "Uruguayan Black",                 "0.875",None,  61.0,  1, "0.75-1 in",                "T"),
    ("Grammostola rosea",                    "Common Rose Hair NCF",            "0.5",  None,  40.0,  1, "NCF",                       "T"),
    ("Grammostola rosea",                    "Common Rose Hair NCF",            "1.5",  None,  78.0,  1, "NCF",                       "T"),
    ("Grammostola rosea",                    "Rose Hair RCF",                   "0.33", None,  40.0,  1, "RCF",                       "T"),
    ("Grammostola rosea",                    "Rose Hair RCF",                   "1.5",  None,  71.0,  1, "RCF",                       "T"),
    ("Hapalopus formosus",                   "Pumpkin Patch",                   "0.25", None,  22.0,  1, None,                        "T"),
    ("Hapalopus guerreroi",                  "Guerrero Pumpkin Patch",          "0.33", None,  37.0,  1, None,                        "T"),
    ("Hapalopus sp. Bolivar",                "Bolivar Pumpkin Patch",           "0.25", None,  71.0,  1, None,                        "T"),
    ("Hapalotremus hananqheswa",             "High Valley Blue",                "0.25", None, 128.0,  1, None,                        "T"),
    ("Hapalotremus major",                   "Urubamba Giant",                  "0.25", None,  85.0,  1, None,                        "T"),
    ("Hapalotremus sp. Inca Gold",           "Inca Gold",                       "0.5",  None,  70.0,  1, None,                        "T"),
    ("Hapalotremus sp. Puma",                None,                              "0.75", None,  76.0,  1, None,                        "T"),
    ("Haplocosmia himalayana",               "Himalayan Beauty",                "0.5",  None,  43.0,  1, None,                        "T"),
    ("Harpactira namaquensis",               "Bronze Baboon",                   "1.25", None,  52.0,  1, "1-1.5 in",                 "T"),
    ("Harpactira pulchripes",                "Golden Blue Leg Baboon",          "0.625",None,  49.0,  1, "0.5-0.75 in",              "T"),
    ("Harpactira pulchripes",                "Golden Blue Leg Baboon",          "2.5",  "F",  154.0,  1, "2-3 in",                   "T"),
    ("Heteroscodra maculata",                "Togo Starburst",                  "0.5",  None,  22.0,  1, None,                        "T"),
    ("Heterothele gabonensis",               "Gabon Blue Dwarf",                "0.25", None,  37.0,  1, None,                        "T"),
    ("Heterothele sp. villasella",           "Tanzanian Chestnut Baboon",       "1.0",  None,  28.0,  1, None,                        "T"),
    ("Heterothele sp. villasella",           "Tanzanian Chestnut Baboon",       "1.75", "F",   61.0,  1, "1.5-2 in",                 "T"),
    ("Holothele longipes",                   "Trinidad Pink",                   "0.5",  None,  22.0,  1, None,                        "T"),
    ("Homoeomma chilense",                   "Chilean Flame",                   "0.25", None,  73.0,  1, None,                        "T"),
    ("Homoeomma orellanai",                  "Chilean Yellow Flame",            "0.25", None,  73.0,  1, None,                        "T"),
    ("Hysterocrates gigas",                  "Cameroon Red Baboon",             "1.5",  None,  28.0,  1, None,                        "T"),
    ("Idiothele mira",                       "Blue Leg Baboon",                 "0.5",  None,  49.0,  1, None,                        "T"),
    ("Iridopelma hirsutum",                  "Amazon Ribbed",                   "0.875",None, 131.0,  1, "0.75-1 in",                "T"),
    ("Ischnocolus jickelii",                 "Dhofar Blue Dwarf",               "0.875",None, 120.0,  1, "Blue; 0.75-1 in",          "T"),
    ("Ischnocolus vanandelae",               "Oman Gold",                       "1.0",  None,  57.0,  1, None,                        "T"),
    ("Kochiana brunnipes",                   "Dwarf Pink Leg",                  "0.125",None,  19.0,  1, None,                        "T"),
    ("Lasiocyaneo sazimai",                  "Brazilian Blue",                  "0.25", None,  19.0,  1, None,                        "T"),
    ("Lasiocyaneo sazimai",                  "Brazilian Blue",                  "0.75", None,  28.0,  1, None,                        "T"),
    ("Lasiocyaneo sazimai",                  "Brazilian Blue",                  "1.5",  None,  45.0,  1, None,                        "T"),
    ("Lasiodora klugi",                      "Bahia Scarlet",                   "0.5",  None,  22.0,  1, None,                        "T"),
    ("Lasiodora parahybana",                 "Brazilian Salmon Pink",           "0.25", None,  19.0,  1, None,                        "T"),
    ("Lasiodora parahybana",                 "Brazilian Salmon Pink",           "1.5",  None,  31.0,  1, None,                        "T"),
    ("Lasiodorides polycuspulatus",          "Peruvian Blonde",                 "0.5",  None,  31.0,  1, None,                        "T"),
    ("Lasiodorides polycuspulatus",          "Peruvian Blonde",                 "1.0",  None,  46.0,  1, None,                        "T"),
    ("Magnacrus taynguyenensis",             "Vietnam Highland",                "1.5",  None,  61.0,  1, None,                        "T"),
    ("Magnacrus tongmianensis",              "Chinese Stout Leg",               "1.5",  None,  55.0,  1, None,                        "T"),
    ("Megaphobema robustum",                 "Colombian Red Leg",               "1.0",  None,  43.0,  1, None,                        "T"),
    ("Megaphobema robustum",                 "Colombian Red Leg",               "4.5",  None, 117.0,  1, "4-5 in",                   "T"),
    ("Megaphobema sp. White",                "Colombian Giant White Leg",       "1.25", None,  85.0,  1, None,                        "T"),
    ("Megaphobema velvetosoma",              "Ecuadorian Brown Velvet",         "1.25", None,  73.0,  1, "1-1.5 in",                 "T"),
    ("Melapoeus albostriatus",               "Thai Zebra",                      "0.5",  None,  30.0,  1, None,                        "T"),
    ("Melapoeus albostriatus",               "Thai Zebra",                      "0.5",  None,  25.0,  1, "Nahkon Ratchasima locale", "T"),
    ("Melapoeus albostriatus",               "Thai Purple Zebra",               "0.5",  None,  34.0,  1, "Purple Zebra form",         "T"),
    ("Melapoeus cf. schmidti",               "Phong Nha-Ke Bang",              "1.25", None,  55.0,  1, "1-1.5 in",                 "T"),
    ("Melapoeus lividus",                    "Cobalt Blue",                     "0.5",  None,  28.0,  1, None,                        "T"),
    ("Melapoeus lividus",                    "Cobalt Blue (WC)",                "4.0",  "F",   76.0,  1, "WC",                        "T"),
    ("Melapoeus minax",                      "Thai Earth Tiger",                "1.25", None,  37.0,  1, "Big Black; 1-1.5 in",      "T"),
    ("Melapoeus sp. Nhen Dep",               "Nhen Dep Earth Tiger",            "1.5",  None,  69.0,  1, None,                        "T"),
    ("Monocentropus balfouri",               "Socotra Island Blue",             "0.5",  None,  37.0,  1, None,                        "T"),
    ("Monocentropus balfouri",               "Socotra Island Blue",             "1.25", None,  52.0,  1, "1-1.5 in",                 "T"),
    ("Monocentropus balfouri",               "Socotra Island Blue",             "2.5",  None,  58.0,  1, "2-3 in",                   "T"),
    ("Monocentropus balfouri",               "Socotra Island Blue",             "4.0",  "F",  166.0,  1, None,                        "T"),
    ("Neischnocolus panamanus",              "Panama Green",                    "0.125",None,  37.0,  1, None,                        "T"),
    ("Neoholothele incei",                   "Trinidad Olive",                  "1.25", None,  31.0,  1, "1-1.5 in",                 "T"),
    ("Neoholothele incei",                   "Trinidad Olive Gold",             "1.5",  None,  40.0,  1, "Gold form",                 "T"),
    ("Neostenotarsus sp. Suriname",          "Suriname Dwarf",                  "0.125",None,  70.0,  1, None,                        "T"),
    ("Nhandu carapoensis",                   "Brazilian Red",                   "1.0",  None,  37.0,  1, None,                        "T"),
    ("Nhandu carapoensis",                   "Brazilian Red",                   "1.5",  None,  79.0,  1, None,                        "T"),
    ("Nhandu coloratovillosus",              "Brazilian White Banded",          "0.25", None,  22.0,  1, None,                        "T"),
    ("Nhandu coloratovillosus",              "Brazilian White Banded",          "1.5",  None,  71.0,  1, None,                        "T"),
    ("Nhandu tripepii",                      "Brazilian Giant Blonde",          "1.5",  None,  64.0,  1, None,                        "T"),
    ("Omothymus schioedtei",                 "Malaysian Earth Tiger",           "1.0",  None,  40.0,  1, None,                        "T"),
    ("Omothymus sp. Magnus",                 "Magnus Earth Tiger",              "1.25", None, 121.0,  1, "1-1.5 in",                 "T"),
    ("Omothymus sp. Valhalla",               "Valhalla Earth Tiger",            "1.5",  None, 182.0,  1, None,                        "T"),
    ("Omothymus violaceopes",                "Singapore Blue",                  "0.75", None,  37.0,  1, None,                        "T"),
    ("Ornithoctoninae sp. Haribon",          "Philippine Eagle",                "0.75", None, 124.0,  1, None,                        "T"),
    ("Ornithoctoninae sp. Long Na",          "Long Na Earth Tiger",             "1.5",  None,  52.0,  1, None,                        "T"),
    ("Ornithoctoninae sp. Phan Cay Blue",    "Cobalt Tree Spider",              "1.25", None, 105.0,  1, "1-1.5 in",                 "T"),
    ("Ornithoctoninae sp. Phan Cay Red",     "Purple Blaze Tree Spider",        "0.75", None, 105.0,  1, None,                        "T"),
    ("Ornithoctoninae sp. Ranong Blue",      "Ranong Blue Earth Tiger",         "0.5",  None,  40.0,  1, None,                        "T"),
    ("Ornithoctoninae sp. Vietnam Silver",   "Vietnam Silver",                  "0.875",None,  60.0,  1, "0.75-1 in",                "T"),
    ("Ornithoctoninae sp. Vietnam Silver",   "Vietnam Silver",                  "1.5",  None,  68.0,  1, None,                        "T"),
    ("Ornithoctonus aureotibialis",          "Thai Golden Fringe",              "0.5",  None,  31.0,  1, None,                        "T"),
    ("Orphnaecus dichromatus",               "New Guinea Two-Toned Earth Tiger","0.5",  None,  34.0,  1, None,                        "T"),
    ("Orphnaecus sp. Kordillera",            "Kordillera Blue",                 "0.5",  None,  34.0,  1, None,                        "T"),
    ("Orphnaecus sp. Marinduque Purple",     "Marinduque Purple",               "0.5",  None,  31.0,  1, None,                        "T"),
    ("Orphnaecus sp. Negros",               "Negros Island Earth Tiger",        "0.5",  None,  31.0,  1, None,                        "T"),
    ("Orphnaecus sp. Quezon Blue",           "Quezon Blue",                     "0.5",  None,  28.0,  1, None,                        "T"),
    ("Pamphobeteus cf. antinous",            "Big Black",                       "1.75", None, 106.0,  1, "1.5-2 in",                 "T"),
    ("Pamphobeteus cf. insignis",            None,                              "0.75", None,  76.0,  1, "Ecuador",                   "T"),
    ("Pamphobeteus fortis",                  "Colombian Giant Copperhead",      "1.5",  None,  91.0,  1, None,                        "T"),
    ("Pamphobeteus nigricolor",              "Colombian Blue Birdeater",        "1.5",  None, 101.0,  1, None,                        "T"),
    ("Pamphobeteus sp. Cascada",             "Cascada Giant Bird Eater",        "1.0",  None,  61.0,  1, None,                        "T"),
    ("Pamphobeteus sp. Flammifera",          "Flame-Bearing Bird Eater",        "1.0",  None,  76.0,  1, None,                        "T"),
    ("Pamphobeteus sp. Machala",             "Purple Starburst Bird Eater",     "2.0",  None,  76.0,  1, None,                        "T"),
    ("Pamphobeteus sp. Manganegra",          "Manganegra Bird Eater",           "0.75", None,  61.0,  1, None,                        "T"),
    ("Pamphobeteus sp. Mascara",             "Mascara Bird Eater",              "1.5",  None,  86.0,  1, None,                        "T"),
    ("Pamphobeteus sp. Platyomma",           "Pink Bloom",                      "1.5",  None,  86.0,  1, None,                        "T"),
    ("Pamphobeteus sp. Tigris",              "Ecuadorian Black Bird Eater",     "0.75", None,  73.0,  1, None,                        "T"),
    ("Pelinobius muticus",                   "King Baboon",                     "0.75", None,  34.0,  1, None,                        "T"),
    ("Phormictopus atrichomatus",            "Red Island",                      "0.75", None,  40.0,  1, None,                        "T"),
    ("Phormictopus auratus",                 "Cuban Bronze",                    "1.0",  None,  31.0,  1, None,                        "T"),
    ("Phormictopus auratus",                 "Cuban Bronze",                    "1.75", None,  46.0,  1, "1.5-2 in",                 "T"),
    ("Phormictopus cancerides",              "Haitian Brown",                   "0.75", None,  34.0,  1, None,                        "T"),
    ("Phormictopus sp. Full Green",          "Dominican Full Green",            "0.875",None,  94.0,  1, "0.75-1 in",                "T"),
    ("Phormictopus sp. Green Gold Carapace", "Hispaniola Giant Green & Gold",   "0.75", None,  58.0,  1, None,                        "T"),
    ("Phormictopus sp. Sierra de Bahoruco",  "Midnight Nebula Birdeater",       "1.0",  None, 121.0,  1, None,                        "T"),
    ("Phormictopus sp. South Hispaniola",    "Hispaniola Green Femur",          "5.0",  "F",  400.0,  1, None,                        "T"),
    ("Phormingochilus arboricola",           "Borneo Black",                    "0.5",  None,  25.0,  1, None,                        "T"),
    ("Phormingochilus everetti",             "Sarawak Red Tiger",               "0.75", None,  76.0,  1, None,                        "T"),
    ("Phormingochilus hati hati",            "Borneo Purple Earth Tiger",       "0.75", None,  28.0,  1, None,                        "T"),
    ("Phormingochilus hati hati",            "Borneo Purple Earth Tiger",       "1.5",  None,  37.0,  1, None,                        "T"),
    ("Phormingochilus sp. Akcaya",           "Indo Bat Eater",                  "1.25", None,  57.0,  1, "1-1.5 in",                 "T"),
    ("Phrixotrichus vulpinus",               "Chilean Ocelot",                  "0.5",  None,  91.0,  1, None,                        "T"),
    ("Plesiopelma longisternale",            "Argentine Dwarf Flame Rump",      "0.25", None,  31.0,  1, None,                        "T"),
    ("Poecilotheria metallica",              "Gooty Sapphire",                  "2.5",  None, 131.0,  1, "2-3 in",                   "T"),
    ("Poecilotheria metallica",              "Gooty Sapphire",                  "4.0",  "F",  361.0,  1, None,                        "T"),
    ("Poecilotheria tigrinawesseli",         "Tiger Ornamental",                "2.5",  None, 120.0,  1, "2-3 in",                   "T"),
    ("Psalmopoeus cambridgei",               "Trinidad Chevron",                "0.5",  None,  19.0,  1, None,                        "T"),
    ("Psalmopoeus irminia",                  "Venezuelan Sun Tiger",            "0.5",  None,  25.0,  1, None,                        "T"),
    ("Psalmopoeus pulcher",                  "Panama Blonde",                   "0.5",  None,  22.0,  1, None,                        "T"),
    ("Psalmopoeus reduncus",                 "Costa Rican Orange Mouth",        "0.5",  None,  24.0,  1, None,                        "T"),
    ("Psalmopoeus victori",                  "Darth Maul",                      "0.5",  None,  40.0,  1, None,                        "T"),
    ("Pseudhapalopus sp. Kurzhaar",          "Short Haired Tarantula",          "0.75", None,  37.0,  1, None,                        "T"),
    ("Pseudhapalopus sp. Kurzhaar",          "Short Haired Tarantula",          "2.0",  None,  97.0,  1, None,                        "T"),
    ("Pseudnocnemis brachyramosa",           "Malaysian Blue Femur",            "0.5",  None,  70.0,  1, None,                        "T"),
    ("Pterinochilus chordatus",              "Kilimanjaro Mustard",             "0.5",  None,  31.0,  1, None,                        "T"),
    ("Pterinochilus lugardi",                "Dodoma Baboon",                   "0.5",  None,  25.0,  1, None,                        "T"),
    ("Pterinochilus murinus",                "Kigoma Starburst",                "1.0",  None,  31.0,  1, "Kigoma locale",             "T"),
    ("Pterinochilus murinus",                "No Common Name (TCF)",            "0.75", None,  25.0,  1, "TCF locale",                "T"),
    ("Pterinochilus murinus",                "Orange Starburst Baboon",         "2.125",None,  40.0,  1, "Usambara; 2-2.25 in",      "T"),
    ("Selenobrachys philippinus",            "Philippine Orange",               "0.5",  None,  28.0,  1, None,                        "T"),
    ("Selenocosmia arndsti",                 "New Guinea Rust Orange",          "0.25", None,  46.0,  1, None,                        "T"),
    ("Selenocosmiinae sp. Romblon Pink",     "Romblon Pink",                    "0.75", None,  46.0,  1, None,                        "T"),
    ("Sericopelma melanotarsum",             "Coffee Tarantula",                "0.625",None, 115.0,  1, "0.5-0.75 in",              "T"),
    ("Sericopelma rubronitens",              "Panama Red Rump",                 "1.5",  None,  71.0,  1, None,                        "T"),
    ("Sericopelma sp. Azuero",               None,                              "0.75", None,  76.0,  1, None,                        "T"),
    ("Sericopelma sp. Darien",               "Darien Black Birdeater",          "1.5",  None, 105.0,  1, None,                        "T"),
    ("Sericopelma sp. Santa Catalina",       "Santa Catalina Bird Eater",       "1.0",  None,  70.0,  1, None,                        "T"),
    ("Spinosatibiapalpus sp. Blue",          "Colombian Blue Dwarf",            "0.125",None,  31.0,  1, None,                        "T"),
    ("Spinosatibiapalpus sp. Colombia",      "Colombia Purple & Gold",          "0.125",None,  46.0,  1, None,                        "T"),
    ("Stromatopelma calceatum",              "Featherleg Baboon",               "1.25", None,  37.0,  1, "1-1.5 in",                 "T"),
    ("Tapinauchenius cupreus",               "Copper Tree Spider",              "0.5",  None,  22.0,  1, None,                        "T"),
    ("Tapinauchenius rasti",                 "Caribbean Diamond",               "1.5",  None,  34.0,  1, None,                        "T"),
    ("Tapinauchenius sanctivincenti",        "St. Vincents Tree Spider",        "0.5",  None,  28.0,  1, None,                        "T"),
    ("Tapinauchenius sanctivincenti",        "St. Vincents Tree Spider",        "2.5",  "F",  200.0,  1, None,                        "T"),
    ("Theraphosinae sp. Roatan",             "Roatan Island Purple",            "0.25", None,  22.0,  1, None,                        "T"),
    ("Theraphosinae sp. Roatan",             "Roatan Island Purple",            "2.0",  None,  64.0,  1, None,                        "T"),
    ("Thrigmopoeus truculentus",             "Lesser Goa Mustard",              "0.5",  None,  25.0,  1, None,                        "T"),
    ("Thrixopelma cyanoeolum",               "Cobalt Red Rump",                 "0.5",  None,  58.0,  1, "Blue form",                 "T"),
    ("Thrixopelma ockerti",                  "Peruvian Red Rump",               "0.25", None,  31.0,  1, None,                        "T"),
    ("Thrixopelma sp. Cajamarca",            "Cajamarca Birdeater",             "0.5",  None,  31.0,  1, None,                        "T"),
    ("Thrixopelma sp. Loque",               None,                               "0.5",  None,  43.0,  1, None,                        "T"),
    ("Thrixopelma sp. Similis",              "Peruvian Blue Femur",             "0.5",  None,  62.0,  1, None,                        "T"),
    ("Thrixopelma sp. Sullana",              "Sullana Velvet",                  "0.5",  None,  22.0,  1, None,                        "T"),
    ("Tliltocatl albopilosus",               "Curly Hair",                      "0.25", None,  14.0,  1, None,                        "T"),
    ("Tliltocatl albopilosus",               "Curly Hair",                      "1.5",  None,  22.0,  1, None,                        "T"),
    ("Tliltocatl epicureanus",               "Yucatan Rust Rump",               "0.25", None,  21.0,  1, None,                        "T"),
    ("Tliltocatl kahlenbergi",               "Veracruz Red Rump",              "0.75", None,  28.0,  1, None,                        "T"),
    ("Tliltocatl kahlenbergi",               "Veracruz Red Rump",              "1.5",  None,  48.0,  1, None,                        "T"),
    ("Tliltocatl sabulosus",                 "Guatemalan Tiger Rump",           "1.5",  None,  42.0,  1, None,                        "T"),
    ("Tliltocatl schroederi",                "Mexican Black Velvet",            "1.5",  None,  87.0,  1, None,                        "T"),
    ("Tliltocatl vagans",                    "Mexican Red Rump",                "1.5",  None,  42.0,  1, None,                        "T"),
    ("Tliltocatl verdezi",                   "Mexican Grey Rose",               "1.0",  None,  37.0,  1, None,                        "T"),
    ("Tliltocatl verdezi",                   "Mexican Grey Rose",               "1.5",  None,  43.0,  1, None,                        "T"),
    ("Trichopelma sp. Montana",              None,                              "0.5",  None,  55.0,  1, None,                        "T"),
    ("Trichopelma sp. Orellana",             None,                              "0.5",  None,  52.0,  1, None,                        "T"),
    ("Urupelma peruvianum",                  "Peru Mountain Dwarf",             "0.5",  None,  48.0,  1, None,                        "T"),
    ("Vitalius chromatus",                   "Brazilian Red & White",           "0.25", None,  19.0,  1, None,                        "T"),
    ("Vitalius chromatus",                   "Brazilian Red & White",           "1.125",None,  34.0,  1, "1-1.25 in",                "T"),
    ("Xenesthis sp. Light",                  "Light Bloom Birdeater",           "1.5",  None, 151.0,  1, None,                        "T"),
    ("Xenesthis sp. White",                  None,                              "1.5",  None, 226.0,  1, None,                        "T"),
    ("Ybyrapora sooretama",                  "Amazon Purple Sapphire",          "0.75", None,  76.0,  1, None,                        "T"),
]

# ---------------------------------------------------------------------------
# SELLER REGISTRY
# Each: (vendor_key, vendor_name, platform, verification_level, datasets)
# ---------------------------------------------------------------------------
SELLERS = [
    {
        "vendor_key":         "fb_unnamed",
        "vendor_name":        "Unnamed Facebook Seller",
        "platform":           "facebook_marketplace",
        "verification_level": "community",
        "data":               FB_SELLER_UPDATED,
    },
    {
        "vendor_key":         "eric_madrid",
        "vendor_name":        "Eric Madrid",
        "platform":           "private_seller",
        "verification_level": "community",
        "data":               ERIC_MADRID_SEXED + ERIC_MADRID_SLINGS,
    },
    {
        "vendor_key":         "good_guy_reptiles",
        "vendor_name":        "Good Guy Reptiles (Wholesale)",
        "platform":           "wholesale",
        "verification_level": "wholesale",
        "data":               GOOD_GUY_WHOLESALE,
    },
    {
        "vendor_key":         "emil",
        "vendor_name":        "Emil",
        "platform":           "private_seller",
        "verification_level": "community",
        "data":               EMIL_LISTINGS,
    },
    {
        "vendor_key":         "aaron_rogers",
        "vendor_name":        "Aaron Rogers",
        "platform":           "private_seller",
        "verification_level": "community",
        "data":               AARON_ROGERS,
    },
    {
        "vendor_key":         "justin_arras",
        "vendor_name":        "Justin Arras",
        "platform":           "private_seller",
        "verification_level": "community",
        "data":               JUSTIN_ARRAS,
    },
    {
        "vendor_key":         "unnamed_wholesale",
        "vendor_name":        "Unnamed Wholesale",
        "platform":           "wholesale",
        "verification_level": "wholesale",
        "data":               UNNAMED_WHOLESALE,
    },
    {
        "vendor_key":         "spider_room",
        "vendor_name":        "The Spider Room",
        "platform":           "shopify",
        "verification_level": "reference_snapshot",
        "data":               SPIDER_ROOM_REF,
    },
]

# ---------------------------------------------------------------------------
# CATEGORY DISPLAY NAMES
# ---------------------------------------------------------------------------
CAT_DISPLAY = {
    "T":  "Tarantula",
    "S":  "Spider / Other Arachnid",
    "SC": "Scorpion",
    "C":  "Centipede",
    "M":  "Millipede",
    "O":  "Other",
}

SEX_DISPLAY = {
    "F":   "Female",
    "M":   "Male",
    "PF":  "Probable Female",
    "PM":  "Probable Male",
    None:  "Unsexed",
}


# ---------------------------------------------------------------------------
# IMPORT LOGIC
# ---------------------------------------------------------------------------

def register_community_vendors(db_path=DB_PATH):
    for s in SELLERS:
        upsert_vendor(
            vendor_key=s["vendor_key"],
            vendor_name=s["vendor_name"],
            base_url="",
            platform=s["platform"],
            db_path=db_path,
        )


def import_all(db_path=DB_PATH, dry_run=False):
    """Parse all seller data and insert into price_history."""
    now = datetime.now(timezone.utc).isoformat()
    total_inserted = 0
    conn = None if dry_run else get_connection(db_path)

    for seller in SELLERS:
        vkey  = seller["vendor_key"]
        vname = seller["vendor_name"]
        vlevel = seller["verification_level"]
        data   = seller["data"]

        # Create a crawl_run record for this seed
        if not dry_run:
            run_id = conn.execute("""
                INSERT INTO crawl_runs
                  (vendor_key, status, pages_crawled, products_found, variants_found,
                   started_at, finished_at, notes)
                VALUES (?, 'complete', 1, ?, ?, ?, ?, ?)
            """, (
                vkey, len(data), len(data), now, now,
                f"Seeded from community price lists — {now[:10]}"
            )).lastrowid
            conn.commit()

        rows = []
        for entry in data:
            name, common, size_str, sex, price, qty, notes, cat = entry

            # Normalize species key
            try:
                name_key = normalize_species_key(name)
            except Exception:
                name_key = name.lower().strip()

            # Parse size
            sz_min, sz_max, sz_mid = parse_size(size_str)
            sz_text = size_str if size_str else None

            sex_code    = sex if sex else "U"
            sex_disp    = SEX_DISPLAY.get(sex, "Unsexed")
            cat_disp    = CAT_DISPLAY.get(cat, cat)
            full_notes  = f"[{cat_disp}]" + (f" {notes}" if notes else "")

            row = (
                vkey,                        # vendor_key
                name,                        # scientific_name
                name_key,                    # scientific_name_key
                common,                      # common_name
                sex_code,                    # sex
                sex_disp,                    # sex_display
                sz_text,                     # size_text
                sz_min,                      # size_min
                sz_max,                      # size_max
                sz_mid,                      # size_midpoint
                price,                       # price_usd
                None,                        # regular_price_usd
                "in_stock",                  # availability
                qty,                         # quantity
                None,                        # product_url
                None,                        # variant_name
                full_notes,                  # notes
                None,                        # deal_rating
                None,                        # deal_reason
                None,                        # current_lowest
                None,                        # market_average
                None,                        # historical_low
                round(price / sz_mid, 2) if sz_mid and sz_mid > 0 else None,  # price_per_inch
                0,                           # is_new
                0,                           # is_price_drop
                0,                           # is_new_historical_low
                0,                           # is_returned_to_stock
                0,                           # is_sold_out
                0,                           # is_price_increase
                None,                        # previous_price
                vlevel,                      # verification_level
                f"{name} {size_str or ''} {sex or ''}".strip(),  # raw_title
                None,                        # raw_variant
                f"${price:.2f}",             # raw_price
                run_id if not dry_run else 0,
                now,                         # observed_at
            )
            rows.append(row)

        if dry_run:
            print(f"[DRY] {vname}: {len(rows)} entries")
        else:
            conn.executemany("""
                INSERT INTO price_history
                    (vendor_key, scientific_name, scientific_name_key, common_name,
                     sex, sex_display, size_text, size_min, size_max, size_midpoint,
                     price_usd, regular_price_usd, availability, quantity,
                     product_url, variant_name, notes,
                     deal_rating, deal_reason, current_lowest, market_average, historical_low,
                     price_per_inch, is_new, is_price_drop, is_new_historical_low,
                     is_returned_to_stock, is_sold_out, is_price_increase,
                     previous_price, verification_level,
                     raw_title, raw_variant, raw_price,
                     crawl_run_id, observed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)
            conn.commit()
            print(f"  [{vname}] {len(rows):>3} entries inserted (level: {vlevel})")

        total_inserted += len(rows)

    if not dry_run:
        conn.close()
    print(f"\nTotal: {total_inserted} community price entries {'(dry run)' if dry_run else 'inserted'}.")
    return total_inserted


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed community price data into the market tracker DB")
    parser.add_argument("--dry-run", action="store_true", help="Count entries without inserting")
    args = parser.parse_args()

    print("Tarantula Market Tracker — Community Price Seeder")
    print("=" * 55)

    if not args.dry_run:
        init_db(DB_PATH)
        register_community_vendors()

    import_all(dry_run=args.dry_run)
