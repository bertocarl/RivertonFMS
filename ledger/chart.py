"""Default chart of accounts. Codes are referenced by the posting services."""

CASH = "1000"
MPESA = "1010"
CARD = "1020"
BANK = "1050"
RECEIVABLES = "1100"
INVENTORY_FUEL = "1200"
INVENTORY_SHOP = "1210"
PAYABLES = "2000"
EQUITY = "3000"
FUEL_SALES = "4000"
SHOP_SALES = "4100"
COGS_FUEL = "5000"
COGS_SHOP = "5100"
SALARIES = "6000"
UTILITIES = "6100"
REPAIRS = "6200"
LICENCES = "6300"
GENERAL = "6800"
CASH_OVER_SHORT = "6900"

DEFAULT_CHART = [
    (CASH, "Cash on hand", "ASSET"),
    (MPESA, "M-Pesa clearing", "ASSET"),
    (CARD, "Card settlements clearing", "ASSET"),
    (BANK, "Bank account", "ASSET"),
    (RECEIVABLES, "Trade receivables (credit customers)", "ASSET"),
    (INVENTORY_FUEL, "Fuel inventory", "ASSET"),
    (INVENTORY_SHOP, "Lubricants, gas and shop inventory", "ASSET"),
    (PAYABLES, "Trade payables (suppliers)", "LIABILITY"),
    (EQUITY, "Owner's equity", "EQUITY"),
    (FUEL_SALES, "Fuel sales", "INCOME"),
    (SHOP_SALES, "Lubricant, gas and shop sales", "INCOME"),
    (COGS_FUEL, "Cost of fuel sold", "EXPENSE"),
    (COGS_SHOP, "Cost of shop goods sold", "EXPENSE"),
    (SALARIES, "Salaries and wages", "EXPENSE"),
    (UTILITIES, "Electricity, water and phone", "EXPENSE"),
    (REPAIRS, "Repairs and maintenance", "EXPENSE"),
    (LICENCES, "Licences and permits", "EXPENSE"),
    (GENERAL, "General expenses", "EXPENSE"),
    (CASH_OVER_SHORT, "Cash over / short", "EXPENSE"),
]
