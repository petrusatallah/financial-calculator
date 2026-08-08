import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


df = pd.DataFrame({
    "Date": [
        "2026-01-01",
        "2026-02-01",
        "2026-03-01",
        "2026-04-01"
    ],
    "Sales": [100,120,150,170]
})

print(df)

df["Date"] = pd.to_datetime(df["Date"])

df.plot(x="Date",y="Sales")

months = mdates.MonthLocator()

formatter = mdates.DateFormatter("%Y-%m")
ax = plt.gca()

ax.xaxis.set_major_locator(months)

ax.xaxis.set_major_formatter(formatter)

plt.show()
