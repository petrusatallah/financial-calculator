import pandas as pd 
data={
    "product":["Mouse","Keyboard","Monitor","Laptop"],
    "price":[25,50,200,900],
    "quantity":[10,8,5,3]
}
dataf=pd.DataFrame(data)
print("original data")
print(dataf)
dataf["revenue"]=dataf["price"]*dataf["quantity"]
print("data_revenue")
print (dataf)
dataf["VAT"]=dataf["revenue"]*0.11
price3050=dataf[(dataf["price"]>30)&(dataf["price"]<500)]
print("price oriented")
print(price3050)
print(dataf[dataf["product"].isin(["mouse","laptop"])])
dataf=dataf.drop(1)
dataf=dataf.reindex([0,2,2,3,"printer"])


dataf.loc["printer"] = ["printer", 150, 4, 600, 66]


dataf= dataf.ffill()


print("transpose tabel")
print(dataf.T)