import matplotlib.pyplot as plt
import pandas as pd


df = pd.DataFrame(
    {
        "Apple":[180,185,190,200],
        "Tesla":[250,260,255,270],
        "Microsoft":[150,160,170,180]
    },

    index=["Q1","Q2","Q3","Q4"]
)

plt.plot(df)

plt.title("Stock Prices")
plt.legend(df[["Apple","Tesla","Microsoft"]],loc=3)
plt.xlabel("Quarter")

plt.ylabel("Price")

plt.show()

df.plot(kind="bar")
#it dos this otomatiqly 
#plt.legend(df[["Apple","Tesla","Microsoft"]],loc=10) 

plt.title("stocks prices")
plt.xlabel("stocks")
plt.ylabel("price")

plt.show()

df.plot(
    kind="bar",
    stacked=True)

plt.show()

df["Apple"].plot(
    kind="pie",
    figsize=(10,6),
    autopct="%1.1f%%"
)
plt.axis("equal")
plt.show()



