import numpy as np 
A = np.arange(24).reshape((4,6))
top,botom=np.vsplit(A,2)
print(top,botom)
left,right=np.hsplit(A,2)
print(left,right)
A1,A2,A3=np.split(A,[1,2],axis=0)
print(A1,A2,A3)