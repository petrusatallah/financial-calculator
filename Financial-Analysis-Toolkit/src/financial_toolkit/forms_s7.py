"""Human-labelled form definitions and parsing shared by Streamlit and Tkinter."""
from __future__ import annotations
import csv
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
import io

from .validation import InputError,parse_number,parse_positive_integer
from .bond_workflows_s6 import DEFAULTS as BOND_DEFAULTS,DISCOUNT_TEXT,PROJECTION_TEXT,EXERCISE_TEXT,request_from_fields
from .data_workflows_s5 import manual_rows


@dataclass(frozen=True)
class Field:
    key:str
    label:str
    default:object=''
    kind:str='text'
    choices:tuple=()
    advanced:bool=False


def F(key,label,default='',kind='text',choices=(),advanced=False):return Field(key,label,default,kind,tuple(choices),advanced)
CCY=F('currency','Currency code','USD')
YEARS=F('years','Years to maturity','3')
FREQ=F('frequency','Payments/coupons per year','1')
DATE=F('valuation_date','Valuation date (YYYY-MM-DD)','2026-10-20')
FLOW=F('flows','Signed cash flows: time or date, amount','time,amount\n0,-100\n1,60\n2,60','table')
PROJECT=[CCY,FREQ,DATE,F('dated','Use actual dates',False,'bool',advanced=True),FLOW,
 F('discount','Annual effective discount rate (%)','10'),F('finance','Finance rate (%) — blank uses discount',''),
 F('reinvest','Reinvestment rate (%) — blank uses discount','')]
ASSETS=F('assets','Assets: id, kind (returns/price/total/log), adjustment, weight',
 'id,kind,adjustment,weight\nA,returns,manual,0.5\nB,returns,manual,0.5','table')
OBS=F('observations','Asset observations: id, date, decimal return or price, distribution',
 'id,date,value,distribution\nA,2021-01-01,0.1,\nA,2022-01-01,0.2,\nA,2023-01-01,0.3,\nB,2021-01-01,0.3,\nB,2022-01-01,0.2,\nB,2023-01-01,0.1,','table')
PORT=[CCY,F('frequency','Observation frequency','yearly','choice',('daily','weekly','monthly','quarterly','yearly')),ASSETS,OBS,
 F('cash_weight','Cash weight (decimal)','0'),F('cash_yield','Annual effective cash yield (%)',''),
 F('funding','Annual effective borrowing rate (%)','',advanced=True),F('risk_free','Annual effective risk-free rate (%)','2'),
 F('expected','Optional expected simple returns: id, decimal return','id,return\n','table',advanced=True),
 F('benchmark','Optional benchmark: date, decimal return','date,return\n','table',advanced=True),
 F('market_expected','Expected annual effective market return (%)','',advanced=True)]
BASIC_BOND=[CCY,F('face','Face amount','100'),F('coupon','Annual coupon (%)','5'),YEARS,FREQ,
 F('redemption','Maturity redemption','100'),F('yield','Nominal annual yield (%) — blank if price supplied','4'),
 F('price','Observed full price — blank if yield supplied',''),
 F('scenarios','Yield scenarios: label, decimal nominal annual yield','label,yield\nHigher,0.05','table')]
MODEL_BOND=[CCY,F('face','Face amount','100'),F('coupon','Annual coupon (%)','5'),YEARS,FREQ,DATE,
 F('redemption','Maturity redemption','100'),F('price','Observed full price (optional)',''),
 F('curve_id','Discount curve identifier','worked-discount'),F('curve_source','Discount curve source','User supplied discount factors'),
 F('as_of','Curve as-of with timezone','2026-10-20T00:00:00+00:00'),F('discount_curve','Discount factors: time in years, discount factor',DISCOUNT_TEXT,'table')]

WORKFLOWS={
 'rate_conversion':('Time Value of Money','Rate conversions',[
     F('direction','Conversion direction','nominal_to_effective','choice',('nominal_to_effective','effective_to_nominal')),
     F('rate','Annual rate (%)','12'),F('payment_frequency','Payments per year','12'),
     F('compounding_frequency','Compounding periods per year','12')]),
 'tvm_regular':('Time Value of Money','Regular payments',[
     CCY,F('target','Solve for','fv','choice',('pv','fv','pmt','rate','periods','auto')),
     F('pv','Signed present value','-100'),F('fv','Signed future value (blank unknown)',''),F('pmt','Signed payment','0'),
     F('periods','Number of payment periods','2'),F('annual_rate','Nominal annual rate (%)','10'),
     F('payment_frequency','Payments per year','1'),F('compounding_frequency','Compounding periods per year','1',advanced=True),
     F('timing','Payment timing','end','choice',('end','beginning'))]),
 'tvm_schedule':('Time Value of Money','Custom / dated / growing schedules',[
     CCY,DATE,FLOW,F('dated','Use actual dates',False,'bool',advanced=True),F('annual_rate','Nominal annual rate (%)','10'),
     F('payment_frequency','Payments per year','1'),F('compounding_frequency','Compounding periods per year','1',advanced=True),
     F('growth','Per-payment growth rate (%) — blank for explicit schedule','',advanced=True)]),
 'bond_regular':('Bond Analytics','Fixed / zero-coupon',BASIC_BOND),
 'bond_floating':('Bond Analytics','Floating-rate',MODEL_BOND+[
     F('projection_id','Projection curve identifier','worked-projection'),F('projection_source','Projection source','User supplied projection factors'),
     F('projection_curve','Projection discount factors',PROJECTION_TEXT,'table'),F('index','Reset index','User specified index'),
     F('tenor','Index tenor','1 year'),F('spread','Annual spread (%)','1'),F('floor','Coupon floor (%) — optional',''),F('cap','Coupon cap (%) — optional',''),
     F('fixing','Observed first-period fixing (%)','3'),F('fixing_source','Fixing source','User supplied observed fixing'),
     F('fixing_as_of','Fixing as-of with timezone','2026-10-20T00:00:00+00:00')]),
 'bond_option':('Bond Analytics','Callable / putable',MODEL_BOND+[
     F('volatility','Annual absolute rate volatility (%)','1'),F('volatility_source','Volatility source/assumption','User assumed constant volatility'),
     F('substeps','Substeps per coupon period','1'),F('mc','Run Monte Carlo cross-check',True,'bool'),
     F('seed','Seed — clear for new automatic seed','20261020'),F('training','Training paths','2000'),F('evaluation','Evaluation paths per batch','2000'),
     F('exercises','Exercise schedule: coupon period, call redemption, put redemption, priority',EXERCISE_TEXT,'table'),
     F('yield_scenarios','Fixed-redemption scenarios: label, decimal yield, period, redemption','label,yield,period,redemption\n','table')]),
 'project':('Investment Appraisal','Project appraisal',PROJECT),
 'project_comparison':('Investment Appraisal','Compare projects',PROJECT+[
     F('projects','Projects: name, time/date, signed amount, rates (%), currency/date/frequency and dated flag',
       'name,time,amount,discount,currency,valuation_date,frequency,dated,finance,reinvest\nA,0,-100,10,USD,2026-10-20,1,false,,\nA,1,60,10,USD,2026-10-20,1,false,,\nA,2,60,10,USD,2026-10-20,1,false,,\nB,0,-100,10,USD,2026-10-20,1,false,,\nB,1,70,10,USD,2026-10-20,1,false,,\nB,2,60,10,USD,2026-10-20,1,false,,','table'),
     F('repeatable','Unequal-life projects are repeatable',False,'bool',advanced=True)]),
 'sensitivity':('Investment Appraisal','Sensitivity',PROJECT+[
     F('driver_x','First driver','annual_discount_rate','choice',('annual_discount_rate','annual_finance_rate','annual_reinvestment_rate','future_flow_multiplier','cash_flow:0','cash_flow:1','cash_flow:2','cash_flow')),
     F('flow_x','First cash-flow row index (when specific cash flow selected)','1'),
     F('values_x','First driver values (decimal rates / multipliers / signed money)','0.05,0.1,0.15'),
     F('driver_y','Second driver — optional','None','choice',('None','annual_discount_rate','annual_finance_rate','annual_reinvestment_rate','future_flow_multiplier','cash_flow:0','cash_flow:1','cash_flow:2','cash_flow'),advanced=True),
     F('flow_y','Second cash-flow row index','1',advanced=True),
     F('values_y','Second driver values','',advanced=True)]),
 'scenarios':('Investment Appraisal','Scenarios',PROJECT+[
     F('cases','Joint scenario changes: name, probability (optional), driver, value (decimal rates)','name,probability,driver,value\nBase,,annual_discount_rate,0.1\nDownside,,future_flow_multiplier,0.8','table'),
     F('exclusive','Scenarios are mutually exclusive and exhaustive',False,'bool')]),
 'portfolio':('Portfolio Analytics and Optimization','Portfolio analytics',PORT),
 'portfolio_comparison':('Portfolio Analytics and Optimization','Compare allocations',PORT+[
     F('allocations','Allocations: name, asset id (CASH for cash), decimal weight','name,id,weight\nBalanced,A,0.5\nBalanced,B,0.5\nTilt,A,0.7\nTilt,B,0.3','table')]),
 'optimization':('Portfolio Analytics and Optimization','Optimization',PORT+[
     F('objective','Objective','minimum_variance','choice',('minimum_variance','maximum_estimated_sharpe','target_return_minimum_variance')),
     F('target','Target simple return floor per observation (decimal)','0.15'),F('allow_cash','Allow cash',False,'bool'),
     F('shorts','Allow short positions',False,'bool',advanced=True),F('bounds','Per-asset bounds: id, lower, upper','id,lower,upper\nA,0,1\nB,0,1','table',advanced=True),
     F('gross','Gross risky exposure cap','1',advanced=True),F('net_min','Minimum net risky exposure','1',advanced=True),F('net_max','Maximum net risky exposure','1',advanced=True)]),
 'market_data':('Market Data','Manual / offline observations',[
     CCY,F('instrument','Instrument identifier','AAPL'),F('asset_class','Asset class','stock','choice',('stock','etf','fx','yield','commodity','bond','index','crypto')),
     F('frequency','Observation frequency','daily','choice',('daily','weekly','monthly')),
     F('unit','Observation unit','USD per share'),F('adjustment','Adjustment','unadjusted','choice',('unadjusted','split_and_dividend_adjusted_close','raw_total_return')),
     F('source','Source reference','User manual observations'),F('observations','Observations: date, value, distribution, split_factor',
       'date,value,distribution,split_factor\n2026-10-12,100,0,1\n2026-10-13,110,0,1\n2026-10-14,99,0,1','table')]),
 'live_data':('Market Data','Retrieve latest available',[
     F('provider','Provider','ecb','choice',('ecb','treasury','world_bank','tiingo')),
     F('instrument','Instrument identifier','EURUSD'),F('asset_class','Asset class','fx','choice',('fx','yield','commodity','stock','etf')),
     F('frequency','Frequency','daily','choice',('daily','weekly','monthly')),F('start','Start date','2026-10-01'),F('end','End date','2026-10-19')]),
 'fx_conversion':('Market Data','FX conversion',[
     F('base_currency','Base currency','EUR'),F('foreign_currency','Foreign currency','USD'),
     F('price_rows','Manual asset prices: date, value, distribution, split_factor','date,value,distribution,split_factor\n2026-10-12,100,0,1\n2026-10-13,110,0,1','table'),
     F('fx_rows','FX rates (base currency per foreign unit): date, value, distribution, split_factor','date,value,distribution,split_factor\n2026-10-12,0.9,,\n2026-10-13,0.91,,','table')])}


def defaults(kind):return {f.key:f.default for f in WORKFLOWS[kind][2]}


# The two simple UI panels share these input contracts. Existing S7 forms stay
# available to reports and historical regression tests.
SIMPLE_TVM_OPTIONS={
    'Future Value (FV)':'fv','Present Value (PV)':'pv','Payment (PMT)':'pmt',
    'Interest Rate':'rate','Number of Periods':'periods'}
SIMPLE_APPRAISAL_OPTIONS={'NPV — Net Present Value':'npv',
                          'IRR — Internal Rate of Return':'irr'}
SIMPLE_BOND_OPTIONS={
    'fixed':{'Bond Price':'price','Face Value':'face','Coupon Rate':'coupon',
             'Yield to Maturity':'yield','Years to Maturity':'years'},
    'zero':{'Bond Price':'price','Face Value':'face',
            'Yield to Maturity':'yield','Years to Maturity':'years'}}
SIMPLE_TVM_EXAMPLE={'pv':'-100','fv':'121','pmt':'0','annual_rate':'10',
                    'years':'2','payment_frequency':'1'}
SIMPLE_PAYMENT_FREQUENCIES={'Annually (1)':'1','Semiannually (2)':'2',
                            'Quarterly (4)':'4','Monthly (12)':'12'}
SIMPLE_BOND_EXAMPLE={
    'fixed':{'face':'100','coupon_rate':'5','annual_yield':'4','years':'2',
             'frequency':'1','price':'101.8860946745562'},
    'zero':{'face':'100','annual_yield':'4','years':'2',
            'price':'92.4556213017751'}}


def simple_tvm_request(target, values, profile='Standard'):
    if target not in SIMPLE_TVM_OPTIONS.values():
        raise InputError('Choose a value to solve for.')
    frequency=str(values.get('payment_frequency','1'))
    if frequency not in SIMPLE_PAYMENT_FREQUENCIES.values():
        raise InputError('Choose Annually, Semiannually, Quarterly or Monthly payment frequency.')
    raw=defaults('tvm_regular')
    raw.update(values)
    raw.update(target=target,currency='USD',timing='end',
               compounding_frequency=frequency)
    if target!='periods':
        try:years=Decimal(str(values.get('years','')).strip())
        except (InvalidOperation,ValueError) as exc:
            raise InputError('Years to maturity must be a positive number.') from exc
        if not years.is_finite() or years<=0:
            raise InputError('Years to maturity must be a positive number.')
        periods=years*int(frequency)
        if periods!=periods.to_integral_value():
            raise InputError('Years to maturity and payment frequency must give a whole number of payment periods.')
        raw['periods']=str(int(periods))
    raw['annual_rate' if target=='rate' else target]=''
    return build('tvm_regular',raw,profile,'Standard')


def simple_appraisal_result(kind, cash_flows, rate_percent=None):
    """Present the existing regular-period NPV and IRR service calculations."""
    from .service import calculate_npv,calculate_irr

    if kind not in ('npv','irr'):
        raise InputError('Choose NPV or IRR.')
    if len(cash_flows)<2:
        raise InputError('Add at least one cash-flow period after Cash Flow 0.')
    result=(calculate_npv(rate_percent,cash_flows) if kind=='npv' else
            calculate_irr(cash_flows))
    if not result.ok:return result,None
    flows=[parse_number(flow,f'Cash Flow {index}') for index,flow in enumerate(cash_flows)]
    def terms(rate_label):
        return ' + '.join(f'{flow:g}' if index==0 else
                        f'({flow:g})/(1+{rate_label})^{index}'
                        for index,flow in enumerate(flows))
    if kind=='npv':
        rate=parse_number(rate_percent,'Discount rate (%)')/100
        discounted=[flow/(1+rate)**index for index,flow in enumerate(flows)]
        steps=[f'Period {index}: {flow:g} / (1 + {rate:g})^{index} = {value:,.6f}'
               for index,(flow,value) in enumerate(zip(flows,discounted))]
        interpretation=('Positive NPV: cash flows exceed the value required by this discount rate.'
                        if result.value>0 else
                        'Negative NPV: cash flows fall short at this discount rate.'
                        if result.value<0 else
                        'Zero NPV: cash flows exactly meet this discount rate.')
        return result,{'formula':'NPV = C0 + Σ Ct / (1 + r)^t, with r per cash-flow period.',
                       'substitution':f'NPV = {terms(format(rate,"g"))}',
                       'steps':steps,'interpretation':interpretation}
    interpretation=('More than one admissible IRR exists; no single rate is chosen.'
                    if len(result.value)>1 else
                    'This rate makes the present value of the signed cash flows equal zero.')
    return result,{'formula':'0 = C0 + Σ Ct / (1 + IRR)^t, with IRR per cash-flow period.',
                   'substitution':f'0 = {terms("IRR")}',
                   'steps':[], 'interpretation':interpretation}


def simple_bond_request(bond_type,target,values,profile='Standard'):
    if bond_type not in SIMPLE_BOND_OPTIONS or target not in SIMPLE_BOND_OPTIONS[bond_type].values():
        raise InputError('Choose a supported bond value to solve.')
    def number(key,label):
        if target==key:return None
        return parse_number(values.get(key,''),label)
    return 'bond_simple',dict(
        bond_type=bond_type,target=target,face=number('face','Face value'),
        coupon_rate=0.0 if bond_type=='zero' else (
            None if target=='coupon' else number('coupon_rate','Coupon rate (%)')/100),
        annual_yield=None if target=='yield' else number('annual_yield','Yield to maturity (%)')/100,
        years=number('years','Years to maturity'),
        frequency=1 if bond_type=='zero' else parse_positive_integer(values.get('frequency',''),
                  'Coupon payment frequency'),price=number('price','Bond price'),mode=profile)


def rows(text,columns):
    reader=csv.DictReader(io.StringIO(text.strip()))
    if reader.fieldnames!=columns:raise InputError('Required columns: '+','.join(columns))
    out=[]
    for i,row in enumerate(reader,2):
        if len(out)>20000 or None in row or any(v is None for v in row.values()):raise InputError(f'Table row{i}: malformed/excessive data.')
        out.append(row)
    return out


def build(kind,v,profile='Standard',financial='Standard'):
    def num(key,optional=False):
        x=v[key]
        if optional and (x is None or isinstance(x,str) and not x.strip()):return None
        return parse_number(x,key)
    def rate(key,optional=False):
        x=num(key,optional);return None if x is None else float(Decimal(str(x))/100)
    def flow_index(key):
        value=num(key)
        if value<0 or not value.is_integer():raise InputError('Cash-flow row index must be a nonnegative integer.')
        return str(int(value))
    def flows(text):
        return [[r['time'] if v.get('dated') else parse_number(r['time'],'Time'),parse_number(r['amount'],'Signed amount')] for r in rows(text,['time','amount'])]
    common={'mode':profile,'financial_mode':financial}
    def project():
        return dict(cash_flows=flows(v['flows']),annual_discount_rate=rate('discount'),currency=v['currency'],
            frequency=num('frequency'),dated=bool(v['dated']),valuation_date=v['valuation_date'],
            annual_finance_rate=rate('finance',True),annual_reinvestment_rate=rate('reinvest',True))
    def portfolio():
        assets=[];weights={};data=rows(v['observations'],['id','date','value','distribution'])
        for item in rows(v['assets'],['id','kind','adjustment','weight']):
            identity=item['id']
            if identity in weights:raise InputError('Duplicate asset ID.')
            weights[identity]=parse_number(item['weight'],'Weight')
            observations=[]
            for row in data:
                if row['id']!=identity:continue
                obs=[row['date'],parse_number(row['value'],'Observation')]
                if item['kind']=='total':obs.append(parse_number(row['distribution'],'Distribution'))
                observations.append(obs)
            assets.append(dict(id=identity,kind=item['kind'],adjustment=item['adjustment'],currency=v['currency'],frequency=v['frequency'],observations=observations))
        if set(weights)!={r['id'] for r in data}:raise InputError('Each observation must map to a declared asset.')
        expected={r['id']:parse_number(r['return'],'Expected return') for r in rows(v['expected'],['id','return'])} or None
        benchrows=rows(v['benchmark'],['date','return'])
        benchmark=dict(id='BENCHMARK',kind='returns',adjustment='manual benchmark',currency=v['currency'],frequency=v['frequency'],observations=[[r['date'],parse_number(r['return'],'Benchmark return')] for r in benchrows]) if benchrows else None
        return dict(assets=assets,weights=weights,currency=v['currency'],frequency=v['frequency'],cash_weight=num('cash_weight'),
            cash_annual_yield=rate('cash_yield',True),funding_annual_rate=rate('funding',True),risk_free_annual_rate=rate('risk_free',True),
            expected_returns=expected,benchmark=benchmark,market_expected_annual_return=rate('market_expected',True))
    if kind=='rate_conversion':args=dict(rate=rate('rate'),direction=v['direction'],payment_frequency=num('payment_frequency'),compounding_frequency=num('compounding_frequency'))
    elif kind=='tvm_regular':
        args={k:num(k,True) for k in ('pv','fv','pmt','periods')}
        args.update(target=v['target'],annual_rate=rate('annual_rate',True),payment_frequency=num('payment_frequency'),
            compounding_frequency=num('compounding_frequency') if financial=='Advanced' else num('payment_frequency'),timing=v['timing'],currency=v['currency'])
    elif kind=='tvm_schedule':args=dict(cash_flows=flows(v['flows']),annual_rate=rate('annual_rate'),currency=v['currency'],
        payment_frequency=num('payment_frequency'),compounding_frequency=num('compounding_frequency') if financial=='Advanced' else num('payment_frequency'),
        dated=bool(v['dated']),valuation_date=v['valuation_date'],growth_rate=rate('growth',True))
    elif kind=='bond_regular':args=dict(face=num('face'),coupon_rate=rate('coupon'),years=num('years'),frequency=num('frequency'),
        redemption=num('redemption'),annual_yield=rate('yield',True),observed_price=num('price',True),currency=v['currency'],
        scenario_yields=[{'label':r['label'],'yield':parse_number(r['yield'],'Scenario yield')} for r in rows(v['scenarios'],['label','yield'])])
    elif kind in ('bond_floating','bond_option'):
        if financial!='Advanced':raise InputError('Select Advanced financial controls for floating and option models; the execution profile remains separate.')
        b=dict(BOND_DEFAULTS)
        names={'Face':'face','Coupon (%)':'coupon','Years':'years','Frequency':'frequency','Currency':'currency','Valuation date':'valuation_date',
            'Redemption':'redemption','Observed full price':'price','Discount curve ID':'curve_id','Discount source':'curve_source','Curve as-of':'as_of'}
        names.update({'Projection curve ID':'projection_id','Projection source':'projection_source','Index':'index','Tenor':'tenor','Spread (%)':'spread',
            'Floor (%)':'floor','Cap (%)':'cap','First fixing (%)':'fixing','Fixing source':'fixing_source','Fixing as-of':'fixing_as_of'} if kind=='bond_floating' else
            {'Volatility (%)':'volatility','Volatility source':'volatility_source','Substeps per coupon':'substeps','Seed':'seed','Training paths':'training','Evaluation paths per batch':'evaluation'})
        for label,key in names.items():b[label]=str(v[key])
        b['Kind']='Floating' if kind=='bond_floating' else 'Callable / putable';b['Mode']=profile;b['Monte Carlo']='Yes' if v.get('mc',True) else 'No'
        _,args=request_from_fields(b,v['discount_curve'],v.get('projection_curve',PROJECTION_TEXT),v.get('exercises',EXERCISE_TEXT),v.get('yield_scenarios','label,yield,period,redemption\n'))
    elif kind=='project':args=project()
    elif kind=='project_comparison':
        groups={}
        cols=['name','time','amount','discount','currency','valuation_date','frequency','dated','finance','reinvest']
        for r in rows(v['projects'],cols):groups.setdefault(r['name'],[]).append(r)
        projects=[]
        for name,rs in groups.items():
            if any(len({r[key] for r in rs})!=1 for key in cols if key not in {'name','time','amount'}):raise InputError('Project rows must agree on their financial conventions.')
            r=rs[0]
            if r['dated'].lower() not in {'true','false'}:raise InputError('Project dated flag must be true/false.')
            base=project();base.update(currency=r['currency'],valuation_date=r['valuation_date'],frequency=parse_number(r['frequency'],'Project frequency'),dated=r['dated'].lower()=='true')
            base['cash_flows']=[[r['time'] if base['dated'] else parse_number(r['time'],'Time'),parse_number(r['amount'],'Amount')] for r in rs]
            base['annual_discount_rate']=float(Decimal(rs[0]['discount'])/100)
            for key,dest in [('finance','annual_finance_rate'),('reinvest','annual_reinvestment_rate')]:
                base[dest]=float(Decimal(rs[0][key])/100) if rs[0][key].strip() else None
            projects.append({'name':name,'inputs':base})
        args=dict(projects=projects,repeatable=bool(v['repeatable']))
    elif kind=='sensitivity':args=dict(base=project(),driver_x='cash_flow:'+flow_index('flow_x') if v['driver_x']=='cash_flow' else v['driver_x'],values_x=[parse_number(x,'Driver value') for x in v['values_x'].split(',')],
        driver_y=None if v['driver_y']=='None' else 'cash_flow:'+flow_index('flow_y') if v['driver_y']=='cash_flow' else v['driver_y'],values_y=None if v['driver_y']=='None' else [parse_number(x,'Driver value') for x in v['values_y'].split(',')])
    elif kind=='scenarios':
        cases={}
        for r in rows(v['cases'],['name','probability','driver','value']):
            case=cases.setdefault(r['name'],{'name':r['name'],'overrides':{}})
            if r['driver'] in case['overrides']:raise InputError('Duplicate scenario driver.')
            case['overrides'][r['driver']]=parse_number(r['value'],'Scenario value')
            if r['probability'].strip():
                p=parse_number(r['probability'],'Probability')
                if 'probability' in case and case['probability']!=p:raise InputError('Conflicting scenario probability.')
                case['probability']=p
        args=dict(base=project(),cases=list(cases.values()),exclusive_exhaustive=bool(v['exclusive']))
    elif kind in ('portfolio','portfolio_comparison','optimization'):
        base=portfolio()
        if kind=='portfolio':args=base
        elif kind=='portfolio_comparison':
            groups={};seen=set()
            for r in rows(v['allocations'],['name','id','weight']):
                marker=(r['name'],r['id'])
                if marker in seen:raise InputError('Duplicate allocation asset/cash row.')
                seen.add(marker)
                alloc=groups.setdefault(r['name'],{'name':r['name'],'weights':{},'cash_weight':0})
                if r['id']=='CASH':
                    alloc['cash_weight']=parse_number(r['weight'],'Cash weight')
                else:
                    if r['id'] in alloc['weights']:raise InputError('Duplicate allocation asset.')
                    alloc['weights'][r['id']]=parse_number(r['weight'],'Weight')
            args={k:base[k] for k in ('assets','currency','frequency','cash_annual_yield','funding_annual_rate','risk_free_annual_rate')}
            args['allocations']=list(groups.values())
        else:
            opt=dict(objective=v['objective'],target_return=num('target') if v['objective']=='target_return_minimum_variance' else None,allow_cash=bool(v['allow_cash']),
                cash_annual_yield=base['cash_annual_yield'],funding_annual_rate=base['funding_annual_rate'],risk_free_annual_rate=base['risk_free_annual_rate'])
            if financial=='Advanced':
                bounds=rows(v['bounds'],['id','lower','upper'])
                opt.update(lower_bounds={r['id']:parse_number(r['lower'],'Lower bound') for r in bounds},upper_bounds={r['id']:parse_number(r['upper'],'Upper bound') for r in bounds},
                    allow_short=bool(v['shorts']),gross_cap=num('gross'),net_min=num('net_min'),net_max=num('net_max'))
            args=dict(analysis_inputs=base,optimization_inputs=opt)
    elif kind=='market_data':
        obs=manual_rows(v['observations'],instrument=v['instrument'],asset_class=v['asset_class'],currency=v['currency'],unit=v['unit'],
            frequency=v['frequency'],adjustment=v['adjustment'],source=v['source'],mode=profile)
        args={'rows':obs}
    elif kind=='live_data':return kind,dict(provider=v['provider'],instrument=v['instrument'],asset_class=v['asset_class'],frequency=v['frequency'],start=v['start'],end=v['end'],mode=profile)
    elif kind=='fx_conversion':
        def manual(text,asset_class,ccy,unit):return manual_rows(text,instrument='ASSET' if asset_class=='stock' else v['base_currency']+v['foreign_currency'],asset_class=asset_class,currency=ccy,unit=unit,adjustment='unadjusted',source='User explicit FX conversion data',mode=profile)
        args=dict(prices=manual(v['price_rows'],'stock',v['foreign_currency'],v['foreign_currency']+' per share'),
            fx=manual(v['fx_rows'],'fx',v['base_currency'],v['base_currency']+' per '+v['foreign_currency']),base_currency=v['base_currency'])
    else:raise InputError('Unsupported workflow.')
    return kind,{**args,**common}
