import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

df = pd.DataFrame(
    {
        "Hours":[2,4,6],
        "Score":[70,80,92],
        "Attendance":[90,95,98]
    }
)


fig = plt.figure()

ax = fig.add_subplot(
    121,
    projection="3d"
)

x = np.arange(-5,10)

y = np.arange(-5,10)

X,Y = np.meshgrid(x,y)

Z = X**2 + Y**2

ax.plot_surface(X,Y,Z,cmap=plt.cm.hot)

ax.view_init(
    elev=20,
    azim=45
)
ax.scatter(
    df["Hours"],
    df["Score"],
    df["Attendance"]
)
plt.show()