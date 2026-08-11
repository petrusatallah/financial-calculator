import pandas as pd

df = pd.DataFrame({
    "Store":["A","A","B","B","C","C"],
    "Product":["TV","Phone","TV","Phone","TV","Phone"],
    "Revenue":[4000,3500,6000,6500,2000,2500]
})

def store_status(group):
    if group["Revenue"].mean() > 5000:
        return "Excellent"
    else:
        return "Needs Improvement"  
group_df=df.groupby("Store").apply(store_status, include_groups=False)
print(df)
print(group_df)

def highest_product(group):
    highest = group["Revenue"].idxmax()
    return group.loc[highest, "Product"]

group_product=df.groupby("Store").apply(highest_product, include_groups=False)
print(group_product)

def performance(group):
    average_revenue = group["Revenue"].mean()
    highest_revenue = group["Revenue"].max()
    lowest_revenue = group["Revenue"].min()

    if average_revenue > 5000:
        status = "Excellent"
    else:
        status = "Needs Improvement"

    return pd.Series({
        "Average": average_revenue,
        "Highest": highest_revenue,
        "Lowest": lowest_revenue,
        "Status": status
    })


final_result = df.groupby("Store").apply(
    performance,
    include_groups=False
)

print("\nFull performance summary:")
print(final_result)
final_result.to_excel("final.xlsx",index=False)

