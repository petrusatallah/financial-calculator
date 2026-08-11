import pandas as pd 

txt=pd.read_csv(
    r"C:\Users\Admin\Desktop\python\run python\chp 5\ex2\employees.txt",
    sep="|"
    )
print(txt)

print(txt[txt["Salary"]>3500])