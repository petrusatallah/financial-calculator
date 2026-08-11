import numpy as np
import pandas as pd

np.random.seed(10)

df = pd.DataFrame({
    "Salary":[1800,2200,2500,3000,3500,4000,4500,10000]
})
df["Groupc"]=pd.cut(df["Salary"],bins=4)
print(df)

df["Groupq"]=pd.qcut(df["Salary"],q=4)
print(df)

print(df["Salary"].agg(["mean","std"]))

mean = df["Salary"].mean()
std = df["Salary"].std()

lower_limit = mean - 3 * std
upper_limit = mean + 3 * std

outliers = df[
    (df["Salary"] < lower_limit) |
    (df["Salary"] > upper_limit)
]

print("Outliers:")
print(outliers)

clean_df = df[
    (df["Salary"] >= lower_limit) &
    (df["Salary"] <= upper_limit)
]

print("\nWithout Outliers:")
print(clean_df)