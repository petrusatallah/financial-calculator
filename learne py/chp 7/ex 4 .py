import pandas as pd 
import matplotlib.pyplot as plt

Department=["HR","Sales","IT"]
Budget=[20,50,30]
ex=[0.1,0.1,0.1]
plt.pie(Budget,labels=Department,autopct="%1.1f%%",explode=ex)


plt.axis("equal")


plt.show()