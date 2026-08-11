import matplotlib.pyplot as plt

months = ["Jan","Feb","Mar","Apr"]

sales = [100,120,150,170]

profit = [20,30,40,45]

fig = plt.figure()

ax1 = fig.add_axes([0.1, 0.1, 0.8, 0.8])

ax2 = fig.add_axes([0.55, 0.2, 0.3, 0.3])

ax1.plot(months, sales)
ax1.set_title("Sales")

ax2.plot(months, profit)
ax2.set_title("Profit")

plt.show()