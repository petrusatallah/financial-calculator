import numpy as np
import pandas as pd 

Portfolio = pd.DataFrame(
    {
        "Price":[
            180,190,205,210,
            250,np.nan,280,300,
            150,160,170,180
        ],

        "Shares":[
            50,50,50,50,
            30,30,30,30,
            40,40,40,40
        ]
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
print(Portfolio.isnull())
Portfolio["Price"] = Portfolio["Price"].fillna(
    Portfolio["Price"].mean()
)
Portfolio["Investment Value"]=Portfolio["Price"]*Portfolio["Shares"]
Portfolio["Target Price"]=Portfolio["Price"]*1.12

print(Portfolio.loc["Tesla"])
print(
    Portfolio.loc[
        (slice(None), "Q3"),
        :
    ]
)
print (Portfolio.loc[
    (slice(None),"Q2"),
    :
])
print (Portfolio[Portfolio["Price"]>200])
print(Portfolio.loc[["Apple","Microsoft"]])
print(Portfolio.describe())
print(Portfolio.corr(numeric_only=True))
print(Portfolio.groupby(level="Company")["Price"].mean())
print(Portfolio.groupby(level="Quarter")["Price"].mean())
print(Portfolio.groupby(level="Company")["Investment Value"].sum())
Portfolio=Portfolio.unstack()
Portfolio=Portfolio.stack()
print(Portfolio.swaplevel().sort_index())
Portfolio=Portfolio.sort_values(["Price"],ascending=False)
print (Portfolio)
Portfolio["Rank"]=Portfolio["Investment Value"].rank(
    ascending=False,
    method="min"
)
print (Portfolio)
print(Portfolio["Investment Value"].idxmax())
print(np.sqrt(Portfolio["Price"]))

def difference(x):
    return x.max() - x.min()

numeric_portfolio = Portfolio.select_dtypes(include="number")

print(numeric_portfolio.apply(difference))

print(
    numeric_portfolio.apply(
        lambda x: x.max() - x.min()
    )
)