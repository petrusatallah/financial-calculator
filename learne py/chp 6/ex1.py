import pandas as pd

employees = pd.DataFrame({
    "ID":[101,102,103,104],
    "Name":["Ali","Sara","Peter","Maya"],
    "Department":["Sales","IT","HR","Finance"]
})

salaries = pd.DataFrame({
    "ID":[101,102,103,105],
    "Salary":[2000,2500,1800,3000]
})

bonuses = pd.DataFrame({
    "ID":[101,103,104],
    "Bonus":[300,200,250]
})

comp=pd.merge(employees,salaries,on="ID",how="inner")
print("original company:")
print(comp)

comp_left=pd.merge(employees,salaries,on="ID",how="left")
print("original company left :")
print(comp_left)

company=pd.merge(comp,bonuses,on="ID",how="inner")
print("howle company:")
print(company)

Q1 = pd.Series([120, 140, 160])
Q2 = pd.Series([150, 170, 180])

quarters = pd.concat([Q1, Q2],ignore_index=True)

print("Concatenated Series:")
print(quarters)

first_data = pd.DataFrame({
    "Name": ["Ali", "Sara", None],
    "Salary": [2000, None, 1800]
})

second_data = pd.DataFrame({
    "Name": [None, "Sara", "Peter"],
    "Salary": [2200, 2500, None]
})

print("First DataFrame:")
print(first_data)

print("Second DataFrame:")
print(second_data)

combined_data = first_data.combine_first(second_data)

print("Combined DataFrame:")
print(combined_data)