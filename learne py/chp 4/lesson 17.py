import pandas as pd 
sales = pd.Series(
    [1200, 1500, 1800],
    index=["Jan", "Feb", "Mar"]
)
sales=sales.reindex(["Mar","Jan","Feb","Apr"])
sales_ffill=sales.ffill()
sales_bfill=sales.bfill()
print(sales)
print("ffill_sales")
print(sales_ffill)


print("bfill_saless")
print(sales_bfill)