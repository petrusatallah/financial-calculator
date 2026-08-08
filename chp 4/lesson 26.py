import numpy as np 
import pandas as pd

Portfolio=pd.DataFrame(
    {
        "Price":[180, 190, 205, 210,
                  250, np.nan, 280, 300,
                  150, 160, 170, 180],

        "Shares":[50, 50, 50, 50,
                   30, 30, 30, 30,
                   40, 40, 40, 40]

    },
        index=[
        [
            "Apple","Apple","Apple","Apple",
            "Tesla","Tesla","Tesla","Tesla",
            "Microsoft","Microsoft","Microsoft","Microsoft"
        ],

        [
            "Q1","Q2","Q3","Q4",
            "Q1","Q2","Q3","Q4",
            "Q1","Q2","Q3","Q4"
        ]
    ]

)

Portfolio.index.names=["Company","Quarter"]

print(Portfolio)

print(Portfolio.isnull())

Portfolio=Portfolio.fillna(Portfolio.mean())
print(Portfolio)

print(Portfolio.notnull())

Portfolio["Investment Value"]=Portfolio["Price"]*Portfolio["Shares"]
Portfolio["Target Price"]=Portfolio["Price"]*1.12

print(Portfolio.loc["Tesla"])

print(Portfolio.loc[(slice(None),"Q3"),:])
print(Portfolio.loc[("Apple","Q3")])
print(Portfolio.loc[("Apple","Q2")])

print(Portfolio[Portfolio["Price"]>200])
print(Portfolio[Portfolio.index.get_level_values("Company").isin(["Apple","Microsoft"])])

print(Portfolio.describe())
print(Portfolio.corr())
avreage_price=Portfolio.groupby(level="Company")["Price"].mean()
print(avreage_price)
print(Portfolio["Investment Value"].idxmax())
def diffrence (x):
    return x.max()- x.min()
print(np.sqrt(Portfolio["Price"]))
unstacked_portfolio = Portfolio.unstack()

print("\nUnstacked Portfolio:")
print(unstacked_portfolio)


stacked_portfolio = unstacked_portfolio.stack()

print("\nStacked Portfolio:")
print(stacked_portfolio)


swapped_portfolio = Portfolio.swaplevel("Company", "Quarter")

print("\nSwapped levels:")
print(swapped_portfolio)


sorted_swapped_portfolio = swapped_portfolio.sort_index()

print("\nSwapped and sorted:")
print(sorted_swapped_portfolio)



total_investment_by_company = (
    Portfolio.groupby(level="Company")["Investment Value"].sum()
)

print("\nTotal Investment Value by Company:")
print(total_investment_by_company)


average_price_by_company = (
    Portfolio.groupby(level="Company")["Price"].mean()
)

print("\nAverage Price by Company:")
print(average_price_by_company)


average_price_by_quarter = (
    Portfolio.groupby(level="Quarter")["Price"].mean()
)

print("\nAverage Price by Quarter:")
print(average_price_by_quarter)



sorted_by_price = Portfolio.sort_values(
    by="Price",
    ascending=False
)

print("\nPortfolio sorted by Price:")
print(sorted_by_price)


Portfolio["Rank"] = Portfolio["Investment Value"].rank(
    ascending=False,
    method="min"
)

print("\nPortfolio with Rank:")
print(Portfolio)


largest_investment_index = Portfolio["Investment Value"].idxmax()

print("\nLargest Investment Value:")
print(largest_investment_index)
