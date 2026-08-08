import pandas as pd

sales = pd.Series(
    [100, 120, 80, 90, 150, 170, 130, 140],
    index=[
        ["Shoes", "Shoes", "Bags", "Bags",
         "Shoes", "Shoes", "Bags", "Bags"],
        ["Black", "White", "Black", "White",
         "Red", "Blue", "Red", "Blue"]
    ]
)

sales.index.names = ["Product", "Color"]

print(sales)

print(sales["Shoes"])

print(sales[:,"Red"])

print(sales["Bags","Blue"])

sales=sales.unstack()
print(sales)

sales=sales.stack()
print(sales)

sales=sales.swaplevel().sort_index()

print(sales)

total_sales_product=sales.groupby(level="Product").sum()

print ("total_sales_product")

print(total_sales_product)

total_sales_color=sales.groupby(level="Color").sum()

print("total_sales_color")
print(total_sales_color)

average_sales_product = sales.groupby(level="Product").mean()

print("Average sales by product:")
print(average_sales_product)
