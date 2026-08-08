import pandas as pd
from sqlalchemy import create_engine

# Create the DataFrame
sales = pd.DataFrame({
    "Product": ["Shoes", "Bag", "Wallet", "Watch", "Heels"],
    "Price": [120, 80, 45, 200, 150],
    "Quantity": [15, 10, 25, 8, 12]
})

# Add Revenue column
sales["Revenue"] = sales["Price"] * sales["Quantity"]

# ----------------------------
# CSV
# ----------------------------
sales.to_csv("sales.csv", index=False)

csv_df = pd.read_csv("sales.csv")

# ----------------------------
# Excel
# ----------------------------
csv_df.to_excel("sales.xlsx", index=False)

excel_df = pd.read_excel("sales.xlsx")

# ----------------------------
# JSON
# ----------------------------
excel_df.to_json("sales.json")

json_df = pd.read_json("sales.json")

# ----------------------------
# Pickle
# ----------------------------
json_df.to_pickle("sales.pkl")

pickle_df = pd.read_pickle("sales.pkl")

# ----------------------------
# SQLite
# ----------------------------
engine = create_engine("sqlite:///sales.db")

pickle_df.to_sql(
    "sales",
    engine,
    index=False,
    if_exists="replace"
)

sql_df = pd.read_sql(
    "SELECT * FROM sales",
    engine
)

# ----------------------------
# Final DataFrame
# ----------------------------
print(sql_df)