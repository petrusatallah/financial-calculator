import numpy as np 
sales = np.array([
1200,
1350,
1400,
1550,
1600,
1700,
1800,
1900,
2000,
2100,
2200,
2300
])
total_sales=np.sum(sales)
print("total:",total_sales)
avrage_sales=np.mean(sales)
print("avrage:",avrage_sales)
Max_sales=np.max(sales)
print("max:",Max_sales)
lowest_sales=np.min(sales)
print("lowest sales:",lowest_sales)
standerd_diviation=np.std(sales)
print("standerd diviation:",standerd_diviation)
sales_matrix= sales.reshape(4,3)
print(sales_matrix)
print(sales_matrix[1])
print(sales_matrix[3,2])
increase_sales=sales_matrix*1.1
print(increase_sales)
print(increase_sales[increase_sales>1800])
expenses = np.random.randint(800, 1501, 12)
print(expenses)
profit=sales-expenses
print(profit)
dot_product = np.dot(sales, expenses)
print(dot_product)
matrix_profit=profit.reshape(4,3)
print(matrix_profit)
tran_profit=matrix_profit.transpose()
print(tran_profit)
parta,partb=np.split(tran_profit,2,axis=1)
print(parta,partb)