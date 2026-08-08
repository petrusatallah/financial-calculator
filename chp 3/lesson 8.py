import numpy as np 
A = np.arange(1,25)
matrix_1=A.reshape((4,6))
print(matrix_1)
matrix_2=A.reshape((6,4))
flat=matrix_1.ravel()
tanspose=matrix_1.transpose()
print(matrix_1,matrix_2,flat,tanspose)
print(matrix_1.shape)
print(tanspose.shape)

