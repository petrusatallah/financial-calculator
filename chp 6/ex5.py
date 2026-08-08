import pandas as pd
import numpy as np

df = pd.DataFrame({
    "Info":[
        "Peter 25",
        "Ali 31",
        "Sara 19",
        "John 42",
        "Maya 27"
    ]
})

shuffel=df.take([4,3,1,2,0])
shuffel=shuffel.reset_index(drop=True)
print("shuffel:")
print(shuffel)

random=np.random.randint(
    0,
    len(df),
    size=3
)
print("random:")
print(random)

permutation = np.random.permutation(len(df))

print(permutation)

print(df.iloc[permutation])

saperat = df["Info"].str.split(" ", expand=True)

print(saperat)
result = saperat[0] + "-" + saperat[1]

print (result)
import re
numbers=result.apply(lambda x:re.findall(r"\d+",x))

def find_all_numbers(text):
    return re.findall(r"\d+", text)
print(result.apply(find_all_numbers))
print(numbers)

match = re.search(r"\d+", "Peter 25")
print("group():", match.group())
print("start():", match.start())
print("end():", match.end())
print("span():", match.span())

pattern = re.compile(r"\d+")

numbers = pattern.findall("Peter 25")

print(numbers)