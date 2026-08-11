import numpy as np 
scores = np.array([55,72,90,43,88,67,95])
print(
    scores[scores>70],
    scores[scores<60],
    scores[(scores>60) & (scores<90)]
    )
mask= scores > 80
print(mask)
grades = np.array([
    [75,82,90],
    [55,68,72],
    [99,100,88]
])
print(grades[grades>80])
print(grades[grades<70])