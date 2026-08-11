import pandas as pd
students = pd.DataFrame({
    "Name":["Peter","Sara","John"],
    "Grade":[88,92,79]
})
students.to_excel("students.xlsx",index=False)
df_student=pd.read_excel("students.xlsx")
print(df_student)