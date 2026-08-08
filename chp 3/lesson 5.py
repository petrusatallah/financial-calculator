import numpy as np 
A = np.arange(1,21)
print(A[0])
print(A[19])
print(A[4])
print(A[4:9])
print(A[::2])
print(A[::-1])
B = np.arange(1,17).reshape((4,4))
print(B)
print(
    "matrix",B,
    "row 2",B[2],
    "column 3",B[:,3],
    "element(1,2)",B[1,2],
    "last row",B[-1],
    "last column",B[:,-1]
)