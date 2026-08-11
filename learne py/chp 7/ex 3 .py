import pandas as pd 
import matplotlib.pyplot as plt

df=pd.DataFrame({
    "Month":["Jan","Feb","Mar","Apr"],
    "Sales":[100,120,140,170],
    "Profit":[20,30,40,45]
})
df["COGS"]=df["Sales"]-df["Profit"]

df.plot(kind="bar")
plt.show()


df.plot(kind="barh")
plt.show()


df.plot(kind="bar",stacked=True)
plt.show()


df.plot(kind="bar",color=["blue", "green", "red"])
plt.show()