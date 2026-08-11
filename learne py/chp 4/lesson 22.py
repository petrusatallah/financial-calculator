import pandas as pd 
import numpy as np 
stocks = pd.DataFrame({
    "Company": ["Apple", "Tesla", "Microsoft", "Amazon", "NVIDIA"],
    "Price": [210, 310, 420, 225, 180],
    "Shares": [40, 15, 20, 30, 50]
})

print(stocks)
stocks=stocks.set_index("Company")
print(stocks)
stocks["Portfolio Value"]=stocks["Price"] * stocks["Shares"]
stocks["Target Price"]=stocks["Price"]*1.15
print(stocks[stocks["Price"]>220])
print(stocks[stocks.index.isin(["Apple", "Tesla", "NVIDIA"])])
print(stocks.sort_values(by="Price",ascending=False))
print(stocks["Portfolio Value"].rank(ascending=False))
print(stocks.corr())
print(stocks.describe())
print(stocks["Portfolio Value"].idxmax())