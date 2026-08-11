import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

months=["Jan","Feb","Mar","Apr"]
sales=[100,120,140,170]

df=pd.DataFrame(
    {
    "Months": months,
    "Sales": sales
    }
)

print(df)

plt.plot(df["Months"], df["Sales"])
plt.title("monthly sales")
plt.xlabel("Months")
plt.ylabel("Sales")
plt.grid(True)
plt.savefig(
    "Msales.png",
    dpi=300
)
plt.show()