import pandas as pd 
df=pd.read_csv("sales.csv",sep=",")
print(df)

print("just to columns:")
print(df[["Product","Price"]])

print("just 3 rows:")
print(df.loc[[0,1,2]])


df["Revenue"]=df["Price"]*df["Quantity"]
print("add new column:")
print(df)

df.to_csv(
    "sales_report.csv",
    index=False
)
