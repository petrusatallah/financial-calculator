import pandas as pd
dfskip=pd.read_csv(
    "monthly salery.csv",
    skiprows=5,
    sep=",")
print(dfskip)

dfnrow=pd.read_csv(
    "monthly salery.csv",
    nrows=10,
    sep=",")
print(dfnrow)

dfchunky=pd.read_csv(
    "monthly salery.csv",
    chunksize=2,
    sep=",")

for chunk in dfchunky:
    print(chunk)
total_sales=0

total_sales += chunk["Sales"].sum()

print(total_sales)