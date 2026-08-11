import pandas as pd 
Data={
    "Employee":["Peter","John","Sarah","Mike"],
    "Salary":[1500,1800,2200,1700],
    "Department":["Finance","HR","IT","Sales"]
}
Employee_Salary_Department=pd.DataFrame(Data)
print(Employee_Salary_Department)
print(Employee_Salary_Department["Salary"])
print(Employee_Salary_Department.loc[1])
print(Employee_Salary_Department.loc[0])
print(Employee_Salary_Department.index)
print(Employee_Salary_Department.columns)

print(Employee_Salary_Department["Salary"])

print(Employee_Salary_Department.loc[0])