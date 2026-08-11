import pandas as pd
inventory = pd.DataFrame({
    "Item":["Shoes","Bag","Watch"],
    "Stock":[50,30,12]
})
inventory.to_pickle(
    "dfi.pkl")
df=pd.read_pickle("dfi.pkl")
print ("new df:")

print(df)