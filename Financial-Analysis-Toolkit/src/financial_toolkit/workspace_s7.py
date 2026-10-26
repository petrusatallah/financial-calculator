"""S7 shared calculation dispatch, generation-safe jobs and presentation data.

REQ-UI-01/02, REPORT-01, PRIV-01/02. Numerical methods remain in S2–S6.
"""
from __future__ import annotations

import copy
from dataclasses import asdict
import hashlib
import inspect
import json
import queue
import threading
import time
import uuid

from .result import CalculationResult,Status
from .validation import InputError
from .tvm_s2 import solve_regular,schedule_value,periodic_rate,nominal_from_effective
from .bond_s2 import analyze_regular_bond, solve_simple_bond
from .bond_s6 import analyze_floating_bond,analyze_option_bond
from .appraisal_s3 import analyze_project
from .appraisal_workflows_s3 import compare_projects,sensitivity,scenarios
from .portfolio_s4 import analyze_portfolio
from .portfolio_workflows_s4 import compare_portfolios
from .optimization_s4 import optimize_portfolio
from .market_data_s5 import analyze_data,convert_fx

MODULES=('Time Value of Money','Cash Flow','Bond Analytics','Investment Appraisal',
         'Portfolio Analytics and Optimization')


def optimized_portfolio(*,analysis_inputs,optimization_inputs,mode='Standard',financial_mode=None,cancelled=lambda:False):
    if analysis_inputs.get('mode',mode)!=mode or optimization_inputs.get('mode',mode)!=mode:
        raise InputError('Analysis, optimization and execution profiles must agree.')
    financial=financial_mode or mode
    analysis=analyze_portfolio(**{**analysis_inputs,'mode':financial,'execution_profile':mode})
    if cancelled(): return CalculationResult(Status.INCOMPLETE,None,'portfolio weights',message='Cancelled.')
    if not analysis.ok:return analysis
    return optimize_portfolio(analysis,**{**optimization_inputs,'mode':financial,'execution_profile':mode},cancel=cancelled)


def fx_analysis(*,prices,fx,base_currency,mode='Standard'):
    rows=convert_fx(prices,fx,base_currency=base_currency,mode=mode)
    return CalculationResult(Status.VALID,None,'FX-converted observations',
        assumptions={'base_currency':base_currency,'quote':'base units per foreign unit; exact dates'},diagnostics={'converted_observations':rows})


def rate_conversion(*,rate,direction,payment_frequency,compounding_frequency,mode='Standard',financial_mode=None):
    financial=financial_mode or mode
    nominal=nominal_from_effective(rate,compounding_frequency) if direction=='effective_to_nominal' else rate
    if direction not in {'nominal_to_effective','effective_to_nominal'}:raise InputError('Unknown conversion direction.')
    periodic,effective=periodic_rate(nominal,payment_frequency,compounding_frequency,financial)
    return CalculationResult(Status.VALID,nominal if direction=='effective_to_nominal' else effective,'decimal annual rate',
        assumptions={'input_basis':'annual effective' if direction=='effective_to_nominal' else 'nominal annual',
            'output_basis':'nominal annual compounded at stated frequency' if direction=='effective_to_nominal' else 'annual effective'},
        diagnostics={'nominal_annual_rate':nominal,'effective_annual_rate':effective,'payment_period_rate':periodic,
            'formula':'EAR=(1+j/m)^m-1; payment-period rate=(1+EAR)^(1/p)-1; j=m*((1+EAR)^(1/m)-1)'})


FUNCTIONS={'tvm_regular':solve_regular,'tvm_schedule':schedule_value,'rate_conversion':rate_conversion,'bond_regular':analyze_regular_bond,
 'bond_simple':solve_simple_bond,
 'bond_floating':analyze_floating_bond,'bond_option':analyze_option_bond,'project':analyze_project,
 'project_comparison':compare_projects,'sensitivity':sensitivity,'scenarios':scenarios,
 'portfolio':analyze_portfolio,'portfolio_comparison':compare_portfolios,'optimization':optimized_portfolio,
 'market_data':analyze_data,'fx_conversion':fx_analysis}


def plain(value):
    """No callable/secrets/non-finite values enter a report or session request."""
    from .io_s2 import _plain
    obj=_plain(value)
    def check(x,depth=0):
        if depth>64:raise InputError('Input nesting exceeds the file contract.')
        if isinstance(x,dict):
            for k,v in x.items():
                if any(word in k.lower() for word in ('api_key','apikey','password','authorization','access_token')):
                    raise InputError('Credentials are not financial inputs and cannot be stored.')
                if k in {'period','periods','frequency','payment_frequency','compounding_frequency','training_paths','evaluation_paths','substeps'} and isinstance(v,float) and v.is_integer():
                    x[k]=int(v)
                check(v,depth+1)
        elif isinstance(x,list):
            for v in x:check(v,depth+1)
    check(obj)
    return obj


def fingerprint(kind,inputs):
    return hashlib.sha256(json.dumps([kind,plain(inputs)],sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def estimated_memory(obj):
    """Conservative session/buffer estimate, including cached explicit-download bytes."""
    if isinstance(obj,CalculationResult):return estimated_memory(asdict(obj))
    if isinstance(obj,bytes):return len(obj)
    if isinstance(obj,str):return 64+len(obj.encode('utf-8'))*16
    if isinstance(obj,dict):return 128+sum(estimated_memory(k)+estimated_memory(v) for k,v in obj.items())
    if isinstance(obj,(list,tuple)):return 64+sum(estimated_memory(v) for v in obj)
    return 32


def execute(kind,inputs,cancelled=lambda:False):
    started=time.monotonic()
    try:
        if kind not in FUNCTIONS:raise InputError('Unsupported calculation type.')
        args=plain(inputs); mode=args.get('mode','Standard')
        financial=args.pop('financial_mode',mode)
        if financial not in ('Standard','Advanced'):raise InputError('Unknown financial controls mode.')
        if kind in {'tvm_regular','tvm_schedule','portfolio','portfolio_comparison'}:
            args.update(mode=financial,execution_profile=mode)
        elif kind in {'optimization','rate_conversion'}:args['financial_mode']=financial
        if mode not in ('Standard','Advanced'):raise InputError('Choose Standard or Advanced execution profile.')
        seconds=10 if mode=='Standard' else 30
        if cancelled():return CalculationResult(Status.INCOMPLETE,None,'analysis',message='Cancelled.')
        # Per-operation parsing estimate plus conservative calculation buffer allowance.
        size=len(json.dumps(args,ensure_ascii=False,allow_nan=False).encode())
        if size*16>(256 if mode=='Standard' else 512)*1024**2:
            return CalculationResult(Status.INCOMPLETE,None,'analysis',message='Estimated request memory exceeds the profile limit.')
        if kind=='bond_option' and args.get('monte_carlo',True):
            from .monte_carlo_s6 import parse_seed
            args['seed']=parse_seed(args.get('seed'))
        fn=FUNCTIONS[kind]
        if 'cancelled' in inspect.signature(fn).parameters:args['cancelled']=cancelled
        result=fn(**args)
        result_size=len(json.dumps(plain(asdict(result)),ensure_ascii=False).encode())
        if (size+result_size)*16>(256 if mode=='Standard' else 512)*1024**2:
            return CalculationResult(Status.INCOMPLETE,None,result.unit,message='Estimated calculation/report memory exceeds profile limit.')
        if cancelled() or time.monotonic()-started>seconds:
            return CalculationResult(Status.INCOMPLETE,None,result.unit,message='Cancelled or operation deadline exceeded; result discarded.')
        return result
    except MemoryError:
        return CalculationResult(Status.INCOMPLETE,None,'analysis',message='Memory allocation failed; operation incomplete.')
    except (InputError,ValueError,TypeError,OverflowError,RecursionError) as exc:
        return CalculationResult(Status.INVALID,None,'analysis',message=str(exc))


class Session:
    """One current result per workflow; no disk history or global user cache."""
    def __init__(self):
        self.current={};self.forms={};self.job=None;self.generation=0;self.phase='Ready'
        self.incoming=None;self.values={}

    def changed(self,key,signature):
        old=self.forms.get(key)
        self.forms[key]=signature
        if old is not None and old!=signature:
            self.current.pop(key,None)
            self.current.pop('export:'+key,None)
            if self.job and self.job['key'] in (key,'export:'+key):self.cancel()

    def cancel(self):
        self.generation+=1
        if self.job:self.job['stop'].set();self.phase='Cancellation requested; waiting for bounded work to stop'

    def clear(self,key):
        self.cancel();self.current.pop(key,None);self.current.pop('export:'+key,None);self.forms.pop(key,None)

    def start(self,key,kind,inputs,task=None):
        if self.job:raise InputError('Wait for the current bounded operation to finish.')
        self.current.pop(key,None);self.current.pop('export:'+key,None)
        self.generation+=1;generation=self.generation
        stop=threading.Event();done=queue.Queue(maxsize=1)
        request=copy.deepcopy(plain(inputs)); signature=fingerprint(kind,request)
        cap=(256 if request.get('mode','Standard')=='Standard' else 512)*1024**2
        if estimated_memory(list(self.current.values()))+estimated_memory(request)*2>cap:
            raise InputError('INCOMPLETE: estimated session/operation memory exceeds profile. Clear other current analyses or reduce inputs.')
        self.phase='Validating and calculating'
        def work():
            started=time.monotonic();seconds=10 if request.get('mode','Standard')=='Standard' else 30
            interrupted=lambda:stop.is_set() or time.monotonic()-started>seconds
            try:
                if task:
                    payload=task(interrupted)
                else:
                    result=execute(kind,request,interrupted)
                    if kind=='bond_option' and 'seed' in result.diagnostics.get('monte_carlo',{}):
                        request['seed']=result.diagnostics['monte_carlo']['seed']
                    payload={'kind':kind,'inputs':request,'result':result}
                if estimated_memory(list(self.current.values()))+estimated_memory(payload)*2>cap:
                    done.put((None,'INCOMPLETE: estimated result/report/session memory exceeds profile.'))
                elif interrupted():done.put((None,'INCOMPLETE: cancelled or whole-operation deadline exceeded.'))
                else:done.put((payload,None))
            except InputError as exc:
                done.put((None,str(exc)))
            except Exception:
                # Do not emit traceback/request/credentials to framework logs.
                done.put((None,'Operation failed validation or could not complete. Check the typed fields and file format.'))
        self.job={'key':key,'signature':signature,'generation':generation,'stop':stop,'done':done}
        threading.Thread(target=work,daemon=True).start()

    def poll(self):
        if not self.job:return False
        job=self.job
        try:payload,error=job['done'].get_nowait()
        except queue.Empty:return False
        self.job=None
        if job['stop'].is_set() or job['generation']!=self.generation:
            self.phase='INCOMPLETE: cancelled or inputs changed; result discarded';return True
        if error:self.phase=error if error.startswith('INCOMPLETE:') else 'INVALID: '+error;return True
        self.current[job['key']]=payload;self.phase=str(payload['result'].status)
        return True


def format_value(value,unit):
    if value is None:return 'Not defined'
    if isinstance(value,(list,tuple)):return ', '.join(format_value(x,unit) for x in value)
    if not isinstance(value,(float,int)) or isinstance(value,bool):return str(value)
    rate='rate' in unit.lower() or 'yield' in unit.lower() or 'return' in unit.lower()
    money=(len(unit)==3 and unit.isalpha() and unit.isupper()) or any(w in unit.lower() for w in ('currency','per stated face'))
    shown=value*100 if rate and 'percent' not in unit.lower() else value
    text=f'{shown:,.4f}%' if rate else f'{shown:,.2f}' if money else f'{shown:.6g}'
    if value and (round(shown,4 if rate else 2)==0 if rate or money else False):
        return f'{shown:.6g}'+('%' if rate else '')
    return text


FORMULAS={
 'rate_conversion':'EAR=(1+j/m)^m-1; equivalent periodic rate=(1+EAR)^(1/p)-1; inverse conversion uses the accepted S2 helper.',
 'tvm_regular':'Signed present/future cash flows and periodic payments use the approved nominal/effective rate and payment timing.',
 'tvm_schedule':'Value = sum of each signed cash flow discounted or accumulated at its explicit time.',
 'bond_regular':'Full price = sum of coupon and redemption cash flows discounted at the nominal annual yield / coupon frequency.',
 'bond_simple':'Full price = sum of periodic coupons and 100% face redemption discounted at the nominal annual yield / coupon frequency.',
 'bond_floating':'Coupon = face × accrual × clip(index fixing/forward + spread, floor, cap); price discounts coupons and redemption on the separate discount curve.',
 'bond_option':'Ho–Lee calibrated state prices; backward exercise after coupon. Monte Carlo freezes a separately trained current-state continuation policy.',
 'project':'NPV = sum of signed discounted cash flows. IRR, MIRR, recovery and PI follow approved applicability rules.',
 'project_comparison':'Compare NPV only on compatible currency/date/horizon/rate bases; unequal-life EAA requires explicit repeatability.',
 'sensitivity':'Recalculate the base project for every specified one- or two-way input change.',
 'scenarios':'Recalculate coherent joint changes; probability-weight only explicitly exhaustive, mutually exclusive cases.',
 'portfolio':'Weighted simple returns; aligned observations; sample covariance; declared frequency and annualization.',
 'portfolio_comparison':'Recalculate named allocations on the same validated observation set and aligned dates.',
 'optimization':'Optimize the selected objective subject to the declared constraints; certify residuals before success.',
 'market_data':'Validate source observations and declared adjustments; never substitute missing prices or bridge missing return periods.',
 'fx_conversion':'Convert using explicit FX direction and matching dates; never guess quote direction.'}


def presentation(kind,inputs,result):
    """Framework-neutral source arrays; no chart-side financial recalculation."""
    d=result.diagnostics; tables={};charts=[]
    for name in ('schedule','cash_flow_schedule','cash_flow_timeline','observations','scenarios','grid','projects','portfolios'):
        value=d.get(name)
        if isinstance(value,list) and value and isinstance(value[0],dict):tables[name]=value
    for name in ('risk','date_specific_yields','yield_scenarios','converted_observations'):
        if isinstance(d.get(name),list) and d[name]:tables[name]=d[name]
    metrics=[]
    for name,value in d.items():
        if name in {'elapsed_seconds','cumulative_generated_paths'}:continue
        if isinstance(value,(int,float)) or value is None:
            unit=(inputs.get('currency',result.unit) if name in {'npv','base_npv','expected_npv','curve_discounted_projected_price'} else
                  'decimal rate' if 'return' in name or 'irr' in name else 'statistic')
            metrics.append({'Metric':name.replace('_',' ').title(),'Value':format_value(value,unit),
                            'Unit':unit,'Status':'UNDEFINED' if value is None else 'VALID'})
        elif name in {'irr','mirr','payback','discounted_payback','profitability_index'}:
            unit='statistic';shown='Not defined'
            if name=='irr':
                unit='annual effective rate';shown=', '.join(format_value(root['annual_effective_rate'],'decimal rate') for root in value.get('roots',[])) or value.get('message','Not defined')
            elif name=='mirr':unit='annual effective rate';shown=format_value(value.get('annual_effective_rate'),'decimal rate')
            elif name in {'payback','discounted_payback'}:
                unit=value.get('unit','years/date');shown=f'First: {value.get("first")}; sustained: {value.get("sustained")}; later reversal: {value.get("reversal",False)}'
            else:shown=format_value(value.get('value'),'statistic')
            metrics.append({'Metric':name.replace('_',' ').title(),'Value':shown,'Unit':unit,'Status':value.get('status','See workings')})
    if metrics:tables={'Summary metrics':metrics,**tables}
    for name in ('schedule','cash_flow_schedule','cash_flow_timeline'):
        rows=d.get(name,[])
        if not rows or not isinstance(rows[0],dict):continue
        xkey=next((k for k in ('date','payment_years','years','time','period') if k in rows[0]),None)
        for ykey in ('balance_end','cash_flow','coupon','present_value','discounted','amount'):
            if xkey and ykey in rows[0] and all(isinstance(r.get(ykey),(int,float)) for r in rows):
                charts.append({'title':name.replace('_',' ').title()+': '+ykey.replace('_',' '),
                    'x_label':xkey,'y_label':inputs.get('currency',result.unit),
                    'x':[r[xkey] for r in rows],'series':{ykey:[r[ykey] for r in rows]}})
    if 'dates' in d and 'cumulative_path' in d:
        charts.append({'title':'Historical portfolio cumulative path','x_label':'date','y_label':'decimal cumulative return',
            'x':d['dates'],'series':{'portfolio':d['cumulative_path']}})
    if isinstance(d.get('return_series'),dict):
        for asset,values in d['return_series'].items():
            charts.append({'title':asset+' aligned simple returns','x_label':'date','y_label':'decimal return',
                'x':d['dates'],'series':{asset:values}})
    if isinstance(d.get('weights'),dict):
        weights={**d['weights'],'CASH':d.get('cash_weight',0.)}
        charts.append({'title':'Allocation weights','x_label':'asset','y_label':'decimal weight','kind':'bar',
            'x':list(weights),'series':{'weight':list(weights.values())}})
    if isinstance(d.get('correlation'),list):
        charts.append({'title':'Asset correlation','x_label':'asset','y_label':'correlation','kind':'heatmap',
            'x':d['assets'],'series':{a:row for a,row in zip(d['assets'],d['correlation'])}})
    if isinstance(d.get('portfolios'),list) and d.get('dates'):
        charts.append({'title':'Allocation historical performance','x_label':'date','y_label':'decimal cumulative return',
            'x':d['dates'],'series':{p['name']:p['cumulative_path'] for p in d['portfolios']}})
        charts.append({'title':'Allocation return and risk','x_label':'volatility','y_label':'expected simple return','kind':'scatter',
            'x':[p['volatility'] for p in d['portfolios']],
            'series':{'expected return':[p['expected_return'] for p in d['portfolios']]}})
    if isinstance(d.get('observations'),list):
        groups={}
        for row in d['observations']:
            key=row['provider']+'/'+row['instrument'];groups.setdefault(key,[]).append(row)
        for key,rows in groups.items():
            charts.append({'title':key+' — '+rows[0]['adjustment'],'x_label':'source date','y_label':rows[0]['unit'],
                'x':[r['date'] for r in rows],'series':{key:[r['value'] for r in rows]}})
    if d.get('tree_grids'):
        for g in d['tree_grids']:
            tables[f'Calibration {g["steps"]} steps']=g['calibration']
    explanation=d.get('interpretation') or (
        'The selected value balances the signed starting amount, end-of-period payments and final amount. Negative values are cash paid out.'
        if kind=='tvm_regular' else
        'This is a conditional model estimate, not an observed market quote.' if kind in ('bond_option','bond_floating') else
        'Review assumptions, signs, units, applicability and warnings before comparing results.')
    formula=FORMULAS.get(kind,'')
    if result.ok and kind=='tvm_regular':
        solved={name:result.value if inputs.get('target')==name else inputs.get(name)
                for name in ('pv','fv','pmt')}
        roots=d.get('periodic_roots')
        periodic=d.get('periodic_rate',roots[0] if roots and len(roots)==1 else None)
        count=len(d.get('schedule',[])) or inputs.get('periods')
        if periodic is not None and count is not None:
            formula=(f"Signed balance: {solved['pv']:g} × (1 + {periodic:.8g})^{count} + "
                     f"{solved['pmt']:g} × A_{count}({periodic:.8g}) + {solved['fv']:g} = 0; "
                     "A_N(r) = ((1+r)^N−1)/r, or N when r=0.")
    elif result.ok and kind=='bond_simple':
        rows=d['schedule'];face=d['solved_face'];coupon=d['coupon_per_period']
        yield_rate=d['solved_nominal_yield'];frequency=result.assumptions['frequency']
        formula=(f"Price = Σ from t=1 to {len(rows)} of {coupon:.8g}/"
                 f"(1 + {yield_rate:.8g}/{frequency})^t + {face:.8g}/"
                 f"(1 + {yield_rate:.8g}/{frequency})^{len(rows)} = "
                 f"{d['theoretical_price']:.8g}.")
    return {'summary':format_value(result.value,result.unit),'unit':result.unit,'status':str(result.status),
        'interpretation':explanation,'formula':formula,'tables':tables,'charts':charts,
        'warnings':list(result.warnings),'assumptions':result.assumptions,'diagnostics':d,'inputs':inputs}


def chart_window(chart,mode,start=0,count=None,series=None):
    limit=10000 if mode=='Standard' else 50000
    keys=list(chart['series']) if series is None else list(series)
    if any(k not in chart['series'] for k in keys):raise InputError('Unknown chart series.')
    count=len(chart['x'])-start if count is None else count
    if start<0 or count<0 or start+count>len(chart['x']):raise InputError('Invalid chart window.')
    if len(keys)*count>limit:raise InputError('Select fewer series or a smaller date window; no points were dropped.')
    if any(len(chart['series'][k])!=len(chart['x']) for k in keys):raise InputError('Chart source dimensions do not match.')
    return {**chart,'x':chart['x'][start:start+count],
        'series':{k:chart['series'][k][start:start+count] for k in keys}}
