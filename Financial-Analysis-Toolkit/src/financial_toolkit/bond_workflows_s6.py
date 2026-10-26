"""Shared S6 form parsing for both interfaces; all financial work stays in engine."""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from .validation import InputError, parse_number
from .bond_s6 import analyze_floating_bond, analyze_option_bond

DEFAULTS = {
    'Kind':'Callable / putable', 'Mode':'Standard', 'Face':'100', 'Coupon (%)':'5',
    'Years':'3','Frequency':'1','Currency':'USD','Valuation date':'2026-10-20',
    'Redemption':'100','Observed full price':'','Volatility (%)':'1',
    'Volatility source':'User assumed constant annual absolute rate volatility',
    'Substeps per coupon':'1','Monte Carlo':'Yes','Seed':'20261020',
    'Training paths':'2000','Evaluation paths per batch':'2000',
    'Discount curve ID':'worked-discount','Discount source':'User supplied discount factors',
    'Projection curve ID':'worked-projection','Projection source':'User supplied projection factors',
    'Curve as-of':'2026-10-20T00:00:00+00:00','Index':'User specified index','Tenor':'1 year',
    'Spread (%)':'1','Floor (%)':'','Cap (%)':'','First fixing (%)':'3',
    'Fixing source':'User supplied observed index fixing','Fixing as-of':'2026-10-20T00:00:00+00:00',
}
DISCOUNT_TEXT='time,discount_factor\n0,1\n1,0.9615384615384616\n2,0.9245562130177514\n3,0.8889963586709148'
PROJECTION_TEXT='time,discount_factor\n0,1\n1,0.970873786407767\n2,0.9335324869305451\n3,0.8976273912793703'
EXERCISE_TEXT='period,call,put,priority\n1,100,,\n2,100,,'
SCENARIO_TEXT='label,yield,period,redemption\n'


def _rows(text,columns):
    reader=csv.DictReader(io.StringIO(text.strip()))
    if reader.fieldnames!=columns: raise InputError('Expected columns: '+','.join(columns))
    result=[]
    for row in reader:
        if None in row or any(v is None for v in row.values()): raise InputError('Malformed table row.')
        if len(result)>=10000: raise InputError('Table exceeds 10000 rows.')
        result.append(row)
    return result


def request_from_fields(fields,discount_text,projection_text,exercise_text,scenario_text=SCENARIO_TEXT):
    def number(name): return parse_number(fields[name],name)
    def optional(name): return None if not fields[name].strip() else number(name)
    def rate(name,optional_rate=False):
        value=optional(name) if optional_rate else number(name)
        return None if value is None else float(Decimal(str(value))/100)
    def curve(role,text):
        rows=_rows(text,['time','discount_factor'])
        return {'id':fields[role+' curve ID'],'source':fields[role+' source'],
            'currency':fields['Currency'],'valuation_date':fields['Valuation date'],
            'as_of':fields['Curve as-of'],'nodes':[{k:parse_number(v,k) for k,v in row.items()} for row in rows]}
    common={'face':number('Face'),'years':number('Years'),'frequency':number('Frequency'),
        'currency':fields['Currency'],'valuation_date':fields['Valuation date'],
        'redemption':number('Redemption'),'mode':fields['Mode'],
        'discount_curve':curve('Discount',discount_text)}
    if fields['Kind']=='Floating':
        common.update(spread=rate('Spread (%)'),projection_curve=curve('Projection',projection_text),
            index=fields['Index'],tenor=fields['Tenor'],floor=rate('Floor (%)',True),cap=rate('Cap (%)',True),
            fixings=[{'period':1,'rate':rate('First fixing (%)'),'source':fields['Fixing source'],'as_of':fields['Fixing as-of']}])
        return 'bond_floating',common
    if fields['Kind']!='Callable / putable': raise InputError('Choose Floating or Callable / putable.')
    exercises=[]
    for row in _rows(exercise_text,['period','call','put','priority']):
        exercises.append({'period':parse_number(row['period'],'Exercise period'),
            'call':None if not row['call'].strip() else parse_number(row['call'],'Call redemption'),
            'put':None if not row['put'].strip() else parse_number(row['put'],'Put redemption'),
            'priority':row['priority'].strip() or None})
    scenarios=[]
    for row in _rows(scenario_text,['label','yield','period','redemption']):
        scenarios.append({'label':row['label'],'yield':parse_number(row['yield'],'Decimal nominal annual yield'),
            'period':parse_number(row['period'],'Scenario horizon'),'redemption':parse_number(row['redemption'],'Scenario redemption')})
    common.update(coupon_rate=rate('Coupon (%)'),volatility=rate('Volatility (%)'),
        volatility_source=fields['Volatility source'],exercises=exercises,scenario_yields=scenarios,
        observed_price=optional('Observed full price'),substeps=number('Substeps per coupon'),
        monte_carlo=fields['Monte Carlo']=='Yes',seed=fields['Seed'].strip() or None,
        training_paths=number('Training paths'),evaluation_paths=number('Evaluation paths per batch'))
    return 'bond_option',common


def execute(kind,inputs,cancelled=lambda:False):
    fn=analyze_floating_bond if kind=='bond_floating' else analyze_option_bond if kind=='bond_option' else None
    if fn is None: raise InputError('Unknown bond workflow.')
    return fn(**inputs,cancelled=cancelled)


def summary(result):
    rows=[f'{result.status}: {result.message}']
    if result.ok: rows.append(f'Full model price: {result.value:.10g} {result.unit}')
    if 'monte_carlo' in result.diagnostics:
        mc=result.diagnostics['monte_carlo']; final=mc.get('final')
        if 'seed' in mc: rows.append(f'Seed: {mc["seed"]}')
        if final is not None: rows.extend([f'Monte Carlo price: {final["price"]:.10g}; standard error: {final["standard_error"]:.6g}',
            f'Approximate 95% interval: {final["confidence_interval_95"]}',
            'Interval excludes policy, discretization, parameter and model bias.'])
    if 'risk' in result.diagnostics:
        risk=result.diagnostics['risk'][-1]
        rows.extend([f'Effective duration: {risk["effective_duration_years"]:.8g} years',
            f'Effective convexity: {risk["effective_convexity_years_squared"]:.8g} years²'])
    rows.extend(result.warnings)
    return '\n'.join(rows)
