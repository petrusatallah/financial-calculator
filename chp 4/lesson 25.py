import pandas as pd

Stocks = pd.DataFrame(
    {
        "Revenue": [200, 100, 300, 200, 200, 500, 400, 100]
    },
    index=[
        [
            "Apple", "Apple", "Apple", "Apple",
            "Tesla", "Tesla", "Tesla", "Tesla"
        ],
        [
            "Q1", "Q2", "Q3", "Q4",
            "Q1", "Q2", "Q3", "Q4"
        ]
    ]
)

Stocks.index.names = ["Company", "Quarter"]

print("Original MultiIndex DataFrame:")
print(Stocks)

print("\nApple revenue:")
print(Stocks.loc["Apple"])

print("\nQ2 revenue for all companies:")
print(Stocks.loc[(slice(None), "Q2"), :])

Stocks_unstacked = Stocks.unstack()

print("\nAfter unstack:")
print(Stocks_unstacked)

Stocks_swapped = Stocks.swaplevel("Company", "Quarter").sort_index()

print("\nSwapped and sorted:")
print(Stocks_swapped)

revenue_by_company = Stocks.groupby(level="Company").sum()

print("\nTotal revenue by company:")
print(revenue_by_company)

average_by_quarter = Stocks.groupby(level="Quarter").mean()

print("\nAverage revenue by quarter:")
print(average_by_quarter)