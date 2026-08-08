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
Employee_Salary_Department["Bonus"]=Employee_Salary_Department["Salary"]*0.1
print(Employee_Salary_Department)
Employee_Salary_Department=Employee_Salary_Department.drop([1])
print(Employee_Salary_Department)
Employee1700=Employee_Salary_Department[Employee_Salary_Department["Salary"]>1700]
print(Employee1700)
Employee_Salary_Department.loc[2, "Salary"] = 2500
print(Employee_Salary_Department.T)
Peter_Mike = Employee_Salary_Department[
    Employee_Salary_Department["Employee"].isin(["Peter", "Mike"])
]

print(Peter_Mike)