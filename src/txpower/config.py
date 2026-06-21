"""Single source of truth for project-wide constants.

Pinning these here keeps the consumption / price / contract / TDU layers
consistent. Everything geographic flows from the chosen ZIP.
"""

# --- Geography (chosen for consistency with Pecan Street Austin-metro homes) ---
ZIP_CODE = "78664"                # Round Rock: fully Oncor-deregulated, Austin metro
TDU_NAME = "Oncor"
TDU_COMPANY_PTC = "ONCOR ELECTRIC DELIVERY COMPANY"   # as it appears in PTC export
ERCOT_LOAD_ZONE = "LZ_NORTH"      # Oncor territory settlement point

# --- Oncor TDU pass-through (delivery) charges -------------------------------
# These change over time, so keep an era-specific snapshot for each analysis.
# 2026 figures (normal-month analysis). Source: WattOwl/Oncor tariff, Jun 2026.
TDU_2026 = {
    "name": "Oncor",
    "fixed_monthly": 4.23,   # $/month
    "per_kwh": 0.0562,       # $/kWh  (~5.62 c/kWh)
}
# 2021 figures (Winter Storm Uri analysis) -- TODO: confirm from a Feb-2021 EFL,
# since Oncor's delivery rate differed. Placeholder mirrors 2026 until verified.
TDU_2021 = {
    "name": "Oncor",
    "fixed_monthly": 3.42,   # TODO verify against Feb-2021 EFL
    "per_kwh": 0.0382,       # TODO verify against Feb-2021 EFL
}

# --- Winter Storm Uri window -------------------------------------------------
URI_START = "2021-02-13"
URI_END = "2021-02-20"
ERCOT_PRICE_CAP_PER_MWH = 9000.0   # $/MWh system offer cap during Uri
