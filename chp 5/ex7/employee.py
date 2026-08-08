import pandas as pd 
employees = pd.DataFrame({
    "Name":["Peter","Sara","John"],
    "Salary":[3000,3500,4200]
})
from sqlalchemy import create_engine
engine=create_engine("sqlite:///company.db")
employees.to_sql(
    "employees",
    engine,
    index=False,
    if_exists="replace"
)
df=pd.read_sql(
    "employees",
    engine
)
print(df)
