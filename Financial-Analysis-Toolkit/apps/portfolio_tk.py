"""Tkinter Portfolio entry point with Markowitz and comparison workflows."""
from __future__ import annotations

import csv
import io
import math
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from apps.portfolio_excel import portfolio_excel_bytes
from apps.portfolio_io import parse_portfolio_file
from financial_toolkit.optimization_s4 import efficient_frontier, optimize_portfolio, validate_portfolio_constraints
from financial_toolkit.portfolio_s4 import analyze_optimization_inputs, compare_return_histories
from financial_toolkit.validation import InputError


def _percent(raw, label):
    text = str(raw).strip().removesuffix('%').strip()
    try:
        value = float(text)/100
    except ValueError as exc:
        raise InputError(f'{label} needs a percentage number (10 means 10%).') from exc
    if not math.isfinite(value):
        raise InputError(f'{label} must be finite.')
    return value


def _read_csv(text, *, minimum_rows=2):
    rows = list(csv.reader(io.StringIO(text.strip())))
    if len(rows) < minimum_rows+1 or len(rows[0]) < 3 or rows[0][0].strip().lower() != 'date':
        raise InputError('Use a Date,name,name header and at least two complete return rows.')
    names = [name.strip() for name in rows[0][1:]]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise InputError('Names must be nonblank and unique.')
    days, values = [], []
    for row in rows[1:]:
        if len(row) != len(names)+1:
            raise InputError('Every return row must have one value per column.')
        try:
            days.append(date.fromisoformat(row[0].strip()).isoformat())
        except ValueError as exc:
            raise InputError('Dates must be YYYY-MM-DD.') from exc
        values.append([_percent(raw, name) for name, raw in zip(names, row[1:])])
    if days != sorted(set(days)):
        raise InputError('Dates must be unique and increasing.')
    return names, days, values


class PortfolioWeek11Tabs:
    def __init__(self, parent, mode='Standard'):
        self.mode = mode
        style = ttk.Style(parent)
        style.configure('Portfolio.Treeview', background='#111827', foreground='#e5e7eb',
                        fieldbackground='#111827', rowheight=25)
        style.configure('Portfolio.Treeview.Heading', background='#1f2937', foreground='#e5e7eb')
        style.map('Portfolio.Treeview', background=[('selected','#2563eb')])
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill='both', expand=True)
        self.tabs = {}
        self.controls = {}
        self.saved = {}
        for key, label in [('markowitz', 'Markowitz Optimization'), ('compare', 'Compare Portfolios')]:
            tab = ttk.Frame(self.notebook, padding=10)
            self.notebook.add(tab, text=label)
            self.tabs[key] = tab
            self._build(tab, key)

    def _entry(self, parent, label, value=''):
        box = ttk.Frame(parent)
        box.pack(fill='x', pady=2)
        ttk.Label(box, text=label).pack(side='left', padx=(0, 8))
        entry = ttk.Entry(box)
        entry.insert(0, value)
        entry.pack(side='left', fill='x', expand=True)
        return entry

    def _text(self, parent, label, value, height=5):
        ttk.Label(parent, text=label).pack(anchor='w', pady=(8, 0))
        text = tk.Text(parent, height=height, wrap='none')
        text.insert('1.0', value)
        text.pack(fill='x')
        return text

    def _build(self, tab, key):
        canvas = tk.Canvas(tab, highlightthickness=0)
        scroll = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(canvas, padding=8)
        window = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda event, c=canvas: c.configure(scrollregion=c.bbox('all')))
        canvas.bind('<Configure>', lambda event, c=canvas, w=window: c.itemconfigure(w, width=event.width))
        c = self.controls[key] = {}
        ttk.Label(body, text='Step 1 · Data input', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        choice = c['choice'] = tk.StringVar(value='Enter manually')
        row = ttk.Frame(body); row.pack(fill='x')
        for label in ('Enter manually', 'Import Excel / CSV'):
            ttk.Radiobutton(row, text=label, variable=choice, value=label).pack(side='left', padx=5)
        if key == 'markowitz':
            basis = c['basis'] = tk.StringVar(value='Historical investment returns')
            row = ttk.Frame(body); row.pack(fill='x')
            for label in ('Historical investment returns', 'Expected returns and covariance'):
                ttk.Radiobutton(row, text=label, variable=basis, value=label).pack(side='left', padx=5)
        frequency = c['frequency'] = ttk.Combobox(body, values=('monthly', 'yearly'), state='readonly')
        frequency.set('monthly')
        ttk.Label(body, text='Frequency').pack(anchor='w')
        frequency.pack(anchor='w')
        c['source_scale'] = ttk.Combobox(body, values=('auto', 'percent', 'decimal'), state='readonly')
        c['source_scale'].set('auto')
        ttk.Label(body, text='Unmarked return scale: Auto reads % signs and Excel percent formats; plain numbers need Percent or Decimal').pack(anchor='w')
        c['source_scale'].pack(anchor='w')
        import_row = ttk.Frame(body); import_row.pack(fill='x', pady=4)
        ttk.Button(import_row, text='Import Excel / CSV', command=lambda: self._import(key)).pack(side='left')
        ttk.Button(import_row, text='Accept preview', command=lambda: self._accept(key)).pack(side='left', padx=5)
        c['preview'] = self._text(body, 'Import preview (accept to use; Summary has no raw returns)', '', 4)
        ttk.Label(body, text='Step 2 · '+('Investments' if key=='markowitz' else 'Create portfolios'), font=('Segoe UI', 13, 'bold')).pack(anchor='w', pady=(10, 0))
        c['names'] = self._entry(body, 'Names (comma separated)', 'Investment 1,Investment 2' if key=='markowitz' else 'Portfolio A,Portfolio B')
        names_row = ttk.Frame(body); names_row.pack(fill='x')
        ttk.Button(names_row, text='Add '+('investment' if key=='markowitz' else 'portfolio'), command=lambda: self._add_name(key)).pack(side='left')
        ttk.Button(names_row, text='Remove last', command=lambda: self._remove_name(key)).pack(side='left', padx=5)
        ttk.Label(body, text='Step 3 · Dated returns (editable CSV table; each value is a percent)', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(10, 0))
        year = date.today().year
        names = ['Investment 1', 'Investment 2'] if key=='markowitz' else ['Portfolio A', 'Portfolio B']
        initial = 'Date,'+','.join(names)+'\n'+ '\n'.join(f'{year}-{month:02d}-{day:02d},,' for month,day in [(1,31),(2,28),(3,31)])
        c['returns'] = self._text(body, 'Date | '+ ' | '.join(names), initial, 6)
        dates_row = ttk.Frame(body); dates_row.pack(fill='x')
        ttk.Button(dates_row, text='Add Row', command=lambda: self._add_row(key)).pack(side='left')
        ttk.Button(dates_row, text='Remove last row', command=lambda: self._remove_row(key)).pack(side='left', padx=5)
        if key == 'markowitz':
            c['means'] = self._text(body, 'Expected returns per selected period: Investment,Return (%)', 'Investment 1,\nInvestment 2,', 3)
            c['covariance'] = self._text(body, 'Covariance: first row names; values in decimal return squared',
                'Investment,Investment 1,Investment 2\nInvestment 1,,\nInvestment 2,,', 4)
            c['current'] = self._text(body, 'Current weights (optional): Investment,Weight (%)', '', 3)
            ttk.Label(body, text='Step 3 · Optimization settings', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(10, 0))
            c['objective'] = ttk.Combobox(body, values=('Minimum Variance','Maximum Sharpe Ratio','Target Return','Efficient Frontier'), state='readonly')
            c['objective'].set('Minimum Variance'); c['objective'].pack(anchor='w')
            c['target'] = self._entry(body, 'Target return (%)')
            ttk.Label(body, text='Step 4 · Portfolio constraints', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(10, 0))
            ttk.Label(body, text='A · Individual investment limits (double-click a percentage to edit)').pack(anchor='w')
            c['bounds_view'] = ttk.Treeview(body, columns=('Investment','Minimum weight (%)','Maximum weight (%)'),
                                            show='headings', height=4, style='Portfolio.Treeview')
            for column in ('Investment','Minimum weight (%)','Maximum weight (%)'):
                c['bounds_view'].heading(column, text=column)
                c['bounds_view'].column(column, width=180)
            c['bounds_view'].pack(fill='x')
            self._rebuild_bounds(c, ['Investment 1','Investment 2'])
            c['bounds_view'].bind('<Double-1>', lambda event: self._edit_bound(key,event))
            c['short'] = tk.BooleanVar(value=False)
            ttk.Checkbutton(body, text='Allow short selling', variable=c['short']).pack(anchor='w')
            ttk.Label(body, text='B · Custom group constraints').pack(anchor='w', pady=(8,0))
            c['groups'] = []
            c['groups_view'] = ttk.Treeview(body, columns=('Group','Investments','Maximum (%)','Minimum (%)'),
                                            show='headings', height=4, style='Portfolio.Treeview')
            for column in ('Group','Investments','Maximum (%)','Minimum (%)'):
                c['groups_view'].heading(column, text=column)
                c['groups_view'].column(column, width=150)
            c['groups_view'].pack(fill='x')
            c['groups_view'].bind('<Double-1>', lambda event: self._group_dialog(key, edit=True))
            group_buttons = ttk.Frame(body); group_buttons.pack(fill='x')
            ttk.Button(group_buttons, text='Add Group', command=lambda: self._group_dialog(key)).pack(side='left')
            ttk.Button(group_buttons, text='Remove Group', command=lambda: self._remove_group(key)).pack(side='left', padx=5)
            ttk.Label(body, text='C · Portfolio allocation validation').pack(anchor='w', pady=(8,0))
            ttk.Label(body, text='Target net portfolio allocation: 100%. With no cash or funding, weights total 100%.').pack(anchor='w')
            c['constraint_status'] = ttk.Label(body, text='Limits are valid until edited.')
            c['constraint_status'].pack(anchor='w')
            advanced = ttk.Frame(body)
            ttk.Button(body, text='Advanced Exposure Settings ▸',
                       command=lambda: advanced.pack_forget() if advanced.winfo_manager() else advanced.pack(fill='x')).pack(anchor='w', pady=(8,0))
            c['gross'] = self._entry(advanced, 'Gross exposure cap (%)', '100')
            c['netmin'] = self._entry(advanced, 'Minimum net risky exposure (%)', '100')
            c['netmax'] = self._entry(advanced, 'Maximum net risky exposure (%)', '100')
            c['cash'] = tk.BooleanVar(value=False)
            ttk.Checkbutton(advanced, text='Allow cash or funding', variable=c['cash']).pack(anchor='w')
            c['yield'] = self._entry(advanced, 'Annual effective cash yield (%)')
            c['funding'] = self._entry(advanced, 'Annual effective funding rate (%) — required for borrowing')
            c['sectors'] = self._text(advanced, 'Optional existing sector caps: Investment,Sector,maximum sector %', '', 3)
        c['rf'] = self._entry(body, 'Annual effective risk-free rate (%) (required for Maximum Sharpe)')
        ttk.Label(body, text='Step '+('5 · Optimize' if key=='markowitz' else '4 · Calculate'), font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(10, 0))
        action = ttk.Frame(body); action.pack(fill='x')
        ttk.Button(action, text='Optimize Portfolio' if key=='markowitz' else 'Calculate Analysis',
                   command=lambda: self._calculate(key)).pack(side='left')
        ttk.Button(action, text='Reset', command=lambda: self._reset(key)).pack(side='left', padx=5)
        ttk.Button(action, text='Export to Excel', command=lambda: self._export(key)).pack(side='left')
        ttk.Label(body, text='Step '+('6' if key=='markowitz' else '5')+' · Results', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(10, 0))
        c['output'] = self._text(body, 'Results and solver diagnostics', '', 16)
        if key == 'markowitz':
            for field in ('gross','netmin','netmax','yield','funding'):
                c[field].bind('<FocusOut>', lambda event: self._validate_ui_constraints('markowitz'))
            c['short'].trace_add('write', lambda *_: self._validate_ui_constraints('markowitz'))
            c['cash'].trace_add('write', lambda *_: self._validate_ui_constraints('markowitz'))
            self._validate_ui_constraints(key)
        figure = Figure(figsize=(6, 3), facecolor='#111827')
        axes = figure.add_subplot(111)
        axes.set_facecolor('#111827')
        canvas = FigureCanvasTkAgg(figure, master=body)
        canvas.get_tk_widget().pack(fill='x', pady=8)
        c['chart'] = (axes, canvas)

    def _chart(self, key, result, frontier=None):
        axes, canvas = self.controls[key]['chart']
        axes.clear()
        axes.set_facecolor('#111827')
        axes.tick_params(colors='white')
        for spine in axes.spines.values(): spine.set_color('#77849a')
        if key == 'compare':
            for item in result.diagnostics['comparison']:
                axes.plot(result.diagnostics['dates'], [value*100 for value in item['path']], marker='o', label=item['name'])
            axes.set_ylabel('Cumulative return (%)', color='white')
            axes.tick_params(axis='x', rotation=25)
        else:
            points = frontier.diagnostics['points']
            axes.plot([point['volatility']*100 for point in points],
                      [point['return']*100 for point in points], marker='o', label='Efficient frontier')
            minimum = frontier.diagnostics['minimum_variance']
            axes.scatter([minimum['volatility']*100], [minimum['expected_return']*100],
                         color='#34d399', s=80, label='Minimum variance')
            axes.scatter([result.diagnostics['volatility']*100], [result.diagnostics['expected_return']*100],
                         color='#fbbf24', s=80, label='Selected result')
            axes.set_xlabel('Volatility (%)', color='white')
            axes.set_ylabel('Expected return (%)', color='white')
        legend = axes.legend(facecolor='#1f2937', edgecolor='#77849a')
        for label in legend.get_texts(): label.set_color('white')
        axes.figure.tight_layout()
        canvas.draw_idle()

    def _names(self, key):
        names = [x.strip() for x in self.controls[key]['names'].get().split(',')]
        if len(names)<2 or any(not name for name in names) or len(set(names))!=len(names):
            raise InputError('Enter at least two unique names.')
        return names

    def _rebuild_bounds(self, controls, names, existing=None):
        view = controls['bounds_view']
        current = existing if existing is not None else {row[0]: (row[1], row[2]) for row in
                                                        (view.item(item, 'values') for item in view.get_children())}
        for item in view.get_children(): view.delete(item)
        for name in names:
            low, high = current.get(name, ('0', '100'))
            view.insert('', 'end', values=(name, low, high))

    def _edit_bound(self, key, event):
        view = self.controls[key]['bounds_view']
        item, column = view.identify_row(event.y), view.identify_column(event.x)
        if not item or column not in ('#2', '#3'):
            return
        values = list(view.item(item, 'values'))
        index = 1 if column == '#2' else 2
        entered = simpledialog.askstring('Investment limit', f'{values[0]} {"minimum" if index == 1 else "maximum"} weight (%)',
                                         initialvalue=values[index], parent=self.tabs[key])
        if entered is not None:
            values[index] = entered.strip()
            view.item(item, values=values)
            self._validate_ui_constraints(key)

    def _refresh_groups(self, key):
        c = self.controls[key]
        view = c['groups_view']
        for item in view.get_children(): view.delete(item)
        for group in c['groups']:
            view.insert('', 'end', values=(group['name'], ', '.join(group['investments']),
                                           group['maximum'], group['minimum']))
        self._validate_ui_constraints(key)

    def _group_dialog(self, key, edit=False):
        c = self.controls[key]
        selection = c['groups_view'].selection()
        if edit and not selection:
            return
        index = c['groups_view'].index(selection[0]) if edit else None
        old = c['groups'][index] if edit else {'name':'', 'investments':[], 'maximum':'100', 'minimum':''}
        dialog = tk.Toplevel(self.tabs[key]); dialog.title('Custom group constraint')
        dialog.transient(self.tabs[key].winfo_toplevel()); dialog.grab_set()
        name = self._entry(dialog, 'Group name', old['name'])
        ttk.Label(dialog, text='Select two or more investments').pack(anchor='w')
        choices = tk.Listbox(dialog, selectmode='multiple', exportselection=False, height=min(8,len(self._names(key))))
        for position, investment in enumerate(self._names(key)):
            choices.insert('end', investment)
            if investment in old['investments']: choices.selection_set(position)
        choices.pack(fill='x')
        maximum = self._entry(dialog, 'Maximum combined weight (%)', old['maximum'])
        minimum = self._entry(dialog, 'Minimum combined weight (%) — optional', old['minimum'])
        def save():
            group = {'name':name.get().strip(),
                     'investments':[choices.get(i) for i in choices.curselection()],
                     'maximum':maximum.get().strip(), 'minimum':minimum.get().strip()}
            if edit: c['groups'][index] = group
            else: c['groups'].append(group)
            dialog.destroy(); self._refresh_groups(key)
        row = ttk.Frame(dialog); row.pack(fill='x', pady=5)
        ttk.Button(row, text='Save Group', command=save).pack(side='left')
        ttk.Button(row, text='Cancel', command=dialog.destroy).pack(side='left', padx=5)

    def _remove_group(self, key):
        c = self.controls[key]
        selection = c['groups_view'].selection()
        if selection:
            c['groups'].pop(c['groups_view'].index(selection[0]))
            self._refresh_groups(key)

    def _constraint_settings(self, key):
        c = self.controls[key]
        rows = [c['bounds_view'].item(item, 'values') for item in c['bounds_view'].get_children()]
        names = self._names(key)
        if [row[0] for row in rows] != names:
            raise InputError('Limit table must contain every investment in order.')
        lower = {row[0]:_percent(row[1],row[0]+' minimum') for row in rows}
        upper = {row[0]:_percent(row[2],row[0]+' maximum') for row in rows}
        groups = [{'name':group['name'], 'investments':group['investments'],
                   'maximum':_percent(group['maximum'],group['name']+' maximum'),
                   'minimum':None if not group['minimum'] else _percent(group['minimum'],group['name']+' minimum')}
                  for group in c['groups']]
        gross = _percent(c['gross'].get(),'Gross cap')
        net_min = _percent(c['netmin'].get(),'Minimum net')
        net_max = _percent(c['netmax'].get(),'Maximum net')
        allow_cash = c['cash'].get()
        cash_yield = _percent(c['yield'].get(),'Cash yield') if allow_cash else None
        funding_rate = _percent(c['funding'].get(),'Funding rate') if allow_cash and c['funding'].get().strip() else None
        status = validate_portfolio_constraints(names, lower_bounds=lower, upper_bounds=upper,
            group_constraints=groups, allow_short=c['short'].get(), gross_cap=gross,
            net_min=net_min, net_max=net_max, allow_cash=allow_cash,
            funding_annual_rate=funding_rate)
        if not status.ok: raise InputError(status.message)
        settings = dict(mode='Advanced', execution_profile=self.mode,
            lower_bounds=lower, upper_bounds=upper, group_constraints=groups,
            allow_short=c['short'].get(), gross_cap=gross, net_min=net_min,
            net_max=net_max, allow_cash=allow_cash, cash_annual_yield=cash_yield,
            funding_annual_rate=funding_rate)
        if self._content(c['sectors']):
            assignments={}; caps={}
            for row in csv.reader(io.StringIO(self._content(c['sectors']))):
                if len(row)!=3: raise InputError('Sectors need Investment,Sector,maximum % rows.')
                assignments[row[0].strip()]=row[1].strip()
                caps[row[1].strip()]=_percent(row[2],row[1])
            settings.update(sector_assignments=assignments,sector_caps=caps)
        return settings

    def _validate_ui_constraints(self, key):
        try:
            self._constraint_settings(key)
            self.controls[key]['constraint_status'].configure(text='Valid constraints · allocation and groups are jointly feasible.')
        except (InputError, ValueError, KeyError) as exc:
            self.controls[key]['constraint_status'].configure(text='Invalid constraints: '+str(exc))

    def _set(self, widget, value):
        if isinstance(widget, tk.Text):
            widget.delete('1.0', tk.END); widget.insert('1.0', value)
        else:
            widget.delete(0, tk.END); widget.insert(0, value)

    def _content(self, widget):
        return widget.get('1.0', tk.END).strip()

    def _message(self, key, message):
        self._set(self.controls[key]['output'], message)

    def _add_name(self, key):
        c=self.controls[key]
        names=[x.strip() for x in c['names'].get().split(',') if x.strip()]
        prefix='Investment' if key=='markowitz' else 'Portfolio'
        i=len(names)+1
        new=f'{prefix} {i}'
        while new in names:
            i+=1; new=f'{prefix} {i}'
        names.append(new)
        self._set(c['names'], ','.join(names))
        lines=list(csv.reader(io.StringIO(self._content(c['returns']))))
        if lines:
            lines[0].append(new)
            for row in lines[1:]: row.append('')
            self._set(c['returns'], '\n'.join(','.join(row) for row in lines))
        if key=='markowitz':
            self._set(c['means'], self._content(c['means'])+'\n'+new+',')
            matrix=list(csv.reader(io.StringIO(self._content(c['covariance']))))
            if matrix:
                matrix[0].append(new)
                for row in matrix[1:]: row.append('')
                matrix.append([new]+['']*len(names))
                self._set(c['covariance'],'\n'.join(','.join(row) for row in matrix))
            self._rebuild_bounds(c,names)
            self._validate_ui_constraints(key)

    def _remove_name(self, key):
        c=self.controls[key]
        try: names=self._names(key)
        except InputError as exc: self._message(key,str(exc)); return
        if len(names)<=2: return
        names.pop(); self._set(c['names'], ','.join(names))
        lines=list(csv.reader(io.StringIO(self._content(c['returns']))))
        self._set(c['returns'], '\n'.join(','.join(row[:-1]) for row in lines))
        if key=='markowitz':
            self._set(c['means'], '\n'.join(self._content(c['means']).splitlines()[:-1]))
            matrix=list(csv.reader(io.StringIO(self._content(c['covariance']))))
            if matrix:
                self._set(c['covariance'],'\n'.join(','.join(row[:-1]) for row in matrix[:-1]))
            self._rebuild_bounds(c,names)
            for group in c['groups']:
                group['investments'] = [name for name in group['investments'] if name in names]
            self._refresh_groups(key)

    def _add_row(self, key):
        c=self.controls[key]
        lines=list(csv.reader(io.StringIO(self._content(c['returns']))))
        try:
            last=date.fromisoformat(lines[-1][0].strip())
            if c['frequency'].get()=='monthly':
                index=last.year*12+last.month
                year, m0=divmod(index,12); month=m0+1
                import calendar
                day=date(year,month,calendar.monthrange(year,month)[1])
            else: day=date(last.year+1,12,31)
            lines.append([day.isoformat()]+['']*(len(lines[0])-1))
            self._set(c['returns'],'\n'.join(','.join(row) for row in lines))
        except (IndexError, ValueError) as exc:
            self._message(key,'Correct the last YYYY-MM-DD date before adding a row.')

    def _remove_row(self, key):
        c=self.controls[key]
        lines=self._content(c['returns']).splitlines()
        if len(lines)>3: self._set(c['returns'],'\n'.join(lines[:-1]))

    def _import(self, key):
        c=self.controls[key]
        path=filedialog.askopenfilename(filetypes=[('Excel and CSV','*.xlsx *.csv')])
        if not path: return
        try:
            parsed=parse_portfolio_file(Path(path).read_bytes(),Path(path).name,
                scale=c['source_scale'].get(),purpose='investments' if key=='markowitz' else 'portfolios')
            c['pending']=parsed
            if parsed['kind']=='history':
                head='Date,'+','.join(parsed['names'])
                lines=[day+','+','.join(str(value) for value in row) for day,row in zip(parsed['dates'],parsed['original_values'])]
                normalized=[day+','+','.join(f'{value*100:.6g}%' for value in row)
                            for day,row in zip(parsed['dates'],parsed['returns'])]
                preview='Original data\n'+head+'\n'+'\n'.join(lines[:8])+\
                        '\n\nNormalized returns\n'+head+'\n'+'\n'.join(normalized[:8])
            else:
                preview=parsed['note']+'\n'+ '\n'.join(f'{name}: {parsed["expected_returns"][name]:.8g}; current {parsed["current_weights"][name]:.4g}' for name in parsed['names'])
            self._set(c['preview'],preview)
            c['choice'].set('Import Excel / CSV')
        except (InputError,OSError) as exc:
            self._message(key,str(exc))

    def _accept(self,key):
        c=self.controls[key]
        p=c.get('pending')
        if not p:
            self._message(key,'Choose a valid file and inspect its preview first.'); return
        self._set(c['names'],','.join(p['names']))
        if key=='markowitz':
            self._rebuild_bounds(c,p['names'])
            c['groups'] = []
            self._refresh_groups(key)
        if p['frequency']: c['frequency'].set(p['frequency'])
        if p['kind']=='history':
            head='Date,'+','.join(p['names'])
            lines=[day+','+','.join(repr(value*100) for value in row) for day,row in zip(p['dates'],p['returns'])]
            self._set(c['returns'],head+'\n'+'\n'.join(lines))
            if key=='markowitz': c['basis'].set('Historical investment returns')
        else:
            c['basis'].set('Expected returns and covariance')
            self._set(c['means'],'\n'.join(f'{name},{repr(p["expected_returns"][name]*100)}' for name in p['names']))
            self._set(c['covariance'],'Investment,'+','.join(p['names'])+'\n'+
                '\n'.join(name+','+','.join(repr(x) for x in row) for name,row in zip(p['names'],p['covariance'])))
            self._set(c['current'],'\n'.join(f'{name},{repr(p["current_weights"][name]*100)}' for name in p['names']))
        c['accepted']=p
        self._message(key,'Imported data accepted. Review and edit before calculation.')

    def _inputs(self,key):
        c=self.controls[key]
        names=self._names(key)
        frequency=c['frequency'].get()
        if key=='compare' or c['basis'].get()=='Historical investment returns':
            observed_names, dates, values=_read_csv(self._content(c['returns']))
            if observed_names!=names:
                raise InputError('Return columns must match the entered names in order.')
            return {'kind':'history','names':names,'dates':dates,'returns':values,'frequency':frequency,
                    'source':c.get('accepted',{}).get('source','Manual entry'), 'original_import':c.get('accepted')}
        means={}
        for row in csv.reader(io.StringIO(self._content(c['means']))):
            if len(row)!=2: raise InputError('Expected returns need Investment,Return (%) rows.')
            means[row[0].strip()]=_percent(row[1],row[0])
        if set(means)!=set(names): raise InputError('Expected return names must match investment names.')
        rows=list(csv.reader(io.StringIO(self._content(c['covariance']))))
        if not rows or rows[0][1:]!=names or len(rows)!=len(names)+1:
            raise InputError('Covariance row and column names must match investments.')
        sigma=[]
        for name,row in zip(names,rows[1:]):
            if row[0]!=name or len(row)!=len(names)+1: raise InputError('Covariance rows are incomplete or out of order.')
            try: sigma.append([float(value) for value in row[1:]])
            except ValueError as exc: raise InputError('Covariance values must be decimal return squared numbers.') from exc
        return {'kind':'estimates','names':names,'frequency':frequency,'expected_returns':means,'covariance':sigma,
                'source':c.get('accepted',{}).get('source','Manual entry'), 'original_import':c.get('accepted')}

    def _calculate(self,key):
        c=self.controls[key]
        try:
            inputs=self._inputs(key)
            rf=None if not c['rf'].get().strip() else _percent(c['rf'].get(),'Risk-free rate')
            if key=='compare':
                result=compare_return_histories(names=inputs['names'],dates=inputs['dates'],returns=inputs['returns'],
                    frequency=inputs['frequency'],risk_free_annual_rate=rf)
                if not result.ok: raise InputError(result.message)
                d=result.diagnostics
                lines=['Portfolio | Average | Cumulative | Variance | Volatility | Sharpe']
                for item in d['comparison']:
                    lines.append(f'{item["name"]} | {item["mean"]:.4%} | {item["cumulative"]:.4%} | {item["variance"]:.8g} | {item["volatility"]:.4%} | '+
                                 ('Unavailable' if item['sharpe'] is None else f'{item["sharpe"]:.4f}'))
                lines.extend(['','Covariance (decimal return squared):',str(d['covariance']),'Correlation:',str(d['correlation'])])
                lines.extend(result.warnings)
                data=portfolio_excel_bytes('Compare Portfolios',inputs,result)
            else:
                current=None
                if self._content(c['current']):
                    current={}
                    for row in csv.reader(io.StringIO(self._content(c['current']))):
                        if len(row)!=2: raise InputError('Current weights need Investment,Weight (%) rows.')
                        current[row[0].strip()]=_percent(row[1],row[0])
                kwargs={'names':inputs['names'],'frequency':inputs['frequency'],'current_weights':current,
                        'risk_free_annual_rate':rf,'mode':self.mode}
                if inputs['kind']=='history': kwargs.update(dates=inputs['dates'],returns=inputs['returns'])
                else: kwargs.update(expected_returns=inputs['expected_returns'],covariance=inputs['covariance'])
                analysis=analyze_optimization_inputs(**kwargs)
                if not analysis.ok: raise InputError(analysis.message)
                objective={'Minimum Variance':'minimum_variance','Maximum Sharpe Ratio':'maximum_estimated_sharpe',
                           'Target Return':'target_return_minimum_variance','Efficient Frontier':'minimum_variance'}[c['objective'].get()]
                settings=self._constraint_settings(key)
                options=dict(settings)
                if objective=='target_return_minimum_variance':
                    options['target_return']=_percent(c['target'].get(),'Target return')
                result=optimize_portfolio(analysis,objective=objective,**options)
                if not result.ok: raise InputError(result.message)
                frontier=efficient_frontier(analysis,points=10,**settings)
                if not frontier.ok: raise InputError(frontier.message)
                d=result.diagnostics
                lines=['Investment | Current | Optimized']
                for name in inputs['names']:
                    previous='—' if current is None else f'{current[name]:.4%}'
                    lines.append(f'{name} | {previous} | {d["weights"][name]:.4%}')
                lines.extend(['',f'Expected return: {d["expected_return"]:.4%}',f'Variance: {d["variance"]:.10g}',
                    f'Volatility: {d["volatility"]:.4%}',
                    'Sharpe: '+('Unavailable' if d['estimated_sharpe'] is None else f'{d["estimated_sharpe"]:.4f}'),
                    f'Solver: {d["solver_message"]}; feasible: {d["feasible"]}',
                    f'Constraint residuals: {d["constraint_residuals"]}',f'Covariance: {analysis.diagnostics["covariance"]}',
                    f'Frontier achieved points: {[(x["return"],x["volatility"]) for x in frontier.diagnostics["points"]]}',
                    'Formula: return = wᵀμ; variance = wᵀΣw; volatility = √variance.'])
                lines.extend(analysis.warnings);lines.extend(result.warnings)
                inputs['objective']=c['objective'].get();inputs['constraints']=options
                data=portfolio_excel_bytes('Markowitz Optimization',inputs,analysis,result,frontier)
            self._message(key,'\n'.join(lines))
            self._chart(key,result,frontier if key=='markowitz' else None)
            self.saved[key]=data
        except (InputError,ValueError,KeyError) as exc:
            self._message(key,str(exc))
            self.saved.pop(key,None)

    def _export(self,key):
        data=self.saved.get(key)
        if not data:
            self._message(key,'Calculate successfully before exporting.'); return
        path=filedialog.asksaveasfilename(defaultextension='.xlsx',filetypes=[('Excel workbook','*.xlsx')])
        if path: Path(path).write_bytes(data)

    def _reset(self,key):
        c=self.controls[key]
        c['pending']=c['accepted']=None
        c['choice'].set('Enter manually')
        if key=='markowitz': c['basis'].set('Historical investment returns')
        c['frequency'].set('monthly')
        names=['Investment 1','Investment 2'] if key=='markowitz' else ['Portfolio A','Portfolio B']
        self._set(c['names'],','.join(names))
        year=date.today().year
        self._set(c['returns'],'Date,'+','.join(names)+'\n'+ '\n'.join(f'{year}-{month:02d}-{day:02d},,' for month,day in [(1,31),(2,28),(3,31)]))
        for field in ('rf','preview','output'):
            self._set(c[field],'')
        if key=='markowitz':
            self._set(c['means'],'Investment 1,\nInvestment 2,')
            self._set(c['covariance'],'Investment,Investment 1,Investment 2\nInvestment 1,,\nInvestment 2,,')
            self._set(c['current'],'')
            self._set(c['target'],'')
            c['objective'].set('Minimum Variance')
            self._rebuild_bounds(c,names, {})
            c['groups'] = []
            self._refresh_groups(key)
            self._set(c['gross'],'100')
            self._set(c['netmin'],'100')
            self._set(c['netmax'],'100')
            self._set(c['yield'],'')
            self._set(c['funding'],'')
            self._set(c['sectors'],'')
            c['short'].set(False)
            c['cash'].set(False)
            self._validate_ui_constraints(key)
        self.saved.pop(key,None)
        axes, canvas = c['chart']
        axes.clear(); canvas.draw_idle()
