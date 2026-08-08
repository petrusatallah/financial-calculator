import pandas as pd
from sqlalchemy import create_engine
employees = pd.DataFrame({
    "Name":["Peter","Sara","John"],
    "Salary":[3000,3500,4200]
})
engine=create_engine("sqlite:///cop.db")
employees.to_sql(
    "employees",
    engine,
    index=False,
    if_exists="replace"
)
df=pd.read_sql(
    "SELECT * FROM employees WHERE Salary > 3200",
    engine
)
print(df)
