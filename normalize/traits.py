"""
Species trait data + badge resolver for the spider-card trait badges.

Design (from research cross-checked against The Tarantula Collective, Tom's Big
Spiders, Fear Not/Jamie's care sheets, Arachnoboards, SpiderShoppe): tarantula
traits are largely genus-consistent, so we keep GENUS defaults plus SPECIES
overrides where a species deviates. Resolution order: species binomial → genus.

Badge set (5, ordered): Hemisphere · Habitat · Size · Temperament · Experience.
Temperament and Experience use traffic-light colors so a beginner can self-select
out at a glance. Non-tarantulas (scorpions, jumping spiders) carry a `kind` and
render a trimmed set. Species not in the table get NO badges (graceful).

`climate` means the husbandry target (how it's KEPT), not just native biome.
"""

TARANTULA_GENUS_DEFAULTS = {
    "Grammostola":    {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Temperate", "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Brachypelma":    {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Tliltocatl":     {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Aphonopelma":    {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Arid",      "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Acanthoscurria": {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Beginner"},
    "Lasiodora":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Beginner"},
    "Nhandu":         {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Intermediate"},
    "Pamphobeteus":   {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Xenesthis":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Phormictopus":   {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Megaphobema":    {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Intermediate"},
    "Theraphosa":     {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Advanced"},
    "Cyriocosmus":    {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Hapalopus":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Neoholothele":   {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Davus":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Cyclosternum":   {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Homoeomma":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Docile",    "speed": "Medium", "experience": "Beginner"},
    "Thrixopelma":    {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Docile",    "speed": "Medium", "experience": "Beginner"},
    "Chromatopelma":  {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Arid",      "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Avicularia":     {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Docile",    "speed": "Medium", "experience": "Beginner"},
    "Caribena":       {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Ybyrapora":      {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Psalmopoeus":    {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Tapinauchenius": {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Ephebopus":      {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Poecilotheria":  {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Omothymus":      {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Lampropelma":    {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Phormingochilus":{"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Chilobrachys":   {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Cyriopagopus":   {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Haplopelma":     {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Melopoeus":      {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Selenocosmia":   {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Orphnaecus":     {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Coremiocnemis":  {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Pterinochilus":  {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Ceratogyrus":    {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Harpactira":     {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Augacephalus":   {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Idiothele":      {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Monocentropus":  {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Arid",      "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Heteroscodra":   {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Stromatopelma":  {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Encyocratella":  {"hemisphere": "Old World", "habitat": "Semi-arboreal","size": "Medium","climate": "Temperate", "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Hysterocrates":  {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Selenotypus":    {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Arid",      "temperament": "Defensive", "speed": "Medium", "experience": "Intermediate"},
    "Selenotholus":   {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Arid",      "temperament": "Defensive", "speed": "Medium", "experience": "Intermediate"},
    "Lasiocyano":     {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Arid",      "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
}

TARANTULA_SPECIES_OVERRIDES = {
    "Chromatopelma cyaneopubescens": {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Arid",      "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Grammostola pulchra":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Temperate", "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Grammostola pulchripes":        {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Temperate", "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Grammostola quirogai":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Temperate", "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Aphonopelma seemanni":          {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Beginner"},
    "Avicularia avicularia":         {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Docile",    "speed": "Medium", "experience": "Beginner"},
    "Acanthoscurria geniculata":     {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Beginner"},
    "Lasiodora parahybana":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Beginner"},
    "Lasiodora klugi":               {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Tliltocatl albopilosus":        {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Tliltocatl vagans":             {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Beginner"},
    "Pterinochilus murinus":         {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Heteroscodra maculata":         {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Stromatopelma calceatum":       {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Psalmopoeus irminia":           {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Psalmopoeus cambridgei":        {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Theraphosa apophysis":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Advanced"},
    "Theraphosa blondi":             {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Advanced"},
    "Thrixopelma pruriens":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Docile",    "speed": "Medium", "experience": "Beginner"},
    "Neoholothele incei":            {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Augacephalus rufus":            {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Chilobrachys natanicharum":     {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Chilobrachys sp kaeng krachan": {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Lasiocyano sazimai":            {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Arid",      "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Phormingochilus hati hati":     {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Omothymus violaceopes":         {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Megaphobema robustum":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Intermediate"},
    "Hysterocrates gigas":           {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Davus pentaloris":              {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Beginner"},
    "Melopoeus lividus":             {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
}

# Expanded genus coverage (2nd research pass, verified vs WSC / care sheets).
# Merged AFTER the curated TARANTULA_GENUS_DEFAULTS, which win on any overlap.
# `# LOW-CONF` marks obscure/newly-described genera or subfamily-label defaults.
NEW_GENUS_DEFAULTS = {
    "Acanthopelma":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Amazonius":          {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Anqasha":            {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Antikuna":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Bistriopelma":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Bonnetina":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Arid",      "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Bumba":              {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Docile",    "speed": "Medium", "experience": "Beginner"},
    "Cardiopelma":        {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Catumiri":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Citharacanthus":     {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Clavopelma":         {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Arid",      "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Cotztetlana":        {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Crassicrus":         {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Cyrtopholis":        {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Dolichothele":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Docile",    "speed": "Medium", "experience": "Beginner"},
    "Euathlus":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Eupalaestrus":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Euthycaelus":        {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Ewok":               {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Guyruita":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Hapalotremus":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Hemirrhagus":        {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Medium", "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Holothele":          {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Iridopelma":         {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Isiboroa":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Kochiana":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Lasiodorides":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Neischnocolus":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Phrixotrichus":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Docile",    "speed": "Slow",   "experience": "Beginner"},
    "Plesiopelma":        {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Pseudhapalopus":     {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Pseudoclamoris":     {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Pterinopelma":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Sericopelma":        {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Intermediate"},
    "Spinosatibiapalpus": {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Thalerommata":       {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Trichopelma":        {"hemisphere": "New World", "habitat": "Fossorial",   "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Typhochlaena":       {"hemisphere": "New World", "habitat": "Arboreal",    "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Advanced"},
    "Urupelma":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Vitalius":           {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Medium", "experience": "Intermediate"},
    "Aspinochilus":       {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},  # LOW-CONF
    "Birupes":            {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Brachionopus":       {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Dwarf",  "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Chaetopelma":        {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Arid",      "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Chilocosmia":        {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},  # LOW-CONF
    "Eucratoscelus":      {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Haploclastus":       {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Haplocosmia":        {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Temperate", "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},  # LOW-CONF
    "Harpactirella":      {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Dwarf",  "climate": "Arid",      "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Heterothele":        {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Ischnocolus":        {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Arid",      "temperament": "Docile",    "speed": "Slow",   "experience": "Intermediate"},  # LOW-CONF
    "Lyrognathus":        {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Magnacrus":          {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},  # LOW-CONF
    "Ornithoctonus":      {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Pelinobius":         {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Arid",      "temperament": "Defensive", "speed": "Slow",   "experience": "Advanced"},
    "Phlogiellus":        {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Intermediate"},
    "Phlogius":           {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Psednocnemis":       {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},  # LOW-CONF
    "Sahydroaraneus":     {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Dwarf",  "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},
    "Selenobrachys":      {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    "Taksinus":           {"hemisphere": "Old World", "habitat": "Arboreal",    "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Fast",   "experience": "Intermediate"},
    "Thrigmopoeus":       {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},
    # Subfamily / family labels — generic defaults, low confidence (span many genera).
    "Ornithoctoninae":    {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},      # LOW-CONF
    "Selenocosmiinae":    {"hemisphere": "Old World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},      # LOW-CONF
    "Thrigmopoeinae":     {"hemisphere": "Old World", "habitat": "Fossorial",   "size": "Large",  "climate": "Tropical",  "temperament": "Defensive", "speed": "Fast",   "experience": "Advanced"},      # LOW-CONF
    "Theraphosinae":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
    "Theraphosidae":      {"hemisphere": "New World", "habitat": "Terrestrial", "size": "Medium", "climate": "Tropical",  "temperament": "Skittish",  "speed": "Medium", "experience": "Intermediate"},  # LOW-CONF
}

# Misspelled genus tokens → the correct genus (all lowercase). Applied before lookup.
GENUS_ALIASES = {
    "aviculaira": "avicularia", "cyriopagapus": "cyriopagopus",
    "tapiniauchenius": "tapinauchenius", "ceratogryus": "ceratogyrus",
    "dugesiella": "aphonopelma", "dolichotherle": "dolichothele",
    "eupaleastrus": "eupalaestrus", "eupelaestrus": "eupalaestrus",
    "pelinobus": "pelinobius", "psuedoclamoris": "pseudoclamoris",
    "harpactra": "harpactira", "harpacta": "harpactira",
    "melapoeus": "melopoeus", "melopeus": "melopoeus",
    "lasiocyaneo": "lasiocyano", "cotzetlana": "cotztetlana",
    "isaboroa": "isiboroa",
}

# Non-tarantulas carry a `kind`; the app renders a trimmed badge set for them.
NON_TARANTULA = {
    "Pandinus imperator": {"kind": "Scorpion", "hemisphere": "Old World", "habitat": "Fossorial",
                           "size": "Large", "climate": "Tropical", "temperament": "Docile",
                           "speed": "Slow", "experience": "Beginner"},
    "Phidippus regius":   {"kind": "Jumping spider", "hemisphere": "New World", "habitat": "Arboreal",
                           "size": "Dwarf", "climate": "Tropical", "temperament": "Docile",
                           "speed": "Fast", "experience": "Beginner"},
}

# ── Badge presentation: emoji + color per trait value ────────────────────────
_GREEN, _AMBER, _RED, _SLATE, _BLUE, _BROWN = "#16a34a", "#d97706", "#dc2626", "#64748b", "#2563eb", "#a16207"
_BADGE = {
    "hemisphere": {
        "New World": ("🌎", _BLUE,  "Native to the Americas. Has urticating (irritating) hairs it can flick; generally calmer venom."),
        "Old World": ("🌍", _RED,   "Native to Africa/Asia. No urticating hairs, but potent venom and usually fast & defensive."),
    },
    "habitat": {
        "Terrestrial":   ("⬛", _BROWN, "Ground-dweller — wants floor space and some substrate to burrow into."),
        "Arboreal":      ("🌳", _GREEN, "Tree-dweller — wants a tall enclosure with height and cross-ventilation."),
        "Fossorial":     ("🕳️", _SLATE, "Burrower — wants deep substrate; often hides underground."),
        "Semi-arboreal": ("🪵", _GREEN, "Uses both height and burrows depending on age/mood."),
    },
    "size": {
        "Dwarf":  ("🐜", _SLATE, "Small species — stays under a few inches."),
        "Medium": ("▪️", _SLATE, "Medium-bodied species."),
        "Large":  ("🦵", _SLATE, "Large species — big leg span and appetite."),
    },
    "temperament": {
        "Docile":    ("🟢", _GREEN, "Calm — tolerates maintenance well, rarely defensive."),
        "Skittish":  ("🟡", _AMBER, "Nervous — likely to bolt or kick hairs, but not aggressive."),
        "Defensive": ("🔴", _RED,   "Readily throws a threat posture and may bite — respect it."),
    },
    "experience": {
        "Beginner":     ("✅", _GREEN, "A good first-tarantula choice."),
        "Intermediate": ("⚠️", _AMBER, "Best after you've kept a few — faster or feistier."),
        "Advanced":     ("⛔", _RED,   "For experienced keepers: speed, venom, or husbandry demands."),
    },
    "climate": {
        "Tropical":  ("🌴", _GREEN, "Warm and humid — keep humidity up."),
        "Temperate": ("🍃", _SLATE, "Room temperature; tolerates cooler conditions."),
        "Arid":      ("🏜️", _AMBER, "Dry — keep mostly dry with a water dish."),
    },
}
# Order badges are rendered in (locked so returning users read by position).
BADGE_ORDER = ["hemisphere", "habitat", "size", "temperament", "experience", "climate"]


def _norm(s):
    return " ".join((s or "").lower().split())


# Pre-lowercased lookups (data keys are Capitalized). Expansion is merged first so
# the curated TARANTULA_GENUS_DEFAULTS win on any overlapping genus.
_SPECIES = {_norm(k): v for k, v in {**TARANTULA_SPECIES_OVERRIDES, **NON_TARANTULA}.items()}
_GENUS = {k.lower(): v for k, v in {**NEW_GENUS_DEFAULTS, **TARANTULA_GENUS_DEFAULTS}.items()}


def traits_for(species_key: str) -> dict | None:
    """Resolve a species_key (lowercase binomial like 'grammostola pulchra') to its
    trait dict, or None if we have no verified data. Species override → genus default
    (after mapping any known misspelled genus token to its correct genus)."""
    k = _norm(species_key)
    if not k:
        return None
    if k in _SPECIES:
        return _SPECIES[k]
    genus = k.split()[0]
    genus = GENUS_ALIASES.get(genus, genus)
    return _GENUS.get(genus)


def trait_badges(species_key: str) -> dict:
    """Render-ready badges for a species: {"badges": [{axis,value,emoji,color,tip}],
    "kind": "Tarantula"|"Scorpion"|...}. `badges` is empty when we have no data.
    `climate` is included as an optional 6th badge."""
    t = traits_for(species_key)
    if not t:
        return {"badges": [], "kind": None}
    out = []
    for axis in BADGE_ORDER:
        val = t.get(axis)
        spec = _BADGE.get(axis, {}).get(val) if val else None
        if not spec:
            continue
        emoji, color, tip = spec
        out.append({"axis": axis, "value": val, "emoji": emoji, "color": color, "tip": tip})
    return {"badges": out, "kind": t.get("kind", "Tarantula")}
