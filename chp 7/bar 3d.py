import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

fig = plt.figure()

ax = fig.add_subplot(
    111,
    projection="3d"
)

products = np.arange(3)

sales_2025 = [100, 80, 50]
sales_2026 = [120, 90, 70]

ax.bar(
    products,
    sales_2025,
    zs=0,
    zdir="y"
)

ax.bar(
    products,
    sales_2026,
    zs=1,
    zdir="y"
)

# X-axis: replace 0, 1, 2 with product names
ax.set_xticks(products)
ax.set_xticklabels(["Shoes", "Bags", "Hats"])

# Y-axis: replace 0.0, 0.2, ... 1.0 with year names
ax.set_yticks([0, 1])
ax.set_yticklabels(["2025", "2026"])


months = ["Jan","Feb","Mar","Apr"]

sales = [100,120,150,170]

profit = [20,30,40,45]


ax2 = fig.add_axes([0.7,0.1,0.2,0.25])


ax2.plot(months, profit)


ax.set_xlabel("Product")
ax.set_ylabel("Year")
ax.set_zlabel("Sales")

ax.view_init(
    elev=20,
    azim=45
)

plt.show()