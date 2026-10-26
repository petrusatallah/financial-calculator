"""S6 frozen-policy LSM on the approved calibrated Ho–Lee lattice.

REQ-MC-01/02/03: training targets can use future training cash flows;
evaluation decisions use only current state and frozen training coefficients.
"""
from __future__ import annotations

import math
import secrets
import numpy as np

from .bond_s6 import Incomplete, exercise_actions
from .validation import InputError, parse_positive_integer


def parse_seed(raw):
    if raw is None:
        return secrets.randbits(128)
    if isinstance(raw,bool) or not isinstance(raw,(str,int)):
        raise InputError('Seed must be an integer or integer text in [0,2^128).')
    try:
        seed = int(raw)
    except (TypeError, ValueError) as exc:
        raise InputError('Seed must be an integer.') from exc
    if isinstance(raw,str) and raw.strip() != str(seed):
        raise InputError('Seed text must be a canonical unsigned decimal integer.')
    if not 0 <= seed < 2**128:
        raise InputError('Seed must be in [0,2^128).')
    return seed


def paths(tree, count, stream, budget):
    N, dt = tree['steps'], tree['dt']
    budget.reserve(N,count)
    rng = np.random.Generator(np.random.PCG64(stream))
    indices = np.zeros(count,dtype=np.int32)
    rates = np.empty((count,N),dtype=float)
    discounts = np.empty((count,N),dtype=float)
    for i in range(N):
        budget.check()
        rates[:,i] = tree['rates'][i][indices]
        discounts[:,i] = np.exp(-rates[:,i]*dt)
        indices += rng.integers(0,2,size=count,dtype=np.int32)
    if not np.all(np.isfinite(discounts)):
        raise Incomplete('Path discount factors are non-finite.')
    return rates,discounts


def fit_continuation(x,y):
    center = float(np.mean(x)); scale = float(np.std(x))
    distinct = np.unique(x).size
    degree = min(2,distinct-1)
    if scale < 1e-14:
        degree = 0; scale = 1.
    z = (x-center)/scale
    reductions=[]
    while True:
        design = np.polynomial.polynomial.polyvander(z,degree)
        beta,_,rank,singular = np.linalg.lstsq(design,y,rcond=None)
        if rank == degree+1:
            condition = float(singular[0]/singular[-1])
            if not math.isfinite(condition) or condition>1e10:
                raise Incomplete('Continuation regression is ill-conditioned.')
            break
        if degree == 0:
            raise Incomplete('Continuation regression cannot be fitted.')
        reductions.append(f'rank {rank} insufficient for degree {degree}')
        degree -= 1
    if not np.all(np.isfinite(beta)):
        raise Incomplete('Continuation coefficients are non-finite.')
    return {'center':center,'scale':scale,'degree':degree,'coefficients':beta.tolist(),
        'condition_number':condition,'distinct_training_states':int(distinct),
        'basis_reduced':degree<2,'rank_reductions':reductions}


def predict(policy,x):
    return np.polynomial.polynomial.polyval((x-policy['center'])/policy['scale'],policy['coefficients'])


def _replace_cash(target,actions,call,put):
    output = target.copy()
    if call is not None: output[actions=='call'] = call
    if put is not None: output[actions=='put'] = put
    return output


def train(tree,rates,discounts,coupon,redemption,substeps,terms,budget):
    y = np.full(rates.shape[0],redemption+coupon)
    policies = {}
    for i in range(tree['steps']-1,-1,-1):
        budget.check()
        target = discounts[:,i]*y
        if i in terms:
            call,put,priority = terms[i]
            policy = fit_continuation(rates[:,i],target)
            prediction = predict(policy,rates[:,i])
            actions = exercise_actions(prediction,call,put,priority)
            target = _replace_cash(target,actions,call,put)
            policies[i] = policy
        y = target+(coupon if i>0 and i%substeps==0 else 0)
    return policies


def evaluate(tree,rates,discounts,policy,coupon,redemption,substeps,terms,budget):
    y = np.full(rates.shape[0],redemption+coupon)
    trace=[]
    for i in range(tree['steps']-1,-1,-1):
        budget.check()
        target = discounts[:,i]*y
        if i in terms:
            call,put,priority = terms[i]
            prediction = predict(policy[i],rates[:,i])
            actions = exercise_actions(prediction,call,put,priority)
            trace.append({'step':i,'years':i*tree['dt'],
                'state_rate_first_paths':rates[:5,i].tolist(),
                'predicted_continuation_first_paths':prediction[:5].tolist(),
                'actions_first_paths':actions[:5].tolist(),
                'action_counts':{key:int(np.count_nonzero(actions==key)) for key in ('call','put','continue')}})
            target = _replace_cash(target,actions,call,put)
        y = target+(coupon if i>0 and i%substeps==0 else 0)
    if not np.all(np.isfinite(y)):
        raise Incomplete('Monte Carlo payoffs are non-finite.')
    return y,sorted(trace,key=lambda row:row['step'])


def statistics(samples):
    n = len(samples)
    if n<2000: raise Incomplete('Insufficient evaluation paths to claim convergence.')
    mean = float(samples.mean())
    # Recognize truly deterministic payoff up to floating-point roundoff.
    std = float(np.std(samples,ddof=1))
    se = std/math.sqrt(n)
    return {'price':mean,'sample_standard_deviation':std,'standard_error':se,
        'confidence_interval_95':[mean-1.96*se,mean+1.96*se],
        'half_width_95':1.96*se,'paths':n}


def protocol(grids,coupon,redemption,face,training_paths,evaluation_paths,seed,budget,report=None):
    report={} if report is None else report
    root=parse_seed(seed)
    report.update(seed=root,generator='PCG64',numpy_version=np.__version__,
        completion='INCOMPLETE',converged=False,experiments=[])
    training = parse_positive_integer(training_paths,'Training paths')
    evaluation = parse_positive_integer(evaluation_paths,'Evaluation paths per batch')
    if min(training,evaluation)<2000:
        raise InputError('Training and each evaluation batch require at least 2000 paths.')
    total = 6*(training+2*evaluation)
    if total>budget.path_cap:
        raise Incomplete('Planned base/doubled and refined-grid protocol exceeds cumulative path limit.')
    sequence = np.random.SeedSequence(root)
    experiments = sequence.spawn(4)
    output=report['experiments']; failures=[]
    money = (.02 if budget.mode=='Standard' else .01)*face/100
    halfwidth = (.10 if budget.mode=='Standard' else .05)*face/100
    for grid_index,g in enumerate(grids):
        for doubled in (False,True):
            experiment = experiments[grid_index*2+int(doubled)]
            streams = experiment.spawn(3)
            mult = 2 if doubled else 1
            rates,discounts = paths(g['tree'],training*mult,streams[0],budget)
            policy = train(g['tree'],rates,discounts,coupon,redemption,g['substeps'],g['terms'],budget)
            del rates,discounts
            batches=[]; values=[]; traces=[]; replay=[]
            for b in range(2):
                rates,discounts = paths(g['tree'],evaluation*mult,streams[b+1],budget)
                if b==0: replay = rates[:3,:min(8,rates.shape[1])].tolist()
                samples,trace = evaluate(g['tree'],rates,discounts,policy,coupon,redemption,g['substeps'],g['terms'],budget)
                batches.append(statistics(samples)); values.append(samples); traces.append(trace)
                del rates,discounts
            summary = statistics(np.concatenate(values))
            item = {'grid_substeps':g['substeps'],'doubled_budget':doubled,
                'training_paths':training*mult,'evaluation_paths_per_batch':evaluation*mult,
                'stream_spawn_keys':[list(stream.spawn_key) for stream in streams],
                'policy':{str(k):v for k,v in sorted(policy.items())},'batches':batches,
                'combined':summary,'same_grid_tree_price':g['model_price'],
                'replay_rate_paths':replay,'evaluation_exercise_trace':traces,
                'policy_frozen_before_evaluation':True}
            tolerance = 4*summary['standard_error']+money
            item['tree_comparison_limit'] = tolerance
            item['tree_error'] = abs(summary['price']-g['model_price'])
            batch_limit=4*math.hypot(batches[0]['standard_error'],batches[1]['standard_error'])+money
            item['batch_comparison_limit']=batch_limit
            item['batch_difference']=abs(batches[0]['price']-batches[1]['price'])
            item['half_width_limit']=halfwidth
            if summary['half_width_95']>halfwidth:
                failures.append(f'Grid {g["substeps"]} doubled={doubled}: sampling interval too wide.')
            if item['tree_error']>tolerance:
                failures.append(f'Grid {g["substeps"]} doubled={doubled}: Monte Carlo/tree disagreement.')
            if item['batch_difference']>batch_limit:
                failures.append(f'Grid {g["substeps"]} doubled={doubled}: independent batches disagree.')
            output.append(item)
    doubling=[]
    for idx in (0,2):
        one,two = output[idx]['combined'],output[idx+1]['combined']
        limit=4*math.hypot(one['standard_error'],two['standard_error'])+money
        difference=abs(one['price']-two['price'])
        doubling.append({'grid_substeps':output[idx]['grid_substeps'],'difference':difference,'limit':limit})
        if difference>limit: failures.append('Path-doubling prices disagree beyond declared uncertainty.')
    # MC grid comparison is reported separately; deterministic tree refinement gates price.
    report.update({'seed':root,'generator':'PCG64','numpy_version':np.__version__,
        'stream_construction':'SeedSequence.spawn: distinct training/evaluation streams',
        'experiments':output,'path_doubling':doubling,'converged':not failures,'failures':failures,
        'cumulative_generated_paths':budget.paths,'final':output[-1]['combined'],
        'grid_difference':abs(output[-1]['combined']['price']-output[1]['combined']['price']),
        'uncertainty_scope':'Approximate normal 95% interval conditional on each frozen fitted policy; excludes policy, discretization, parameter and model bias.',
        'completion':'COMPLETE' if not failures else 'INCOMPLETE'})
    return report
