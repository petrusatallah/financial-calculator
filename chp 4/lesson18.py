import pandas as pd 
sales1=pd.Series([1200,1500,1800],
                 index=["jan","feb","mar"])
sales2=pd.Series([300,500,700],
                 index=["feb","mar","apr"])
total_sales=sales1+sales2
print("total sales",
      total_sales)