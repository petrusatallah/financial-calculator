import tkinter as tk



menu = {
    "1": "Future Value",
    "2": "Present Value",
    "3": "NPV",
    "4": "Bond Price",
    "5": "Exit"
}
print("TVM CALCULATOR")
print()

for key, value in menu.items():
    print(f"{key}. {value}")

choice = input("Choose an option: ")

# Present value
def Present_value(fv,rate,years,pmt):
    pv_fv = fv / (1 + rate) ** years
    pv_pmt = pmt * ((1 - (1 + rate) ** -years) / rate)

    pv = pv_fv + pv_pmt

    return pv
#Futuer value

def Future_value(pv,rate,years,pmt):
    Fv= (pv*(1+ rate )**years)+(pmt*((1+rate)**years-1)/rate)
    return Fv
# NPV
def NPV(rate, cashflows):
    npv = 0

    for year, cashflow in enumerate(cashflows):
        pv = cashflow / (1 + rate) ** year
        npv += pv

    return npv
# Bond price
def Bond_price(face_value, coupon_rate, ytm, years, frequency):
    coupon = face_value * coupon_rate / frequency
    periods = years * frequency
    periodic_ytm = ytm / frequency
    pv_coupons = coupon * (
        (1 - (1 + periodic_ytm) ** -periods)
        / periodic_ytm
        )
    pv_face_value = face_value / (1 + periodic_ytm) ** periods
    bond_price = pv_coupons + pv_face_value

    return bond_price





if choice == "1":
    print("Future Value")
    pv = float(input("Enter Present Value: "))
    rate = float(input("Enter Annual Interest Rate (%): "))
    rate = rate / 100
    years = int(input("Enter Number of Years: "))
    pmt=float(input("Enter PMT Value:"))
    result=Future_value(pv,rate,years,pmt)
    print(f"Future value =${result:.2f}")

elif choice == "2":
    print("Present Value ")
    fv= float(input("Enter Future Value:"))
    rate = float(input("Enter Annual Interest Rate (%): "))
    rate = rate / 100
    years = int(input("Enter Number of Years: "))
    pmt=float(input("Enter PMT Value:"))
    result = Present_value(fv, rate, years,pmt)
    print(f"Present Value = ${result:.2f}")

elif choice == "3":
    print("NPV")

    rate = float(input("Enter Required Return (%): "))
    rate = rate / 100

    number_of_cashflows = int(input("How many cash flows? "))

    cashflows = []
    for year in range(number_of_cashflows):
        cashflow = float(input(f"Enter cash flow for year {year}: "))
        cashflows.append(cashflow)
    result = NPV(rate, cashflows)
    print(f"NPV = ${result:.2f}")



elif choice == "4":
    print("Bond Price")

    face_value = float(input("Enter Face Value: "))

    coupon_rate = float(input("Enter Coupon Rate (%): "))
    coupon_rate = coupon_rate / 100

    ytm = float(input("Enter YTM (%): "))
    ytm = ytm / 100

    years = int(input("Enter Years to Maturity: "))

    frequency = int(input("Enter Coupon Frequency per Year: "))

    result = Bond_price(
        face_value,
        coupon_rate,
        ytm,
        years,
        frequency
    )

    print(f"Bond Price = ${result:.2f}")

elif choice == "5":
    print("Goodbye!")

else:
    print("Invalid option. Please choose 1-5.")







