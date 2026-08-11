import numpy as np 
A = np.ones((2,3))

B = np.zeros((2,3))
ABV=np.vstack((A,B))
ABH=np.hstack((A,B))
a = np.array([1,2,3])

b = np.array([4,5,6])

c = np.array([7,8,9])
abcc=np.column_stack((a,b,c))
abcr=np.row_stack((a,b,c))
print(ABV,ABH,abcc,abcr)

