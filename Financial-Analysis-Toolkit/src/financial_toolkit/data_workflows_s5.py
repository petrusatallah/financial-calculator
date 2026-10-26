"""UI-independent manual entry and portfolio handoff for S5."""
import csv
from datetime import datetime, timezone
import io
from dataclasses import replace

from .market_data_s5 import observation, validate, analyze_data
from .io_s5 import portfolio_assets
from .portfolio_s4 import analyze_portfolio
from .validation import InputError


def manual_rows(text, *, instrument, asset_class='stock', currency='USD', unit='USD per share',
                frequency='daily', adjustment='unadjusted', source='user manual entry', mode='Standard'):
    reader = csv.DictReader(io.StringIO(text.strip()))
    if reader.fieldnames != ['date','value','distribution','split_factor']:
        raise InputError('Manual columns must be date,value,distribution,split_factor.')
    retrieved = datetime.now(timezone.utc).isoformat()
    rows=[]
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise InputError('Malformed manual observation row.')
        rows.append(observation(provider='manual',instrument=instrument,asset_class=asset_class,day=row['date'],
            value=row['value'] if row['value'].strip() else None,currency=currency,unit=unit,frequency=frequency,
            adjustment=adjustment,source=source,retrieved_at=retrieved,source_timezone='UTC',
            distribution=row['distribution'] if row['distribution'].strip() else None,
            split_factor=row['split_factor'] if row['split_factor'].strip() else None))
        if len(rows)>20000:
            raise InputError('Manual observation count exceeds Advanced bound.')
    return validate(rows,mode)


def analyze_loaded_portfolio(rows, weight_text, mode='Standard'):
    parts=[piece.strip().split('=',1) for piece in weight_text.split(',')]
    if any(len(part)!=2 or not part[0] for part in parts) or len({p[0] for p in parts})!=len(parts):
        raise InputError('Enter unique provider/instrument=weight pairs.')
    assets=portfolio_assets(rows,mode)
    currencies={a['currency'] for a in assets}
    frequencies={a['frequency'] for a in assets}
    if len(currencies)!=1 or len(frequencies)!=1:
        raise InputError('Portfolio assets require one currency and frequency; convert FX explicitly first.')
    result=analyze_portfolio(assets=assets,weights=dict(parts),currency=currencies.pop(),frequency=frequencies.pop(),mode=mode)
    data=analyze_data(rows,mode)
    if result.ok:
        result=replace(result,diagnostics={**result.diagnostics,'data_provenance':data.diagnostics['observations'],
            'data_latest':data.diagnostics['latest']})
    return replace(result,warnings=tuple(dict.fromkeys((*data.warnings,*result.warnings))))
