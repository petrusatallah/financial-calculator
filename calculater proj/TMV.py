import pandas as pd
import numpy as np

pv = 2000
rate = 0.08
years = 5


def Future_value(pv, rate, years):
    Fv = pv * (1 + rate) ** years
    return Fv


pv = 2000
rate = 0.08
years = 5
results = Future_value(pv, rate, years)
print(results)


def Present_value(fv, rate, years):
    pv = fv / (1 + rate) ** years
    return pv


portfolio = pd.DataFrame(
    {
        "PV": [1000, 2000, 1500, 5000],
        "Rate": [0.05, 0.08, 0.10, 0.07],
        "Years": [3, 5, 4, 2],
    }
)
portfolio["FV"] = portfolio.apply(
    lambda row: Future_value(row["PV"], row["Rate"], row["Years"]), axis=1
)

print(portfolio)

portfolio2 = pd.DataFrame(
    {
        "FV": [1000, 2000, 1500, 5000],
        "Rate": [0.05, 0.08, 0.10, 0.07],
        "Years": [3, 5, 4, 2],
    }
)
portfolio2["PV"] = portfolio2.apply(
    lambda row: Present_value(row["FV"], row["Rate"], row["Years"]), axis=1
)

print(portfolio2)
