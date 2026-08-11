import pandas as pd 
import numpy as np 

grades = pd.DataFrame({
    "Math": [80, 90, np.nan, 70],
    "Physics": [75, 95, 85, np.nan],
    "English": [88, 92, 81, 79]
})

print(grades)

print(grades.isnull())

grades=grades.fillna(grades.mean())

print(grades)

def diffrence(x):
    return x.max()-x.min()
print(grades.apply(diffrence))

print(grades.apply(lambda x: x.max()-x.min()))
print(np.sqrt(grades["English"]))
print(grades.mean())

grades["Total"] = grades.sum(axis=1)

print(grades.loc[grades["Total"].idxmax()])
