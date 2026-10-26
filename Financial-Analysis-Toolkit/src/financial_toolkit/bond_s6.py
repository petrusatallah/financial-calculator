"""Approved S6 regular floating and Ho–Lee bond contracts.

REQ-BOND-02/03/04/05, REQ-MC-01/02/03. D04/D05/D06/D13 approved
in S6_Evidence/s6_decisions_approved.md; no pricing convention is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
import time
from typing import Callable

import numpy as np

from .bond_s2 import _periods, _schedule, _price, _ytm_for_schedule
from .result import CalculationResult, Status
from .validation import InputError, UnsupportedInput, parse_number, parse_currency, parse_positive_integer


class Incomplete(InputError):
    pass


@dataclass
class Budget:
    mode: str
    cancelled: Callable = lambda: False

    def __post_init__(self):
        if self.mode not in {'Standard', 'Advanced'}:
            raise InputError('Mode must be Standard or Advanced.')
        self.started = time.monotonic()
        self.seconds = 10 if self.mode == 'Standard' else 30
        self.memory = (256 if self.mode == 'Standard' else 512) * 1024**2
        self.steps = 64 if self.mode == 'Standard' else 256
        self.path_cap = 100000 if self.mode == 'Standard' else 500000
        self.paths = 0

    def check(self):
        if self.cancelled():
            raise Incomplete('Cancelled; no successful price is available.')
        if time.monotonic() - self.started > self.seconds:
            raise Incomplete('Execution exceeded the approved time limit.')

    def reserve(self, n, paths=0):
        self.check()
        if n > self.steps:
            raise UnsupportedInput('Base/refined grid exceeds the approved step limit.')
        # Conservative allowance for paths, discounts, regression and temporaries.
        estimate = 64 * (n + 1)**2 + paths * ((n + 1) * 48 + 1024)
        if estimate > self.memory:
            raise Incomplete('Estimated working memory exceeds the approved limit.')
        if self.paths + paths > self.path_cap:
            raise Incomplete('Cumulative generated paths exceed the approved limit.')
        self.paths += paths


def _day(raw, name):
    try:
        if not isinstance(raw, str) or len(raw) != 10:
            raise ValueError
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise InputError(f'{name} must be an ISO calendar date.') from exc


def _label(raw, name):
    if not isinstance(raw, str) or not raw.strip():
        raise InputError(f'{name} is required.')
    return raw.strip()


class Curve:
    """Explicit DF curve, log-linear interpolation and no extrapolation."""
    def __init__(self, raw, currency, valuation_date, horizon, name):
        if not isinstance(raw, dict):
            raise InputError(f'{name} must be an identified discount-factor curve.')
        required = {'id', 'currency', 'valuation_date', 'source', 'as_of', 'nodes'}
        if set(raw) != required:
            raise InputError(f'{name} requires exactly {sorted(required)}.')
        for field in ('id', 'source'):
            _label(raw[field], f'{name} {field}')
        try:
            stamp = datetime.fromisoformat(raw['as_of'])
            if stamp.utcoffset() is None:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise InputError(f'{name} as_of must include a timezone.') from exc
        if parse_currency(raw['currency']) != currency or raw['valuation_date'] != valuation_date:
            raise InputError(f'{name} currency/valuation date must match the contract.')
        _day(raw['valuation_date'], f'{name} valuation date')
        nodes = raw['nodes']
        if not isinstance(nodes, list) or not 2 <= len(nodes) <= 10000:
            raise InputError(f'{name} requires 2–10000 explicit time/DF nodes.')
        ts, dfs = [], []
        for node in nodes:
            if not isinstance(node, dict) or set(node) != {'time', 'discount_factor'}:
                raise InputError('Curve nodes must contain time and discount_factor only.')
            t = parse_number(node['time'], 'Curve time in years')
            df = parse_number(node['discount_factor'], 'Discount factor')
            if t < 0 or df <= 0 or ts and t <= ts[-1]:
                raise InputError('Curve times must increase strictly; discount factors must be positive.')
            ts.append(t); dfs.append(df)
        if ts[0] != 0 or dfs[0] != 1 or ts[-1] < horizon:
            raise InputError('Require DF(0)=1 and coverage through maturity; no extrapolation.')
        self.times = np.asarray(ts)
        self.logs = np.log(dfs)
        self.raw = raw

    def df(self, t, shift=0.):
        values = np.asarray(t)
        if np.any(values < 0) or np.any(values > self.times[-1] + 1e-12):
            raise InputError('Curve extrapolation is unsupported.')
        answer = np.exp(np.interp(values, self.times, self.logs) - shift * values)
        if not np.all(np.isfinite(answer)) or np.any(answer <= 0):
            raise UnsupportedInput('Discount factors exceed the supported numeric range.')
        return float(answer) if values.ndim == 0 else answer


def _failure(exc, diagnostics=None):
    status = Status.INCOMPLETE if isinstance(exc, (Incomplete,MemoryError)) else Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID
    return CalculationResult(status, None, 'bond analysis', message=str(exc) or 'Memory allocation failed; calculation incomplete.', diagnostics=diagnostics or {})


def analyze_floating_bond(*, face, years, frequency, spread, projection_curve,
                          discount_curve, valuation_date, index, tenor, currency,
                          fixings, floor=None, cap=None, redemption=None,
                          allow_same_curve=False, mode='Standard', cancelled=lambda: False):
    """Observed period-one reset; future regular resets use identified forwards."""
    try:
        budget = Budget(mode, cancelled)
        budget.check()
        n, f = _periods(years, frequency, mode)
        budget.reserve(n)
        ccy = parse_currency(currency)
        _day(valuation_date, 'Valuation date')
        _label(index, 'Reset index'); _label(tenor, 'Index tenor')
        F = parse_number(face, 'Face'); s = parse_number(spread, 'Spread')
        K = F if redemption is None else parse_number(redemption, 'Redemption')
        lo = None if floor is None else parse_number(floor, 'Floor')
        hi = None if cap is None else parse_number(cap, 'Cap')
        if F <= 0 or K <= 0 or lo is not None and hi is not None and lo > hi:
            raise InputError('Face/redemption must be positive; floor cannot exceed cap.')
        pc = Curve(projection_curve, ccy, valuation_date, n/f, 'Projection curve')
        dc = Curve(discount_curve, ccy, valuation_date, n/f, 'Discount curve')
        if not isinstance(allow_same_curve, bool):
            raise InputError('Same-curve selection must be explicit true/false.')
        if pc.raw == dc.raw and not allow_same_curve:
            raise InputError('Select allow_same_curve explicitly when using one curve for both roles.')
        if not isinstance(fixings, list):
            raise InputError('Fixings must be explicit identified reset records.')
        fixed = {}; fixing_records = {}
        for row in fixings:
            if not isinstance(row, dict) or set(row) != {'period', 'rate', 'source', 'as_of'}:
                raise InputError('Fixings require period, decimal rate, source and as_of.')
            p = parse_positive_integer(row['period'], 'Fixing period')
            if p != 1 or p in fixed:
                raise InputError('Only the valuation-date first-period fixing is already reset; no duplicate or future fixings.')
            _label(row['source'], 'Fixing source')
            try:
                stamp = datetime.fromisoformat(row['as_of'])
                if stamp.utcoffset() is None or stamp.date() > _day(valuation_date, 'Valuation date'):
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise InputError('Observed fixing needs a timezone and cannot be dated after valuation.') from exc
            fixed[p] = parse_number(row['rate'], 'Observed fixing')
            fixing_records[p] = row
        if 1 not in fixed:
            raise InputError('The valuation-date reset requires its observed first-period fixing.')
        rows = []
        for p in range(1, n+1):
            budget.check()
            reset, payment = (p-1)/f, p/f
            L = fixed[p] if p in fixed else (pc.df(reset)/pc.df(payment)-1)*f
            rate = L+s
            if lo is not None: rate = max(rate, lo)
            if hi is not None: rate = min(rate, hi)
            coupon = F/f*rate
            redemption_amount = K if p == n else 0.
            df = dc.df(payment)
            rows.append({'period':p, 'reset_years':reset, 'payment_years':payment,
                'accrual_fraction':1/f, 'index_rate':L, 'coupon_rate':rate,
                'coupon':coupon, 'redemption':redemption_amount, 'discount_factor':df,
                'present_value':(coupon+redemption_amount)*df,
                'coupon_kind':'contractual observed fixing' if p in fixed else 'projected',
                'fixing':fixing_records.get(p)})
        value = math.fsum(r['present_value'] for r in rows)
        if not math.isfinite(value): raise UnsupportedInput('Floating price is not finite.')
        budget.check()
        return CalculationResult(Status.VALID, value, f'{ccy} per stated face',
            warnings=('Future coupons are projections, not known contractual cash amounts.',),
            assumptions={'currency':ccy, 'valuation_date':valuation_date, 'index':index, 'tenor':tenor,
                'projection_curve':pc.raw, 'discount_curve':dc.raw, 'spread':s, 'floor':lo, 'cap':hi,
                'quote':'full price at coupon date; no accrual', 'rate_scale':'decimal',
                'curve_interpolation':'log-linear DF; no extrapolation', 'same_curve_selected':allow_same_curve},
            diagnostics={'schedule':rows, 'curve_discounted_projected_price':value,
                         'elapsed_seconds':time.monotonic()-budget.started})
    except (InputError, TypeError, ValueError, OverflowError, ZeroDivisionError, FloatingPointError,MemoryError) as exc:
        return _failure(exc)


def exercise_value(continuation, call, put, priority):
    """Ex-coupon, with approved contractual first-right precedence."""
    result = continuation
    if call is not None and put is not None:
        if priority == 'holder-first':
            return np.maximum(put, np.minimum(call, continuation))
        return np.minimum(call, np.maximum(put, continuation))
    if call is not None: result = np.minimum(result, call)
    if put is not None: result = np.maximum(result, put)
    return result


def exercise_actions(continuation, call, put, priority):
    actions = np.full(np.shape(continuation), 'continue', dtype='<U8')
    # Strict inequalities preserve continuation on ties.
    order = ('call', 'put') if priority == 'holder-first' else ('put', 'call')
    current = np.asarray(continuation).copy()
    for right in order:
        strike = call if right == 'call' else put
        if strike is not None:
            take = current > strike if right == 'call' else current < strike
            actions[take] = right
            current = np.minimum(current, strike) if right == 'call' else np.maximum(current, strike)
    return actions


def exercise_contract(raw, n, substeps):
    if not isinstance(raw, list): raise InputError('Exercise terms must be a list.')
    result = {}
    for term in raw:
        if not isinstance(term, dict) or not {'period','call','put','priority'} == set(term):
            raise InputError('Each exercise term requires period, call, put and priority.')
        p = parse_positive_integer(term['period'], 'Exercise period')
        if not 1 <= p < n or p*substeps in result:
            raise InputError('Exercise periods must be unique coupon dates strictly before maturity.')
        call = None if term['call'] is None else parse_number(term['call'], 'Call redemption')
        put = None if term['put'] is None else parse_number(term['put'], 'Put redemption')
        if call is None and put is None or call is not None and call <= 0 or put is not None and put <= 0:
            raise InputError('Require a positive call and/or put redemption.')
        priority = term['priority']
        if call is not None and put is not None and priority not in {'holder-first','issuer-first'}:
            raise InputError('Concurrent call/put requires contractual holder-first or issuer-first priority.')
        if not (priority is None or priority in {'holder-first','issuer-first'}):
            raise InputError('Invalid exercise priority.')
        result[p*substeps] = (call, put, priority)
    return result


def calibrate(curve, steps, dt, sigma, budget, shift=0.):
    budget.reserve(steps)
    targets = curve.df(np.arange(steps+1)*dt, shift)
    Q = np.ones(1); rates = []; rows = []
    for i in range(steps):
        budget.check()
        offset = (2*np.arange(i+1)-i)*sigma*math.sqrt(dt)
        # Log-sum-exp keeps calibration stable at admissible negative rates.
        log_terms = np.log(Q) - offset*dt
        peak = float(np.max(log_terms))
        log_total = peak + math.log(float(np.exp(log_terms-peak).sum()))
        alpha = (log_total-math.log(targets[i+1]))/dt
        r = alpha+offset
        discounted = Q*np.exp(-r*dt)
        fitted = float(discounted.sum())
        residual = fitted-targets[i+1]
        if not math.isfinite(fitted) or abs(residual) > 1e-10+1e-10*abs(targets[i+1]):
            raise Incomplete('Ho–Lee curve calibration failed its discount-factor tolerance.')
        nextQ = np.zeros(i+2)
        nextQ[:-1] += .5*discounted; nextQ[1:] += .5*discounted
        if np.any(nextQ <= 0) or not np.all(np.isfinite(r)):
            raise UnsupportedInput('Tree state prices/rates exceed supported numeric range.')
        rates.append(r)
        rows.append({'step':i, 'years':i*dt, 'alpha':alpha, 'target_df':float(targets[i+1]),
                     'fitted_df':fitted, 'residual':residual})
        Q = nextQ
    return {'rates':rates, 'calibration':rows, 'steps':steps, 'dt':dt}


def tree_price(tree, coupon, redemption, substeps, terms, budget, trace=False):
    N, dt = tree['steps'], tree['dt']
    values = np.full(N+1, redemption+coupon)
    log = []
    for i in range(N-1,-1,-1):
        budget.check()
        cont = .5*(values[:-1]+values[1:])*np.exp(-tree['rates'][i]*dt)
        call, put, priority = terms.get(i, (None,None,None))
        ex = exercise_value(cont, call, put, priority)
        if trace and i in terms:
            actions = exercise_actions(cont, call, put, priority)
            log.append({'step':i, 'years':i*dt, 'rates':tree['rates'][i].tolist(),
                'continuation_ex_coupon':cont.tolist(), 'exercise_value_ex_coupon':ex.tolist(),
                'actions':actions.tolist(), 'coupon':coupon, 'call':call,'put':put,'priority':priority})
        values = ex + (coupon if i > 0 and i % substeps == 0 else 0)
    return float(values[0]), sorted(log, key=lambda row:row['step'])


def _scenario_yields(F, c, K, n, f, exercises, observed_price, scenario_yields):
    yields, scenarios = [], []
    if observed_price is not None:
        observed_price = parse_number(observed_price, 'Observed full price')
        if observed_price <= 0: raise InputError('Observed full price must be positive.')
        for term in exercises:
            for right in ('call','put'):
                strike = term[right]
                if strike is None: continue
                rows = _schedule(F,c,float(strike),int(term['period']),f)
                y = _ytm_for_schedule(rows,observed_price,f)
                p = _price(rows,y,f)[0]
                yields.append({'right':right,'period':int(term['period']),'years':int(term['period'])/f,
                    'redemption':float(strike), 'observed_full_price':observed_price,
                    'nominal_annual_yield':y, 'periodic_yield':y/f,
                    'repricing_residual':p-observed_price, 'schedule':rows,
                    'meaning':'contractual date-specific scenario, not a guaranteed return'})
    if not isinstance(scenario_yields,list): raise InputError('Scenario yields must be a list.')
    if len(scenario_yields)>1000: raise UnsupportedInput('Too many yield scenarios.')
    for scenario in scenario_yields:
        if not isinstance(scenario,dict) or set(scenario) != {'label','yield','period','redemption'}:
            raise InputError('Yield scenario requires label, yield, period and redemption.')
        label = _label(scenario['label'],'Scenario label')
        p = parse_positive_integer(scenario['period'],'Scenario horizon in coupon periods')
        strike = parse_number(scenario['redemption'],'Scenario redemption')
        if p>n or strike<=0: raise InputError('Scenario horizon/redemption is invalid.')
        y = parse_number(scenario['yield'],'Scenario nominal annual yield')
        rows = _schedule(F,c,strike,p,f)
        price = _price(rows,y,f)[0]
        scenarios.append({'label':label,'period':p,'years':p/f,'nominal_annual_yield':y,
            'periodic_yield':y/f,'redemption':strike,'schedule':rows,'full_theoretical_price':price,
            'observed_baseline':observed_price, 'price_change':None if observed_price is None else price-observed_price,
            'percentage_change':None if observed_price is None else price/observed_price-1,
            'meaning':'prescribed fixed-redemption yield scenario, not stochastic option price'})
    return yields, scenarios


def analyze_option_bond(*, face, coupon_rate, years, frequency, discount_curve,
                        valuation_date, volatility, volatility_source, exercises, currency,
                        redemption=None, observed_price=None, scenario_yields=None,
                        substeps=1, monte_carlo=True, seed=None, training_paths=2000,
                        evaluation_paths=2000, mode='Standard', cancelled=lambda: False):
    """Calibrated tree, refined risks and information-safe MC verification protocol."""
    diagnostics = {}
    try:
        budget = Budget(mode, cancelled); budget.check()
        n,f = _periods(years,frequency,mode)
        ccy = parse_currency(currency); _day(valuation_date,'Valuation date')
        F = parse_number(face,'Face'); c = parse_number(coupon_rate,'Annual coupon rate')
        K = F if redemption is None else parse_number(redemption,'Maturity redemption')
        sigma = parse_number(volatility,'Annual absolute rate volatility')
        source = _label(volatility_source,'Volatility source/assumption')
        if F<=0 or K<=0 or c<0 or sigma<0: raise InputError('Invalid face, redemption, coupon or volatility.')
        if not isinstance(monte_carlo,bool): raise InputError('Monte Carlo selection must be true/false.')
        s = parse_positive_integer(substeps,'Substeps per coupon period')
        if 2*n*s>budget.steps: raise UnsupportedInput('Base plus refined grid exceeds the selected profile step limit.')
        curve = Curve(discount_curve,ccy,valuation_date,n/f,'Discount curve')
        terms = exercise_contract(exercises,n,s)
        finer_terms = exercise_contract(exercises,n,2*s)
        coupon = F*c/f
        if observed_price is not None: observed_price=parse_number(observed_price,'Observed full price')
        ys, scenarios = _scenario_yields(F,c,K,n,f,exercises,observed_price,scenario_yields or [])
        diagnostics.update({'observed_full_price':observed_price,'date_specific_yields':ys,'yield_scenarios':scenarios})
        grids=[]; risk=[]
        for mult in (1,2):
            ss = s*mult; N=n*ss; dt=1/(f*ss)
            ts = terms if mult==1 else finer_terms
            prices=[]
            for bump in (0.,-.0001,.0001):
                tree = calibrate(curve,N,dt,sigma,budget,bump)
                price,trace = tree_price(tree,coupon,K,ss,ts,budget,trace=bump==0)
                prices.append(price)
                if bump==0:
                    straight,_ = tree_price(tree,coupon,K,ss,{},budget)
                    curve_straight = math.fsum(coupon*curve.df(p/f) for p in range(1,n+1))+K*curve.df(n/f)
                    if abs(straight-curve_straight)>1e-8+1e-10*abs(curve_straight):
                        raise Incomplete('No-option tree does not match independently discounted cash flows.')
                    grids.append({'substeps':ss,'tree':tree,'terms':ts,'model_price':price,
                        'straight_curve_price':curve_straight,'straight_tree_price':straight,'exercise_trace':trace})
            base,down,up = prices
            if base<=0: raise UnsupportedInput('Effective risk requires a positive model price.')
            risk.append({'substeps':ss,'price':base,'price_down':down,'price_up':up,'bump_decimal':.0001,
                'effective_duration_years':(down-up)/(2*base*.0001),
                'effective_convexity_years_squared':(up+down-2*base)/(base*.0001**2)})
        allowance = (.02 if mode=='Standard' else .01)*F/100
        grid_error=abs(grids[1]['model_price']-grids[0]['model_price'])
        diagnostics.update({'model':'Ho–Lee additive recombining binomial v1',
            'tree_grids':[{key:value for key,value in g.items() if key not in {'tree','terms'}} |
                {'calibration':g['tree']['calibration'],'steps':g['tree']['steps'],'dt':g['tree']['dt']}
                for g in grids], 'risk':risk, 'grid_price_difference':grid_error,
            'grid_price_tolerance':allowance,
            'risk_refinement_difference':{k:risk[1][k]-risk[0][k] for k in
                ('effective_duration_years','effective_convexity_years_squared')}})
        if monte_carlo:
            from .monte_carlo_s6 import protocol
            diagnostics['monte_carlo'] = {}
            protocol(grids,coupon,K,F,training_paths,evaluation_paths,seed,budget,diagnostics['monte_carlo'])
        budget.check()
        diagnostics['elapsed_seconds'] = time.monotonic()-budget.started
        diagnostics['cumulative_generated_paths'] = budget.paths
        failures=[]
        if grid_error>allowance: failures.append('Tree grid refinement exceeds its declared price tolerance.')
        if monte_carlo and not diagnostics['monte_carlo']['converged']:
            failures.extend(diagnostics['monte_carlo']['failures'])
        if failures: raise Incomplete(' '.join(failures))
        return CalculationResult(Status.VALID,grids[-1]['model_price'],f'{ccy} per stated face',
            warnings=('Model value is not an observed quote. Ho–Lee has no mean reversion; volatility is an explicit input.',
                'Monte Carlo intervals cover sampling uncertainty conditional on the frozen fitted policy, not policy, grid or model bias.') if monte_carlo else
                ('Tree-only run selected; no Monte Carlo result is claimed.',),
            assumptions={'currency':ccy,'valuation_date':valuation_date,'discount_curve':curve.raw,
                'volatility':sigma,'volatility_source':source,'volatility_unit':'decimal rate per square-root year',
                'probabilities':[.5,.5],'measure':'risk-neutral','quote':'full price at coupon date; no accrual',
                'coupon_timing':'coupon once, then exercise/redemption','exercise_contracts':exercises,
                'interpolation':'log-linear DF; no extrapolation','risk_bump':'parallel continuous zero rate +/-1bp; recalibrate and re-exercise',
                'rate_scale':'decimal','model_version':'ho-lee-binomial-v1','mode':mode},diagnostics=diagnostics)
    except (InputError,TypeError,ValueError,OverflowError,ZeroDivisionError,FloatingPointError,np.linalg.LinAlgError,MemoryError) as exc:
        if 'budget' in locals():
            diagnostics['cumulative_generated_paths']=budget.paths
            diagnostics['elapsed_seconds']=time.monotonic()-budget.started
        return _failure(exc,diagnostics)
