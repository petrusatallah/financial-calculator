import numpy as np 
import pandas as pd
employees = pd.DataFrame({
    "Employee": ["Peter", "John", "Sarah", "Mike", "Emma"],
    "Department": ["Finance", "HR", "Finance", "IT", "HR"],
    "Salary": [2500, np.nan, 3200, 2800, 3000]
})
print("employees",employees)
print(employees["Salary"])


employees["Salary"] = employees["Salary"].replace(np.nan, 2000)
print (employees)
employees["Bonus"]=employees["Salary"]*0.1
print(employees["Bonus"])
print(employees[employees["Salary"]>2700])
print(employees.isnull())
employees=employees.dropna(how="all")
print(employees)
print(employees.describe())