import numpy as np
B = np.arange(1,10).reshape((3,3))
print(
    B[0],
    B[1],
    B[2],
    B[:0],
    B[:1],
    B[:2]
      )
for element in B.flat:
    print(element)
sum_of_rows=np.apply_along_axis(np.sum,axis=1,arr=B)
print(sum_of_rows)
sum_of_column=np.apply_along_axis(np.sum,axis=0,arr=B)
print(sum_of_column)
