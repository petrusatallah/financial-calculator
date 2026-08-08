import pandas as pd 
import matplotlib.pyplot as plt

df=pd.DataFrame({
    "Month":["Jan","Feb","Mar","Apr"],
    "Sales":[100,120,140,170],
    "Profit":[20,30,40,45]
})
#plt.plot(df["Month"], df["Sales"], label="Sales")

#plt.plot(df["Month"], df["Profit"], label="Profit")
# bouth works just need to whright it like this 
df.plot(x="Month", y=["Sales","Profit"])
plt.legend(loc=4)
plt.title("df")
plt.xlabel("Months")
plt.grid(True)
plt.savefig(
    "Msales 2.png",
    dpi=300
)

plt.show()
