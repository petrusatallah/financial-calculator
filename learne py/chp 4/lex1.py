import pandas as pd
import numpy as np

employees = pd.DataFrame({
    "Employee": ["Peter", "John", "Sarah", "Mike", "Emma"],
    "Department": ["Finance", "HR", "Finance", "IT", "HR"],
    "Salary": [2500, np.nan, 3200, 2800, 3000]
})


print("employees:")

print(employees)

print(employees["Salary"])


print("Missing values:")

print(employees.isnull())

employees.loc[1,"Salary"]=2000
employees["Bonus"]=employees["Salary"]*0.12


print("salary:")

print(employees[employees["Salary"]>2700])


print("descriptive:")

print(employees.describe())


print("Correlation matrix:")

print(employees.corr(numeric_only=True))

print(employees)