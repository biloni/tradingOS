"""Phase 2 seed symbol universe: a diversified, liquid subset of US equities
and broad-market ETFs (ADR-003: equities + ETFs only). Reversible default
confirmed with the user — not an exhaustive index constituent list.
"""

from tradingos_api.models.symbol import AssetType

SeedSymbol = tuple[str, str, str, AssetType]

SEED_SYMBOLS: list[SeedSymbol] = [
    # Technology
    ("AAPL", "Apple Inc.", "NASDAQ", AssetType.EQUITY),
    ("MSFT", "Microsoft Corporation", "NASDAQ", AssetType.EQUITY),
    ("GOOGL", "Alphabet Inc.", "NASDAQ", AssetType.EQUITY),
    ("AMZN", "Amazon.com, Inc.", "NASDAQ", AssetType.EQUITY),
    ("NVDA", "NVIDIA Corporation", "NASDAQ", AssetType.EQUITY),
    ("META", "Meta Platforms, Inc.", "NASDAQ", AssetType.EQUITY),
    ("CRM", "Salesforce, Inc.", "NYSE", AssetType.EQUITY),
    # Healthcare
    ("JNJ", "Johnson & Johnson", "NYSE", AssetType.EQUITY),
    ("UNH", "UnitedHealth Group Incorporated", "NYSE", AssetType.EQUITY),
    ("PFE", "Pfizer Inc.", "NYSE", AssetType.EQUITY),
    ("ABBV", "AbbVie Inc.", "NYSE", AssetType.EQUITY),
    # Financials
    ("JPM", "JPMorgan Chase & Co.", "NYSE", AssetType.EQUITY),
    ("BAC", "Bank of America Corporation", "NYSE", AssetType.EQUITY),
    ("GS", "The Goldman Sachs Group, Inc.", "NYSE", AssetType.EQUITY),
    ("V", "Visa Inc.", "NYSE", AssetType.EQUITY),
    # Energy
    ("XOM", "Exxon Mobil Corporation", "NYSE", AssetType.EQUITY),
    ("CVX", "Chevron Corporation", "NYSE", AssetType.EQUITY),
    # Consumer
    ("PG", "The Procter & Gamble Company", "NYSE", AssetType.EQUITY),
    ("KO", "The Coca-Cola Company", "NYSE", AssetType.EQUITY),
    ("WMT", "Walmart Inc.", "NYSE", AssetType.EQUITY),
    ("HD", "The Home Depot, Inc.", "NYSE", AssetType.EQUITY),
    ("NKE", "NIKE, Inc.", "NYSE", AssetType.EQUITY),
    # Industrials
    ("BA", "The Boeing Company", "NYSE", AssetType.EQUITY),
    ("CAT", "Caterpillar Inc.", "NYSE", AssetType.EQUITY),
    ("GE", "GE Aerospace", "NYSE", AssetType.EQUITY),
    # Communication services
    ("DIS", "The Walt Disney Company", "NYSE", AssetType.EQUITY),
    # Broad-market ETFs
    ("SPY", "SPDR S&P 500 ETF Trust", "NYSEARCA", AssetType.ETF),
    ("QQQ", "Invesco QQQ Trust", "NASDAQ", AssetType.ETF),
    ("IWM", "iShares Russell 2000 ETF", "NYSEARCA", AssetType.ETF),
    ("DIA", "SPDR Dow Jones Industrial Average ETF Trust", "NYSEARCA", AssetType.ETF),
]
