import pandas as pd 
stocks={
    "Company":["Apple","Microsoft","Tesla","Amazon","NVIDIA"],
    "Price":[210,420,310,225,180],
    "Shares":[40,20,15,30,50],
}

stocks=pd.DataFrame(stocks)
stocks =stocks.set_index("Company")
print("stocks")

print(stocks)
stocks["Portfolio Value"]=stocks["Price"]*stocks["Shares"]
print("stocks value")

print(stocks)

stocks["Target Price"]=stocks["Price"]*1.15
print("stocks Target")

print(stocks)
Price250=stocks[stocks["Price"]>250]
print("Price>250")

print(Price250)
ShowATN = stocks.loc[["Apple", "Tesla", "NVIDIA"]]
print("ShowATN")

print(ShowATN)
stocks=stocks.reindex(["Apple","Microsoft","Tesla","Amazon","NVIDIA","Meta"])
print(stocks)
stocks=stocks.ffill()
print(stocks)
print(stocks["Portfolio Value"].idxmax())
print(stocks["Portfolio Value"].idxmin())
print(stocks.T)
