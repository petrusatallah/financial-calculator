import pandas as pd
df=pd.read_html(
    r"C:\Users\Admin\Desktop\python\run python\chp 5\ex5\website.html")
print(df)
tabel1=df[0]
print(tabel1)