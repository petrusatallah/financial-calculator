import pandas as pd

df = pd.DataFrame({
    "Product":["Shoes","Shoes","Bag","Bag","Hat","Hat"],
    "Price":[120,120,80,80,40,40],
    "Color":["Red","Red","Blue","Blue","Black","Black"]
})

print(df.duplicated())

clean_df=df.drop_duplicates()
print(clean_df)

new_df=clean_df.replace({
    "Red":"White",
    "Blue":"Green",
    "Black":"Gray"
})
print(new_df)

rename_df = new_df.rename(columns={
    "Price": "Unit Price",
    "Color": "Product Color"
})

print(rename_df)

rename_df.index = ["A", "B", "C"]

print(rename_df)