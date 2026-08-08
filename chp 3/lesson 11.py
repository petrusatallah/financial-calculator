import numpy as np 
A = np.arange(16).reshape((4,4))

B = np.array([10,20,30,40])
ab=A+B
print(ab)
C = np.array([1,2,3,4])
ac=A+C
print(ac)
