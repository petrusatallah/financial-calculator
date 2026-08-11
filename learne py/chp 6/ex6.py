import pandas as pd
import numpy as np
import re


df = pd.DataFrame({
    "City":["Beirut","Beirut","Tripoli","Tripoli","Saida","Saida"],
    "Category":["Shoes","Bags","Shoes","Bags","Shoes","Bags"],
    "Sales":[120,150,200,180,170,160]
})
result=df.groupby("City")
print("result:")
print(result)
print(result.groups)

result = df.groupby("City")

for city, group in result:
    print("City:", city)
    print(group)
    print()

print(result["Sales"].sum())
print(result["Sales"].mean())

result=df.groupby(["City","Category"])
print(result)

print(result["Sales"].sum())
