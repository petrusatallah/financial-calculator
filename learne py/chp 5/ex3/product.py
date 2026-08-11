import pandas as pd
df=pd.read_json(
    r"C:\Users\Admin\Desktop\python\run python\chp 5\ex3\products.json")
print(df)

df["Discount Price"]=df["Price"]*0.9
print(df)

df.to_json(
    "products_discount.json",
    indent=4
)
