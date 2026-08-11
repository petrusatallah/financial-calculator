import pandas as pd 
grades=pd.Series([85,90,78,95],
                index=["Math","physics","biology","chemistry"])
print(grades)
print(grades.values,grades.index)
print(grades.idxmin(),grades.idxmax())
print(grades.index.is_unique)
