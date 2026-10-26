"""S5 approved market data: typed provenance, calendar checks and offline calculations."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time as wall_time, timedelta, timezone
import calendar
import math
import time
from zoneinfo import ZoneInfo

from .result import CalculationResult, Status
from .validation import InputError, UnsupportedInput, parse_currency, parse_number

FIELDS = ('provider', 'instrument', 'asset_class', 'date', 'value', 'currency', 'unit',
          'frequency', 'adjustment', 'timezone', 'retrieved_at', 'source', 'source_period',
          'raw_close', 'distribution', 'split_factor', 'source_timestamp', 'published_date', 'warnings')
CLASSES = {'stock', 'etf', 'fx', 'yield', 'commodity'}
MANUAL_CLASSES = {'bond', 'index', 'crypto'}
PROVIDERS = {'manual', 'tiingo', 'ecb', 'treasury', 'world_bank'}


class Incomplete(InputError):
    pass


def profile(mode, count, instruments, started):
    if mode not in {'Standard', 'Advanced'}:
        raise InputError('Mode must be Standard or Advanced.')
    assets, rows, seconds, memory = (50, 5000, 10, 256) if mode == 'Standard' else (200, 20000, 30, 512)
    if count > rows or instruments > assets:
        raise UnsupportedInput(f'{mode} supports {assets} instruments and {rows} total observations.')
    if count * 8192 > memory * 1024 * 1024:
        raise Incomplete('Estimated data working memory exceeded.')
    if time.monotonic() - started > seconds:
        raise Incomplete(f'{mode} data processing exceeded {seconds} seconds.')


def utc(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise InputError('Retrieval time must include its UTC offset.') from exc


def observation(*, provider, instrument, asset_class, day, value, currency, unit,
                frequency='daily', adjustment='unadjusted', source, retrieved_at,
                source_timezone, source_period='', raw_close=None, distribution=None,
                split_factor=None, source_timestamp=None, published_date=None, warnings=()):
    return dict(zip(FIELDS, (provider, instrument, asset_class, day, value, currency, unit,
        frequency, adjustment, source_timezone, retrieved_at, source, source_period,
        raw_close, distribution, split_factor, source_timestamp or day, published_date, list(warnings))))


def validate(rows, mode='Standard', *, started=None):
    started = time.monotonic() if started is None else started
    if not isinstance(rows, (list, tuple)) or not rows:
        raise InputError('Enter at least one typed observation.')
    profile(mode, len(rows), 0, started)
    result, seen, identities = [], set(), {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise InputError('Observation fields do not match the S5 typed schema.')
        out = dict(row)
        for key in ('provider', 'instrument', 'asset_class', 'unit', 'frequency', 'adjustment', 'timezone', 'source'):
            if not isinstance(out[key], str) or not out[key].strip() or len(out[key]) > 2048:
                raise InputError(f'{key} must be explicit bounded text.')
            out[key] = out[key].strip()
        if out['provider'] not in PROVIDERS or out['asset_class'] not in (CLASSES | (MANUAL_CLASSES if out['provider'] == 'manual' else set())):
            raise UnsupportedInput('Provider or asset class is outside approved S5 coverage.')
        if out['frequency'] not in {'daily', 'weekly', 'monthly'}:
            raise UnsupportedInput('Frequency must be daily, weekly or monthly.')
        out['currency'] = parse_currency(out['currency'])
        try:
            day = date.fromisoformat(out['date'])
            ZoneInfo(out['timezone'])
        except (TypeError, ValueError, KeyError) as exc:
            raise InputError('Invalid observation date or source timezone.') from exc
        retrieved = utc(out['retrieved_at'])
        if not isinstance(out['source_timestamp'], str) or len(out['source_timestamp']) > 64:
            raise InputError('Source timestamp must preserve a bounded source date/time.')
        stamp_day = utc(out['source_timestamp']).date() if 'T' in out['source_timestamp'] else date.fromisoformat(out['source_timestamp'])
        if stamp_day != day:
            raise InputError('Source timestamp date and observation date do not agree.')
        if 'T' in out['source_timestamp'] and utc(out['source_timestamp']) > retrieved:
            raise InputError('Source timestamp cannot be later than retrieval time.')
        out['retrieved_at'] = retrieved.isoformat()
        if out['published_date'] is not None:
            published = date.fromisoformat(out['published_date'])
            if published < day or published > retrieved.date():
                raise InputError('Publication date must be between observation and retrieval.')
        if day > retrieved.astimezone(ZoneInfo(out['timezone'])).date():
            raise InputError('Observation date cannot be after retrieval date.')
        if not isinstance(out['source_period'], str) or len(out['source_period']) > 32:
            raise InputError('Source period must be short text.')
        if not isinstance(out['warnings'], list) or any(not isinstance(w, str) or len(w) > 2048 for w in out['warnings']):
            raise InputError('Warnings must be bounded text items.')
        if sum(len(str(v)) for v in out.values()) > 8192:
            raise InputError('Observation metadata exceeds its bounded record size.')
        for key in ('value', 'raw_close', 'distribution', 'split_factor'):
            if out[key] is not None:
                out[key] = parse_number(out[key], key)
        if out['value'] is not None and out['asset_class'] != 'yield' and out['value'] <= 0:
            raise InputError('Prices and FX reference rates must be positive.')
        if out['raw_close'] is not None and out['raw_close'] <= 0 or out['split_factor'] is not None and out['split_factor'] <= 0:
            raise InputError('Raw close and split factor must be positive.')
        provider = out['provider']
        if provider == 'ecb' and (out['instrument'],out['asset_class'],out['currency'],out['unit']) != ('EURUSD','fx','USD','USD per EUR'):
            raise InputError('ECB observation identity, currency or quote direction mismatch.')
        if provider == 'treasury' and (out['asset_class'] != 'yield' or out['currency'] != 'USD' or
                out['unit'] != 'decimal nominal annual par yield' or out['instrument'] not in
                {'UST:'+t for t in ('1 Mo','3 Mo','6 Mo','1 Yr','2 Yr','3 Yr','5 Yr','7 Yr','10 Yr','20 Yr','30 Yr')}):
            raise InputError('Treasury yields require explicit decimal annual par-yield units.')
        if provider == 'world_bank' and (out['asset_class'] != 'commodity' or out['currency'] != 'USD' or
                out['frequency'] != 'monthly' or out['instrument'] not in {'BRENT','GOLD'}):
            raise InputError('World Bank observation is outside approved monthly commodity coverage.')
        if provider == 'world_bank' and (out['unit'] != {'BRENT':'USD per barrel','GOLD':'USD per troy ounce'}[out['instrument']]
                or out['source_period'] != out['date'][:7]):
            raise InputError('World Bank source period or commodity unit mismatch.')
        if provider == 'tiingo' and (out['asset_class'] not in {'stock','etf'} or out['currency'] != 'USD' or
                out['unit'] != 'USD per share' or out['adjustment'] != 'split_and_dividend_adjusted_close'):
            raise InputError('Tiingo observations require the explicit approved adjusted-close basis.')
        if provider == 'tiingo' and out['value'] is not None and any(out[k] is None for k in ('raw_close','distribution','split_factor')):
            raise InputError('Tiingo observations require the original raw-close and corporate-action fields.')
        expected_zone = {'ecb':'Europe/Berlin','treasury':'America/New_York','tiingo':'America/New_York','world_bank':'UTC'}
        if provider in expected_zone and out['timezone'] != expected_zone[provider]:
            raise InputError('Provider source timezone mismatch.')
        identity = (out['provider'], out['instrument'])
        basis = tuple(out[k] for k in ('currency', 'unit', 'asset_class', 'frequency', 'adjustment', 'timezone'))
        if identity in identities and identities[identity] != basis:
            raise InputError('An instrument cannot mix currencies, units, frequencies or adjustment bases.')
        identities[identity] = basis
        key = (*identity, out['date'])
        if key in seen:
            raise InputError('Duplicate or conflicting observation rows are not allowed.')
        seen.add(key)
        if out['value'] is None:
            out['warnings'] = list(dict.fromkeys(out['warnings'] + ['Missing observation; no zero or carry-forward substitution.']))
        result.append(out)
        profile(mode, len(result), len(identities), started)
    return sorted(result, key=lambda r: (r['provider'], r['instrument'], r['date']))


def _nth(year, month, weekday, n):
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last(year, month, weekday):
    last = date(year, month, calendar.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day):
    return day - timedelta(days=1) if day.weekday() == 5 else day + timedelta(days=1) if day.weekday() == 6 else day


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19*a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    return date(year, month, (h + l - 7*m + 114) % 31 + 1)


def business_day(day, calendar_name):
    if day.weekday() >= 5:
        return False
    y, easter = day.year, _easter(day.year)
    if calendar_name == 'TARGET':
        holidays = {date(y, 1, 1), date(y, 5, 1), date(y, 12, 25), date(y, 12, 26),
                    easter-timedelta(days=2), easter+timedelta(days=1)}
    elif calendar_name in {'US_FEDERAL', 'NYSE'}:
        holidays = {_nth(y, 2, 0, 3), _last(y, 5, 0), _nth(y, 9, 0, 1), _nth(y, 11, 3, 4)}
        if y >= (1998 if calendar_name == 'NYSE' else 1986):
            holidays.add(_nth(y, 1, 0, 3))
        for year in (y-1, y, y+1):
            for month, daynum in ((1, 1), (7, 4), (12, 25)):
                fixed = date(year, month, daynum)
                # NYSE does not observe a Saturday New Year on the preceding Friday.
                if calendar_name == 'NYSE' and month == 1 and fixed.weekday() == 5:
                    continue
                holidays.add(_observed(fixed))
            if year >= (2022 if calendar_name == 'NYSE' else 2021):
                holidays.add(_observed(date(year, 6, 19)))
        if calendar_name == 'NYSE':
            holidays.add(easter-timedelta(days=2))
            # Published extraordinary full-session closures in supported history.
            holidays.update(date.fromisoformat(d) for d in ('2001-09-11','2001-09-12','2001-09-13','2001-09-14',
                '2004-06-11','2007-01-02','2012-10-29','2012-10-30','2018-12-05','2025-01-09'))
        else:
            holidays.update({_nth(y, 10, 0, 2), _observed(date(y, 11, 11))})
    elif calendar_name == 'WEEKDAY':
        holidays = set()
    else:
        raise InputError('Unknown publication calendar.')
    return day not in holidays


def _next(day, calendar_name):
    day += timedelta(days=1)
    while not business_day(day, calendar_name):
        day += timedelta(days=1)
    return day


def freshness(row, now):
    now = utc(now)
    observed = date.fromisoformat(row['date'])
    provider = row['provider']
    if provider == 'manual':
        return {'state': 'manual_as_of', 'deadline': None, 'label': 'Manual value as of '+row['date']}
    if provider == 'world_bank':
        # Monthly averages are published in the next month. They remain current
        # until the NEXT scheduled monthly publication plus the approved grace.
        publication = date(observed.year+(observed.month==12), observed.month%12+1, 1)
        month = date(publication.year + (publication.month == 12), publication.month % 12 + 1, 1)
        fourth = month - timedelta(days=1)
        for _ in range(4):
            fourth = _next(fourth, 'WEEKDAY')
        deadline = datetime.combine(fourth, wall_time(23, 59, 59), timezone.utc)
    else:
        name, tz, hour = {'ecb': ('TARGET', 'Europe/Berlin', 20),
                          'treasury': ('US_FEDERAL', 'America/New_York', 23),
                          'tiingo': ('NYSE', 'America/New_York', 20)}[provider]
        minute, second = (59, 59) if provider == 'treasury' else (0, 0)
        deadline = datetime.combine(_next(observed, name), wall_time(hour, minute, second), ZoneInfo(tz))
    stale = now > deadline
    return {'state': 'stale' if stale else 'latest_available', 'deadline': deadline.isoformat(),
            'label': ('Stale observation' if stale else 'Latest available observation')+' as of '+row['date']}


def resample(rows, frequency, mode='Standard'):
    rows = validate(rows, mode)
    if frequency not in {'daily', 'weekly', 'monthly'}:
        raise UnsupportedInput('Only daily, weekly or monthly observations are supported.')
    if all(r['frequency'] == frequency for r in rows):
        return rows
    if any(r['adjustment'] == 'raw_total_return' for r in rows):
        raise UnsupportedInput('Raw daily corporate actions cannot be reduced by endpoint selection; supply adjusted closes or explicit period-level total-return observations.')
    if any(r['frequency'] != 'daily' for r in rows) or frequency == 'daily':
        raise UnsupportedInput('Only daily observations can be reduced to weekly or monthly.')
    selected = {}
    for row in rows:
        day = date.fromisoformat(row['date'])
        period = f'{day.isocalendar().year}-W{day.isocalendar().week:02}' if frequency == 'weekly' else row['date'][:7]
        key = row['provider'], row['instrument'], period
        selected[key] = row
    result = []
    for row in selected.values():
        out = dict(row, frequency=frequency)
        out['warnings'] = list(row['warnings']) + ['Derived last actual daily observation; date retained; not a period average.']
        result.append(out)
    return result


def analyze_data(rows, mode='Standard', *, now=None):
    started = time.monotonic()
    try:
        rows = validate(rows, mode, started=started)
        if all(row['value'] is None for row in rows):
            raise Incomplete('No usable observations; missing data cannot be a successful result.')
        now = now or datetime.now(timezone.utc).isoformat()
        groups = defaultdict(list)
        warnings = []
        for row in rows:
            groups[(row['provider'], row['instrument'])].append(row)
            warnings.extend(row['warnings'])
        series, latest = {}, {}
        for key, values in groups.items():
            label = '/'.join(key)
            previous, previous_day, returns = None, None, []
            for row in values:
                if row['asset_class'] == 'yield':
                    previous = None  # yield changes are not investment price returns
                    continue
                value = row['value']
                day = date.fromisoformat(row['date'])
                if previous_day is not None and row['frequency'] == 'monthly' and (day.year*12+day.month)-(previous_day.year*12+previous_day.month) != 1:
                    previous = None
                    warnings.append(label+': missing monthly period; no one-period return across the gap.')
                if previous_day is not None and row['frequency'] == 'weekly' and (
                        (day-timedelta(days=day.weekday()))-(previous_day-timedelta(days=previous_day.weekday())) != timedelta(days=7)):
                    previous = None
                    warnings.append(label+': missing weekly period; no one-period return across the gap.')
                if previous is not None and value is not None:
                    if row['adjustment'] == 'raw_total_return':
                        if row['distribution'] is None or row['split_factor'] is None:
                            raise InputError('Raw total returns require explicit distribution and split evidence for every period.')
                        change = (value+row['distribution'])*row['split_factor']/previous-1
                    else:
                        change = value/previous-1
                    if not math.isfinite(change):
                        raise InputError('Observation return overflowed.')
                    returns.append({'date': row['date'], 'return': change})
                previous = value  # null breaks the chain
                previous_day = day
            series[label] = returns
            latest[label] = freshness(values[-1], now)
            if values[-1]['value'] is None:
                latest[label] = {'state':'missing','deadline':None,'label':'Latest source row is missing a value as of '+values[-1]['date']}
            if latest[label]['state'] == 'stale':
                warnings.append(label+': '+latest[label]['label'])
        profile(mode, len(rows), len(groups), started)
        return CalculationResult(Status.VALID, None, 'market data', warnings=tuple(dict.fromkeys(warnings)),
            assumptions={'returns': 'close-to-close change on declared basis; monthly commodity changes compare averages',
                         'missing': 'no substitution or bridging', 'freshness': 'approved D11 publication calendar'},
            diagnostics={'observations': rows, 'returns': series, 'latest': latest, 'row_count': len(rows)})
    except (InputError, TypeError, ValueError, OverflowError) as exc:
        status = Status.INCOMPLETE if isinstance(exc, Incomplete) else Status.UNSUPPORTED if isinstance(exc, UnsupportedInput) else Status.INVALID
        return CalculationResult(status, None, 'market data', message=str(exc))


def convert_fx(prices, fx, *, base_currency, mode='Standard'):
    """FX must be explicit base units per one foreign unit on exactly matching dates."""
    prices, fx = validate(prices, mode), validate(fx, mode)
    base_currency = parse_currency(base_currency)
    if len({r['instrument'] for r in prices}) != 1 or len({r['instrument'] for r in fx}) != 1:
        raise InputError('FX conversion accepts one asset and one FX series.')
    foreign = prices[0]['currency']
    if any(r['asset_class'] in {'yield','fx'} for r in prices):
        raise InputError('FX conversion here applies to asset prices, not yields or another FX quote.')
    if any(r['asset_class'] != 'fx' or r['currency'] != base_currency or r['unit'] != f'{base_currency} per {foreign}' for r in fx):
        raise InputError('FX direction must be base-currency units per one foreign-currency unit.')
    if {r['date'] for r in prices} != {r['date'] for r in fx} or prices[0]['frequency'] != fx[0]['frequency']:
        raise InputError('Asset and FX dates/frequency must match exactly; no filling.')
    rates = {r['date']: r for r in fx}
    converted = []
    for row in prices:
        rate = rates[row['date']]
        value = None if row['value'] is None or rate['value'] is None else row['value'] * rate['value']
        if value is not None and not math.isfinite(value):
            raise InputError('Converted value overflowed.')
        converted.append({'date': row['date'], 'value': value, 'currency': base_currency,
                          'asset_source': row, 'fx_source': rate})
    return converted

