import pandas as pd

sales = pd.DataFrame({
    "City":["Beirut","Beirut","Tripoli","Tripoli"],
    "Quarter":["Q1","Q2","Q1","Q2"],
    "Sales":[120,150,200,220]
})

pivot_sales=sales.pivot(
    index="City",
    columns="Quarter",
    values="Sales"
)
print(pivot_sales)

pivot_sales_unstack=pivot_sales.stack().reset_index(name="Sales")
print(pivot_sales_unstack)

sales = pd.DataFrame({
    "City": ["Beirut", "Beirut", "Tripoli", "Tripoli"],
    "Quarter": ["Q1", "Q2", "Q1", "Q2"],
    "Sales": [120, 150, 200, 220]
})

multi_sales = sales.set_index(["City", "Quarter"])

print(multi_sales)

print(multi_sales.stack())
print(multi_sales.unstack())

# 6. Swap the index levels
swapped = multi_sales.swaplevel()

print("\n6. swaplevel()")
print(swapped)


# 7. Sort the swapped index
sorted_swapped = swapped.sort_index()

print("\n7. Sorted swapped index")
print(sorted_swapped)


