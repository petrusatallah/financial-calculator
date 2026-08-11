import pandas as pd

df = pd.DataFrame({
    "City":["Beirut","Beirut","Tripoli","Tripoli","Saida","Saida"],
    "Category":["Shoes","Bags","Shoes","Bags","Shoes","Bags"],
    "Sales":[120,150,200,180,170,160]
})

def range_function(x):
    return x.max()-x.min()

result=df.groupby("City")["Sales"].agg([
                                        "sum",
                                        "max",
                                        "mean",
                                        "std",
                                        range_function])
print(result)

df["City_Total"]=df.groupby("City")["Sales"].transform("sum")

df["City_average"]=df.groupby("City")["Sales"].transform("mean")

df["Percentage"]=df["Sales"]/df["City_Total"]*100

def current_state(group):
    if group["Sales"].mean()> 170:
        return "Excellent"
    else:
        return "Needs Improvement"
final_result=df.groupby("City").apply(current_state, include_groups=False)
print(df)
print (final_result)