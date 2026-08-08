import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

df = pd.DataFrame({
    "Company": ["Apple", "Tesla", "Microsoft", "Amazon", "NVIDIA"],
    "Price": [210, 310, 420, 225, 180],
    "Shares": [40, 15, 20, 30, 50]
})

fig=plt.figure(figsize=(10,6))
gs=plt.GridSpec(2,2)
ax1=fig.add_subplot(gs[0,0])
ax1.plot(df["Company"],df[["Price","Shares"]])
ax1.set_title("Price value")
plt.xlabel(" Company")
plt.ylabel("$ price")
plt.grid(True)
#plt.xticks(rotation=-20)
plt.legend()


ax2=fig.add_subplot(gs[1,1])
ax2.pie(df["Shares"],labels=df["Company"],autopct="%1.1f%%")
ax2.legend()

ax2.axis("equal")



ax3=fig.add_subplot(gs[1,0])
df.plot(
    x="Company",
    y=["Price", "Shares"],
    kind="bar",
    ax=ax3)
plt.xticks(rotation=-20)
ax3.set_title("compar co")
ax3.set_xlabel("Companys")
ax3.set_ylabel("Price per $")

ax4=fig.add_subplot(gs[0,1])
df.plot(
    x="Company",
    y=["Price", "Shares"],
    kind="hist",
    ax=ax4)


ax4.set_title("compar co")
ax4.set_xlabel("Companys")
ax4.set_ylabel("Price per $")

plt.tight_layout()
plt.savefig(
    "dashboard.png",
    dpi=300
)
plt.show()


