"""Reference values for the Service Board price matrix.

Do not treat these as production prices — they define allowed model names and
mileage bands for validation during CSV import.
"""

BOARD_VEHICLE_MODELS: tuple[str, ...] = (
    "Corolla",
    "Avensis",
    "Camry",
    "Prado",
    "Coaster",
    "Hilux",
    "Hiace",
    "Yaris",
    "RAV-4",
)

BOARD_MILEAGE_BANDS_KM: tuple[int, ...] = (
    1_000,
    5_000,
    10_000,
    15_000,
    25_000,
    40_000,
    60_000,
    80_000,
    100_000,
)

DEFAULT_PRICE_DISCLAIMER = (
    "Displayed prices are working estimates inclusive of labour, parts and tax "
    "and may vary according to the work actually performed."
)

PRICE_IMPORT_TEMPLATE_COLUMNS = (
    "vehicleModel",
    "serviceItemCode",
    "mileageBandKm",
    "price",
)
