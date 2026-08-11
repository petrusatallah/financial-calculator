import pandas as pd

data = {
    "Country": ["USA", "USA", "UK", "UK"],
    "Product": ["Shoes", "Bag", "Shoes", "Bag"],
    "Price": [35, 50, 40, 60]
}

df = pd.DataFrame(data)

print(df.unstack(1))
print(df)