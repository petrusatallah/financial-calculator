import numpy as np
import pandas as pd 

stocks = pd.DataFrame({
    "Company": ["Apple", "Tesla", "Microsoft", "Amazon", "NVIDIA"],
    "Price": [210, 310, 420, 225, 180],
    "Shares": [40, 15, 20, 30, 50]
})


stocks=stocks.set_index(["Company"])
print(stocks)

stocks["Portfolio Value"]=stocks["Price"]*stocks["Shares"]
stocks["Target Price"]=stocks["Price"]*1.15
print(stocks)


print(stocks[stocks["Price"]>220])
print(stocks.loc[["Apple","Tesla","NVIDIA"]])

stocks=stocks.sort_values("Price",ascending=False)
print("new stocks :")
print(stocks)

stocks["Rank"]=stocks["Portfolio Value"].rank(
                                            ascending=False,
                                            method="min")
print(stocks[["Rank","Portfolio Value"]])
print("highest portfolio value:")
print(stocks.loc[stocks["Portfolio Value"].idxmax()])
print(stocks["Price"].mean())
print(stocks.corr(numeric_only=True))
stocks.to_excel("stocks.xlsx")