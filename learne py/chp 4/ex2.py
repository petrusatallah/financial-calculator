import numpy as np 
import pandas as pd 

products = pd.DataFrame({
    "Product": ["Mouse", "Keyboard", "Monitor", "Laptop", "Printer"],
    "Price": [25, 50, 200, 900, 150],
    "Quantity": [10, 8, 5, 3, 4]
})

products["Revenue"]=products["Price"]*products["Quantity"]
products["VAT"]=products["Revenue"]*0.11

print("products:")
print(products)

print("products with condition:")
print(products[(products["Price"]>30)&(products["Price"]<500)])

print(products.loc[0],products.loc[3],products.loc[4])
# or i can use same result easeyer to output 
print(products[products["Product"].isin(["Mouse", "Laptop", "Printer"])])

orgenized_products=products.sort_values(
    by="Revenue",
    ascending=False)
print("orgenized_products:")
print(orgenized_products)

print("highest revenue:")
print(products.loc[products["Revenue"].idxmax()])
print("Price squeware:")
print(np.sqrt(products["Price"]))

def difference(x):
    return x.max()-x.min() 

#this can work but i need to select the products first 
numeric_products = products.select_dtypes(include="number")
print(products.apply(difference, numeric_only=True))
#if not this can work
print(products[["Price", "Quantity", "Revenue", "VAT"]].apply(difference))
