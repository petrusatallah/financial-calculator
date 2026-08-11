import pandas as pd

df = pd.DataFrame({
    "Department":["HR","HR","IT","IT","Sales","Sales"],
    "Employee":["Ali","Sara","John","Maya","Peter","Rami"],
    "Salary":[1800,2200,3000,2800,2500,2700]
})
def Salery_range(group):
    return group.max()-group.min()

result=df.groupby("Department")["Salary"].agg([
                                                "sum",
                                                "mean",
                                                "min",
                                                "max",
                                                "std",
                                                Salery_range
])
print(result)
result=result.add_prefix("Department_")
print(result)
df["Department_Total"]=df.groupby("Department")["Salary"].transform("sum")
df["Department_Average"]=df.groupby("Department")["Salary"].transform("mean")
df["Difference_From_Average"]=df["Salary"]-df["Department_Average"]
df["Percentage_of_Department"]=df["Salary"]/df["Department_Total"]*100
df.to_excel("df.xlsx",index=False)
