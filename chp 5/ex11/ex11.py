import pandas as pd
from sqlalchemy import create_engine


df_emp=pd.read_csv("employees.csv",sep=",")

df_ex=pd.read_csv("expenses.csv",sep=",")

df_sal=pd.read_csv("sales.csv",sep=",")

total_sales=(df_sal["Price"]*df_sal["Quantity"]).sum()
print("total sales revenue:",
      total_sales)

total_expenses=df_ex["Amount"].sum()
print("total_expence:",
      total_expenses)
profit=total_sales-total_expenses
print("profit:",profit)


sales_report = pd.DataFrame({
    "Total Sales Revenue": [total_sales],
    "Total Expenses": [total_expenses],
    "Profit": [profit]
})

print("\nSales Report:")
print(sales_report)

# 5. Save the sales report in different formats

# CSV
sales_report.to_csv(
    "sales_report.csv",
    index=False
)

# Excel
sales_report.to_excel(
    "sales_report.xlsx",
    index=False
)

# JSON
sales_report.to_json(
    "sales_report.json",
    orient="records",
    indent=4
)

# Pickle
sales_report.to_pickle(
    "sales_report.pkl"
)

# 6. Store the report in SQLite
engine = create_engine("sqlite:///company.db")

sales_report.to_sql(
    "SalesReport",
    engine,
    index=False,
    if_exists="replace"
)

# 7. Read the report back from SQLite
sql_report = pd.read_sql(
    "SELECT * FROM SalesReport",
    engine
)

print("\nReport read from SQLite:")
print(sql_report)
