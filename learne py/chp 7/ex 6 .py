import pandas as pd
import matplotlib.pyplot as plt 
import numpy as np 


df = pd.DataFrame({
    "Hours": [2, 4, 6, 8],
    "Score": [70, 80, 92, 97],
    "Attendance": [90, 95, 98, 99]
})

print(df)

fig=plt.figure()
ax=fig.add_subplot(
    111,
    projection="3d")
ax.scatter(
    df["Hours"],
    df["Score"],
    df["Attendance"]
)


plt.show()

fig=plt.figure()
ax=fig.add_subplot(
    111,
    projection="3d")

x = np.linspace(0, 5, 20)
y = np.linspace(0, 5, 20)

#x = np.array([1, 2, 3])
#y = np.array([1, 2, 3])

#x, y = np.meshgrid(x, y)

#z = np.array([[10, 12, 15],[20, 22, 25],[30, 35, 40]])

x, y = np.meshgrid(x, y)


z = x**2 + y**2

ax.plot_surface(x, y, z)

ax.view_init(
    elev=20,
    azim=45
)
plt.show()




