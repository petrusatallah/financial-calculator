import numpy as np 
data=np.array([
    (1,"Peter",3.4),
    (2,"John",2.8),
    (3,"ali",3.9)
],
dtype=([
    ("ID","u4"),
    ("Name","a10"),
    ("GPA","f4")
]))
print(data)
print(data["Name"],data["GPA"],data["ID"])
data.dtype.names=("studentID","studentname","studentGPA")
print(data["studentname"])
print(data)

