# Tunables for the jobs extract stage: the UI strings a saved page is located
# by, and the floor under which a page counts as unrendered. Kept out of
# extract.py so a LinkedIn wording change moves without touching the parse logic.

# LinkedIn's saved-page markup carries no JSON-LD, so every field below is
# located by UI text. These anchors follow the LinkedIn interface language,
# not the posting language: a Spanish UI is assumed throughout.
BODY_START_ANCHOR = "Acerca del empleo"

# The recommended-jobs rail is rendered inside the same container as the
# description. Cutting at the first of these keeps other companies' postings
# out of the text handed to the model.
BODY_END_ANCHORS = (
    "Establecer una alerta para empleos similares",
    "Búsqueda de empleo más rápida con Premium",
    "Más empleos",
    "Ver más empleos como este",
)

# Shortest legitimate description observed is 922 characters; anything far
# below that means the page was saved before the description rendered.
MIN_BODY_LENGTH = 300

MODALITIES = ("En remoto", "Híbrido", "Presencial")

CONTRACT_TYPES = (
    "Jornada completa",
    "Media jornada",
    "Contrato temporal",
    "Prácticas",
    "Por contrato",
    "Contrato de duración determinada",
)
