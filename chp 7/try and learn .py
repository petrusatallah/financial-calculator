import matplotlib.pyplot as plt
months=["January", "February", "March", "April"]
plt.plot(["January", "February", "March", "April"],[20,40,40,50], label="price")
plt.plot(months, [15, 25, 35, 45], "ro")
plt.title("Monthly Sales")
plt.axis([-1,5,0,60])
plt.xlabel("Month")
plt.ylabel("Sales")
plt.text("April", 50, "Highest Growth")
plt.grid(True)
plt.legend(loc="lower right")#or loc=1-10
plt.annotate(
    "middel Sales",
    xy=("March",40),
    xytext=(0,45),
    arrowprops=dict(facecolor="black")
)
plt.title(
    r"$y=x^2$"
)
plt.show()
#plt.plot(["January", "February", "March", "April"],[20,30,40,50])
#plt.show()
#plt.xlabel("jkr")
#plt.ylabel("kkrk")
#plt.title("jrjr")


scores = [70,75,75,80,82,82,82,90]

plt.hist(scores,bins=20)

plt.show()

departments = ["HR", "Sales", "IT"]
budget = [20, 50, 30]

explode = [0.1, 0,0.01]

plt.pie(
    budget,
    labels=departments,
    explode=explode,
    autopct="%1.1f%%"
)

plt.show()

values = [20, 50, 30]

# Make the figure very wide
plt.figure(figsize=(10, 3))

plt.pie(
    values,
    labels=["HR", "Sales", "IT"],
    autopct="%1.1f%%"
)

plt.axis("equal")

plt.title("With axis('equal')")

plt.show()

