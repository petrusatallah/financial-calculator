import matplotlib.pyplot as plt

months = ["Jan", "Feb", "Mar", "Apr"]
sales = [100, 120, 150, 170]

plt.plot(months, sales)

plt.title("Monthly Sales")

plt.savefig("sales.png", dpi=300)

plt.show()