"""Primary S7 resizable Windows interface; workers never touch Tk widgets."""
from __future__ import annotations
import copy
import gc
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk,filedialog

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from financial_toolkit.workspace_s7 import Session,MODULES,fingerprint,presentation,chart_window
from financial_toolkit.forms_s7 import (WORKFLOWS,defaults,build,SIMPLE_TVM_OPTIONS,
    SIMPLE_BOND_OPTIONS,SIMPLE_TVM_EXAMPLE,SIMPLE_BOND_EXAMPLE,SIMPLE_PAYMENT_FREQUENCIES,
    simple_tvm_request,simple_bond_request,simple_appraisal_result,SIMPLE_APPRAISAL_OPTIONS)
from financial_toolkit.reporting_s7 import read_bytes,recalculate,make_record,csv_bundle,excel_bytes
from financial_toolkit.result import CalculationResult,Status
from apps.manual_returns_tk import ManualPortfolioTabs, blank as blank_manual_returns
from apps.portfolio_tk import PortfolioWeek11Tabs


class ToolkitApp:
    def __init__(self,root):
        self.root=root;self.session=Session();self.widgets={};self.outputs={};self.report_widgets={}
        self.simple_vars={};self.simple_outputs={}
        self.appraisal_widgets={};self.appraisal_outputs={};self.appraisal_results={}
        self.appraisal_values={'cash_flow':{'target':'npv','flows':['-100','60','60'],'rate':'10'}}
        self.manual_forms={kind:blank_manual_returns(kind) for kind in ('Investments','Portfolio')}
        self.manual_tabs=None
        self.simple_values={
            'tvm_regular':{'target':'fv',**SIMPLE_TVM_EXAMPLE},
            'bond_simple_fixed':{'target':'price',**SIMPLE_BOND_EXAMPLE['fixed']},
            'bond_simple_zero':{'target':'price',**SIMPLE_BOND_EXAMPLE['zero']}}
        root.title('Financial Analyst Toolkit');root.geometry('1280x900');root.minsize(800,600)
        self.style=ttk.Style(root);self.style.theme_use('clam')
        self.sidebar=ttk.Frame(root,padding=10);self.sidebar.pack(side='left',fill='y')
        ttk.Label(self.sidebar,text='Financial Analyst\nToolkit',font=('Segoe UI',16,'bold')).pack(pady=10)
        self.module=tk.StringVar(value=MODULES[0]);self.financial=tk.StringVar(value='Standard');self.profile=tk.StringVar(value='Standard');self.theme=tk.StringVar(value='Dark')
        self.advanced_controls=ttk.Frame(self.sidebar)
        for name,var,choices in [('Appearance',self.theme,('Dark','Light')),('Financial controls',self.financial,('Standard','Advanced')),('Execution profile',self.profile,('Standard','Advanced'))]:
            parent=self.sidebar if name=='Appearance' else self.advanced_controls
            ttk.Label(parent,text=name).pack(anchor='w')
            box=ttk.Combobox(parent,textvariable=var,values=choices,state='readonly',width=24);box.pack(fill='x',pady=3)
            box.bind('<<ComboboxSelected>>',lambda e:self.settings_changed())
        self.advanced_controls.pack(fill='x')
        self.mode_caption=ttk.Label(self.sidebar,text='Features and resource\nlimits are independent.')
        self.mode_caption.pack(pady=8)
        self.nav_buttons=[]
        for name in MODULES:
            control=ttk.Radiobutton(self.sidebar,text=name,variable=self.module,value=name,command=self.render)
            control.pack(anchor='w',pady=5);self.nav_buttons.append(control)
        ttk.Button(self.sidebar,text='Cancel current operation',command=self.session.cancel).pack(fill='x',pady=10)
        self.phase=ttk.Label(self.sidebar,text='Ready',wraplength=200);self.phase.pack(fill='x')
        self.progress=ttk.Progressbar(self.sidebar,mode='indeterminate');self.progress.pack(fill='x',pady=6)
        ttk.Label(self.sidebar,text='Session only. Save explicitly\nto preserve an analysis.').pack(pady=12)
        self.content=ttk.Frame(root);self.content.pack(side='left',fill='both',expand=True)
        self.closed=False;self.after_id=None
        self.apply_theme();self.render();self.after_id=self.root.after(100,self.poll)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def apply_theme(self):
        dark=self.theme.get()=='Dark';self.bg='#111827' if dark else '#f8fafc';self.fg='#e5e7eb' if dark else '#111827';self.card='#1f2937' if dark else '#ffffff'
        self.root.configure(bg=self.bg)
        self.style.configure('.',background=self.bg,foreground=self.fg,font=('Segoe UI',10))
        self.style.configure('TEntry',fieldbackground=self.card,foreground=self.fg)
        self.style.configure('TCombobox',fieldbackground=self.card,foreground=self.fg)
        self.style.map('TCombobox',fieldbackground=[('readonly',self.card)],foreground=[('readonly',self.fg)])
        self.style.configure('Treeview',fieldbackground=self.card,background=self.card,foreground=self.fg,rowheight=24)
        self.style.configure('TNotebook.Tab',padding=(12,8))

    def settings_changed(self):
        self.save_forms();self.apply_theme();self.render()

    def save_forms(self):
        for kind,widgets in self.widgets.items():
            self.session.values.setdefault(kind,defaults(kind)).update(self.raw(kind))

    def raw(self,kind):
        vals=defaults(kind)
        for key,(widget,field,var) in self.widgets.get(kind,{}).items():
            vals[key]=var.get() if field.kind=='bool' else widget.get('1.0','end-1c') if field.kind=='table' else widget.get()
        return vals

    def select(self,module,kind=None):
        self.module.set(module);self.render()
        if kind and kind in getattr(self,'tabs',{}):self.notebook.select(self.tabs[kind])

    def render(self):
        if self.manual_tabs is not None:
            self.manual_tabs.save()
            self.manual_tabs=None
        self.save_forms()
        self.save_appraisal()
        for key,fields in self.simple_vars.items():
            self.simple_values[key].update({name:var.get() for name,var in fields.items()})
        if self.module.get() in ('Time Value of Money','Cash Flow','Bond Analytics'):
            self.advanced_controls.pack_forget();self.mode_caption.pack_forget()
        else:
            self.advanced_controls.pack(before=self.nav_buttons[0],fill='x')
            self.mode_caption.pack(before=self.nav_buttons[0],pady=8)
        for child in self.content.winfo_children():child.destroy()
        gc.collect()  # Finalize detached Tk variables/canvases on their owning thread.
        self.widgets={};self.outputs={};self.report_widgets={}
        self.simple_vars={};self.simple_outputs={}
        self.appraisal_widgets={};self.appraisal_outputs={}
        self.tabs={}
        ttk.Label(self.content,text=self.module.get(),font=('Segoe UI',18,'bold')).pack(anchor='w',padx=12,pady=8)
        if self.module.get()=='Time Value of Money':
            self.render_simple_panel(self.content,'tvm_regular');return
        if self.module.get()=='Bond Analytics':
            book=ttk.Notebook(self.content);book.pack(fill='both',expand=True)
            for key,label in [('bond_simple_fixed','Fixed-Rate Bonds'),('bond_simple_zero','Zero-Coupon Bonds')]:
                tab=ttk.Frame(book);book.add(tab,text=label);self.render_simple_panel(tab,key)
            return
        if self.module.get()=='Cash Flow':
            self.render_appraisal_panel(self.content)
            return
        if self.module.get()=='Reporting and Visualization':self.render_reports();return
        if self.module.get()=='Portfolio Analytics and Optimization':
            self.portfolio_tabs=PortfolioWeek11Tabs(self.content,self.financial.get())
            self.notebook=self.portfolio_tabs.notebook;self.tabs.update(self.portfolio_tabs.tabs)
            return
        if self.module.get()=='Investment Appraisal':
            self.manual_tabs=ManualPortfolioTabs(self.content,self.manual_forms,self.financial.get(),kinds=('Investments',))
            self.notebook=self.manual_tabs.notebook;self.tabs.update(self.manual_tabs.tabs)
            return
        self.notebook=ttk.Notebook(self.content);self.notebook.pack(fill='both',expand=True);self.tabs={}
        for kind,(module,label,fields) in WORKFLOWS.items():
            if module!=self.module.get():continue
            tab=ttk.Frame(self.notebook);self.notebook.add(tab,text=label);self.tabs[kind]=tab
            canvas=tk.Canvas(tab,bg=self.bg,highlightthickness=0);scroll=ttk.Scrollbar(tab,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            frame=ttk.Frame(canvas,padding=12);item=canvas.create_window((0,0),window=frame,anchor='nw')
            frame.bind('<Configure>',lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>',lambda e,c=canvas,i=item:c.itemconfigure(i,width=e.width))
            if kind in ('bond_floating','bond_option') and self.financial.get()!='Advanced':
                ttk.Label(frame,text='Select Advanced financial controls for this model. Execution limits remain independent.').pack();continue
            widgets={};stored=self.session.values.setdefault(kind,defaults(kind))
            for field in fields:
                if field.advanced and self.financial.get()!='Advanced':continue
                strip=ttk.Frame(frame);strip.pack(fill='x',pady=3)
                ttk.Label(strip,text=field.label,wraplength=430).pack(anchor='w')
                value=stored.get(field.key,field.default);var=None
                if field.kind=='bool':var=tk.BooleanVar(value=bool(value));w=ttk.Checkbutton(strip,variable=var)
                elif field.kind=='choice':w=ttk.Combobox(strip,values=field.choices,state='readonly');w.set(value)
                elif field.kind=='table':w=tk.Text(strip,height=6,bg=self.card,fg=self.fg,insertbackground=self.fg,wrap='none');w.insert('1.0',str(value))
                else:w=ttk.Entry(strip);w.insert(0,str(value))
                w.pack(fill='x');widgets[field.key]=(w,field,var)
            self.widgets[kind]=widgets
            controls=ttk.Frame(frame);controls.pack(fill='x',pady=8)
            ttk.Button(controls,text='Calculate' if kind!='live_data' else 'Retrieve latest available',command=lambda k=kind:self.run_workflow(k)).pack(side='left')
            ttk.Button(controls,text='Clear / reset',command=lambda k=kind:self.reset(k)).pack(side='left',padx=8)
            out=ttk.Frame(frame);out.pack(fill='both',expand=True);self.outputs[kind]=out
            self.track(kind)
            if kind in self.session.current:self.show(self.session.current[kind],out,kind)

    def save_appraisal(self):
        widgets=self.appraisal_widgets.get('cash_flow')
        if not widgets:return
        values=self.appraisal_values['cash_flow']
        values['flows']=[entry.get() for entry in widgets['flows']]
        if widgets['rate'] is not None:values['rate']=widgets['rate'].get()

    def render_appraisal_panel(self,parent):
        key='cash_flow';stored=self.appraisal_values[key];kind=stored['target']
        canvas=tk.Canvas(parent,bg=self.bg,highlightthickness=0)
        scroll=ttk.Scrollbar(parent,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        frame=ttk.Frame(canvas,padding=12);item=canvas.create_window((0,0),window=frame,anchor='nw')
        frame.bind('<Configure>',lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')))
        canvas.bind('<Configure>',lambda e,c=canvas,i=item:c.itemconfigure(i,width=e.width))
        ttk.Label(frame,text='Cash Flow 0 occurs today; later flows occur at the end of equally spaced periods.',
                  wraplength=850).pack(anchor='w',pady=5)
        ttk.Label(frame,text='Solve For').pack(anchor='w',pady=(5,0))
        names={value:label for label,value in SIMPLE_APPRAISAL_OPTIONS.items()}
        choice=ttk.Combobox(frame,values=list(SIMPLE_APPRAISAL_OPTIONS),state='readonly')
        choice.set(names[kind]);choice.pack(fill='x',pady=3)
        choice.bind('<<ComboboxSelected>>',lambda e:self.change_appraisal_target(
            SIMPLE_APPRAISAL_OPTIONS[choice.get()]))
        flows=[]
        for index,value in enumerate(stored['flows']):
            label='Initial investment / Cash Flow 0' if index==0 else f'Cash Flow {index}'
            ttk.Label(frame,text=label).pack(anchor='w',pady=(5,0))
            entry=ttk.Entry(frame);entry.insert(0,value);entry.pack(fill='x');flows.append(entry)
        row=ttk.Frame(frame);row.pack(fill='x',pady=6)
        ttk.Button(row,text='Add period',command=lambda:self.change_appraisal_periods(1)).pack(side='left')
        ttk.Button(row,text='Remove last period',command=lambda:self.change_appraisal_periods(-1),
                   state='normal' if len(flows)>2 else 'disabled').pack(side='left',padx=8)
        rate=None
        if kind=='npv':
            ttk.Label(frame,text='Discount rate (% per period)').pack(anchor='w',pady=(5,0))
            rate=ttk.Entry(frame);rate.insert(0,stored['rate']);rate.pack(fill='x')
        self.appraisal_widgets[key]={'flows':flows,'rate':rate}
        row=ttk.Frame(frame);row.pack(fill='x',pady=8)
        ttk.Button(row,text='Calculate',command=self.run_appraisal).pack(side='left')
        ttk.Button(row,text='Reset',command=self.reset_appraisal).pack(side='left',padx=8)
        output=ttk.Frame(frame);output.pack(fill='both',expand=True)
        self.appraisal_outputs[key]=output
        saved=self.appraisal_results.get(key)
        if saved and saved[0]==self.appraisal_signature():
            self.show_appraisal(output,saved[1],saved[2],kind)

    def appraisal_signature(self):
        widgets=self.appraisal_widgets['cash_flow']
        return (self.appraisal_values['cash_flow']['target'],
                tuple(entry.get() for entry in widgets['flows']),
                widgets['rate'].get() if widgets['rate'] is not None else None)

    def change_appraisal_target(self,target):
        self.save_appraisal()
        self.appraisal_values['cash_flow']['target']=target
        self.appraisal_results.pop('cash_flow',None)
        self.appraisal_widgets={}
        self.render()

    def change_appraisal_periods(self,change):
        self.save_appraisal()
        flows=self.appraisal_values['cash_flow']['flows']
        if change>0:flows.append('0')
        elif len(flows)>2:flows.pop()
        self.appraisal_results.pop('cash_flow',None)
        self.appraisal_widgets={}
        self.render()

    def run_appraisal(self):
        self.save_appraisal()
        stored=self.appraisal_values['cash_flow'];kind=stored['target']
        signature=self.appraisal_signature()
        output=self.appraisal_outputs['cash_flow']
        for child in output.winfo_children():child.destroy()
        try:
            result,view=simple_appraisal_result(kind,stored['flows'],
                                                 stored['rate'] if kind=='npv' else None)
            self.appraisal_results['cash_flow']=(signature,result,view)
            self.show_appraisal(output,result,view,kind)
        except ValueError as exc:
            ttk.Label(output,text='INVALID: '+str(exc),wraplength=850).pack(anchor='w')

    def show_appraisal(self,frame,result,view,kind):
        if not result.ok:
            ttk.Label(frame,text=f'{result.status}: {result.message}',wraplength=850).pack(anchor='w',pady=5)
            return
        summary=(f'NPV: {result.value:,.6f}' if kind=='npv' else
                 'IRR: '+', '.join(f'{root*100:.6f}%' for root in result.value)+' per period')
        ttk.Label(frame,text=summary,font=('Segoe UI',13,'bold')).pack(anchor='w',pady=6)
        for line in (view['formula'],view['substitution'],*view['steps'],view['interpretation'],*result.warnings):
            ttk.Label(frame,text=line,wraplength=850).pack(anchor='w',pady=3)

    def reset_appraisal(self):
        self.save_appraisal()
        self.appraisal_values['cash_flow']={'target':'npv','flows':['-100','60','60'],'rate':'10'}
        self.appraisal_results.pop('cash_flow',None)
        self.appraisal_widgets={}
        self.render()

    def track(self,kind):
        vals=self.raw(kind)
        self.session.changed(kind,fingerprint(kind,{'form':vals,'profile':self.profile.get(),'financial':self.financial.get()}))
        self.session.values.setdefault(kind,defaults(kind)).update(vals)

    def run_workflow(self,kind):
        if self.session.job:return
        gc.collect()
        self.track(kind);self.session.current.pop(kind,None);self.session.current.pop('export:'+kind,None)
        for child in self.outputs[kind].winfo_children():child.destroy()
        try:
            calculation,inputs=build(kind,self.raw(kind),self.profile.get(),self.financial.get())
            if kind=='live_data':
                from financial_toolkit.providers_s5 import fetch_data
                def task(cancelled):
                    result=fetch_data(**inputs,cancelled=cancelled)
                    return {'kind':'market_data','inputs':{'rows':result.diagnostics.get('observations',[]),'mode':inputs['mode']},'result':result}
                self.session.start(kind,kind,inputs,task)
            else:self.session.start(kind,calculation,inputs)
        except (ValueError,TypeError) as exc:ttk.Label(self.outputs[kind],text='INVALID: '+str(exc),wraplength=800).pack(anchor='w')

    def reset(self,kind):
        self.session.clear(kind);self.session.values[kind]=defaults(kind);self.widgets.pop(kind,None);self.render()

    def render_simple_panel(self,parent,key):
        canvas=tk.Canvas(parent,bg=self.bg,highlightthickness=0)
        scroll=ttk.Scrollbar(parent,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        frame=ttk.Frame(canvas,padding=12);item=canvas.create_window((0,0),window=frame,anchor='nw')
        frame.bind('<Configure>',lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')))
        canvas.bind('<Configure>',lambda e,c=canvas,i=item:c.itemconfigure(i,width=e.width))
        is_tvm=key=='tvm_regular'
        kind='fixed' if key.endswith('fixed') else 'zero'
        options=SIMPLE_TVM_OPTIONS if is_tvm else SIMPLE_BOND_OPTIONS[kind]
        names={value:label for label,value in options.items()}
        stored=self.simple_values[key]
        ttk.Label(frame,text='Regular end-of-period payments' if is_tvm else
                  'Full price at a coupon date; 100% face redemption at maturity',
                  wraplength=850).pack(anchor='w',pady=5)
        ttk.Label(frame,text='Solve For').pack(anchor='w')
        target=tk.StringVar(value=names[stored['target']])
        chooser=ttk.Combobox(frame,textvariable=target,values=list(options),state='readonly')
        chooser.pack(fill='x',pady=3)
        chooser.bind('<<ComboboxSelected>>',lambda e,k=key,o=options:
                     self.change_simple_target(k,o[chooser.get()]))
        variables={}
        if is_tvm:
            labels={'pv':'Present Value (PV)','fv':'Future Value (FV)',
                'pmt':'Payment each period (PMT)','annual_rate':'Interest rate (nominal annual, %)',
                'years':'Years to maturity (e.g., 2 years)'}
            fields=list(labels)
            unknown='annual_rate' if stored['target']=='rate' else stored['target']
        else:
            labels={'face':'Face Value','coupon_rate':'Coupon Rate (nominal annual, %)',
                'annual_yield':'Yield to Maturity (nominal annual, %)',
                'years':'Years to Maturity','frequency':'Coupon Payments per Year',
                'price':'Bond Price (full price at a coupon date)'}
            fields=['face']+(['coupon_rate'] if kind=='fixed' else [])+['annual_yield','years']
            if kind=='fixed':fields.append('frequency')
            fields.append('price');unknown=stored['target']
        for name in fields:
            if name==unknown or (is_tvm and name=='years' and stored['target']=='periods'):continue
            ttk.Label(frame,text=labels[name]).pack(anchor='w',pady=(5,0))
            var=tk.StringVar(value=stored[name]);variables[name]=var
            ttk.Entry(frame,textvariable=var).pack(fill='x')
        if is_tvm:
            ttk.Label(frame,text='Payment frequency').pack(anchor='w',pady=(5,0))
            frequency=tk.StringVar(value=stored['payment_frequency'])
            variables['payment_frequency']=frequency
            frequency_buttons=ttk.Frame(frame);frequency_buttons.pack(fill='x')
            for label,value in SIMPLE_PAYMENT_FREQUENCIES.items():
                ttk.Radiobutton(frequency_buttons,text=label,variable=frequency,
                                value=value).pack(side='left',padx=(0,10))
        self.simple_vars[key]=variables
        if is_tvm:
            ttk.Label(frame,text='Outflows are negative; inflows are positive. The rate is nominal annual; years × payments per year gives the payment periods.',
                      wraplength=850).pack(anchor='w',pady=5)
        controls=ttk.Frame(frame);controls.pack(fill='x',pady=8)
        ttk.Button(controls,text='Calculate',command=lambda k=key:self.run_simple(k)).pack(side='left')
        ttk.Button(controls,text='Reset',command=lambda k=key:self.reset_simple(k)).pack(side='left',padx=8)
        output=ttk.Frame(frame);output.pack(fill='both',expand=True);self.simple_outputs[key]=output
        self.track_simple(key)
        if key in self.session.current:self.show(self.session.current[key],output,key)

    def change_simple_target(self,key,target):
        self.simple_values[key]['target']=target
        self.render()

    def track_simple(self,key):
        values={name:var.get() for name,var in self.simple_vars[key].items()}
        self.simple_values[key].update(values)
        self.session.changed(key,fingerprint(key,{'target':self.simple_values[key]['target'],
            'values':values,'profile':'Standard'}))

    def run_simple(self,key):
        if self.session.job:return
        self.track_simple(key)
        values=self.simple_values[key];target=values['target']
        output=self.simple_outputs[key]
        for child in output.winfo_children():child.destroy()
        try:
            if key=='tvm_regular':
                calculation,inputs=simple_tvm_request(target,values,'Standard')
            else:
                calculation,inputs=simple_bond_request(
                    'fixed' if key.endswith('fixed') else 'zero',target,values,'Standard')
            self.session.start(key,calculation,inputs)
        except (ValueError,TypeError) as exc:
            ttk.Label(output,text='INVALID: '+str(exc),wraplength=850).pack(anchor='w')

    def reset_simple(self,key):
        self.session.clear(key)
        self.simple_values[key]={'target':'fv',**SIMPLE_TVM_EXAMPLE} if key=='tvm_regular' else {
            'target':'price',**SIMPLE_BOND_EXAMPLE['fixed' if key.endswith('fixed') else 'zero']}
        self.simple_vars.pop(key,None);self.render()

    def poll(self):
        if self.closed or not self.root.winfo_exists():return
        for key in self.appraisal_widgets:
            saved=self.appraisal_results.get(key)
            if saved and saved[0]!=self.appraisal_signature():
                self.appraisal_results.pop(key,None)
                output=self.appraisal_outputs[key]
                for child in output.winfo_children():child.destroy()
                ttk.Label(output,text='Inputs changed — calculate again.').pack(anchor='w')
        for key in self.simple_vars:
            before=key in self.session.current;self.track_simple(key)
            if before and key not in self.session.current:
                for child in self.simple_outputs[key].winfo_children():child.destroy()
        for kind in self.widgets:
            before=kind in self.session.current;self.track(kind)
            if before and kind not in self.session.current:
                for child in self.outputs[kind].winfo_children():child.destroy()
        changed=self.session.poll();self.phase.configure(text=self.session.phase)
        if self.session.job:self.progress.start(15)
        else:self.progress.stop()
        if changed:
            if self.module.get()=='Reporting and Visualization':self.render()
            else:
                for kind,frame in self.outputs.items():
                    for child in frame.winfo_children():child.destroy()
                    if kind in self.session.current:self.show(self.session.current[kind],frame,kind)
                for key,frame in self.simple_outputs.items():
                    for child in frame.winfo_children():child.destroy()
                    if key in self.session.current:self.show(self.session.current[key],frame,key)
        self.after_id=self.root.after(100,self.poll)

    def show(self,payload,frame,key):
        result=payload['result'];view=presentation(payload['kind'],payload['inputs'],result)
        ttk.Label(frame,text=(view['summary']+' '+view['unit']) if result.ok and result.value is not None else str(result.status)+': '+result.message,
            font=('Segoe UI',13,'bold'),wraplength=900).pack(anchor='w',pady=8)
        for message in [view['interpretation'],*view['warnings']]:ttk.Label(frame,text=message,wraplength=850).pack(anchor='w',pady=3)
        simple=key=='tvm_regular' or key.startswith('bond_simple_')
        if simple and result.ok:
            ttk.Label(frame,text=view['formula'],wraplength=850).pack(anchor='w',pady=4)
            if key.startswith('bond_simple_'):
                ttk.Label(frame,text=f"Coupon each period: {result.diagnostics['coupon_per_period']:,.2f}").pack(anchor='w')
        for name,rows in view['tables'].items():
            if simple and name=='Summary metrics':continue
            self.table(frame,name,rows)
        if view['charts']:self.charts(frame,view['charts'])
        details=tk.Text(frame,height=8,bg=self.card,fg=self.fg,wrap='word');details.pack(fill='x',pady=6)
        details.insert('1.0',view['formula']+'\n'+json.dumps({'inputs':view['inputs'],'assumptions':view['assumptions'],'diagnostics':view['diagnostics']},ensure_ascii=False,indent=2));details.configure(state='disabled')
        if 'differences' in payload:ttk.Label(frame,text=json.dumps(payload['differences']),wraplength=850).pack(anchor='w')
        if result.ok:
            buttons=ttk.Frame(frame);buttons.pack(fill='x')
            ttk.Button(buttons,text='Prepare Excel and CSV reports',command=lambda:self.prepare(key,payload)).pack(side='left')
            exports=self.session.current.get('export:'+key)
            if exports:
                ttk.Button(buttons,text='Save Excel',command=lambda:self.save(exports['xlsx'],'.xlsx')).pack(side='left',padx=6)
                ttk.Button(buttons,text='Save CSV bundle',command=lambda:self.save(exports['zip'],'.zip')).pack(side='left')
        self.report_widgets[key]={'view':view,'details':details}

    def table(self,frame,name,rows):
        ttk.Label(frame,text=name.replace('_',' ').title()).pack(anchor='w')
        cols=list(dict.fromkeys(k for row in rows for k in row))
        tree=ttk.Treeview(frame,columns=cols,show='headings',height=min(8,len(rows)));tree.pack(fill='x')
        for col in cols:tree.heading(col,text=col.replace('_',' '));tree.column(col,width=130,minwidth=70)
        bar=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview);bar.pack(fill='x');tree.configure(xscrollcommand=bar.set)
        page=[0];size=200 if self.profile.get()=='Standard' else 500
        label=ttk.Label(frame);label.pack(anchor='w')
        def display(delta=0):
            page[0]=max(0,min(page[0]+delta,(len(rows)-1)//size))
            tree.delete(*tree.get_children())
            for row in rows[page[0]*size:(page[0]+1)*size]:tree.insert('','end',values=[json.dumps(row.get(c),ensure_ascii=False) if isinstance(row.get(c),(dict,list)) else row.get(c) for c in cols])
            label.configure(text=f'Page {page[0]+1} of {(len(rows)-1)//size+1}; {len(rows)} total rows')
        nav=ttk.Frame(frame);nav.pack(anchor='w');ttk.Button(nav,text='Previous page',command=lambda:display(-1)).pack(side='left');ttk.Button(nav,text='Next page',command=lambda:display(1)).pack(side='left');display()

    def charts(self,frame,charts):
        selector=ttk.Combobox(frame,values=[c['title'] for c in charts],state='readonly');selector.current(0);selector.pack(fill='x')
        controls=ttk.Frame(frame);controls.pack(fill='x')
        ttk.Label(controls,text='Start row').pack(side='left');start=ttk.Entry(controls,width=8);start.insert(0,'0');start.pack(side='left')
        ttk.Label(controls,text='Row count').pack(side='left');count=ttk.Entry(controls,width=8);count.insert(0,str(min(1000,len(charts[0]['x']))));count.pack(side='left')
        holder=ttk.Frame(frame);holder.pack(fill='both',expand=True);message=ttk.Label(frame,wraplength=850);message.pack(anchor='w')
        def draw():
            for child in holder.winfo_children():child.destroy()
            try:
                c=chart_window(charts[selector.current()],self.profile.get(),int(start.get()),int(count.get()))
                from matplotlib.figure import Figure
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg,NavigationToolbar2Tk
                fig=Figure(figsize=(8,3),dpi=90,facecolor=self.bg);ax=fig.add_subplot(111);ax.set_facecolor(self.card)
                kind=c.get('kind','line')
                if kind=='heatmap':
                    import numpy as np
                    matrix=np.array([[float('nan') if v is None else v for v in row] for row in c['series'].values()])
                    ax.imshow(matrix,vmin=-1,vmax=1,cmap='RdBu_r',aspect='auto');ax.set_xticks(range(len(c['x'])),c['x']);ax.set_yticks(range(len(c['series'])),list(c['series']))
                else:
                    for label,values in c['series'].items():
                        if kind=='bar':ax.bar(c['x'],values,label=label)
                        elif kind=='scatter':ax.scatter(c['x'],values,label=label)
                        else:ax.plot(c['x'],values,label=label)
                ax.set_title(c['title'],color=self.fg);ax.set_xlabel(c['x_label'],color=self.fg);ax.set_ylabel(c['y_label'],color=self.fg);ax.tick_params(colors=self.fg)
                if kind!='heatmap':ax.legend()
                fig.autofmt_xdate();fig.tight_layout()
                chart=FigureCanvasTkAgg(fig,master=holder);chart.draw();chart.get_tk_widget().pack(fill='both',expand=True);NavigationToolbar2Tk(chart,holder).update();message.configure(text='')
            except (ValueError,TypeError) as exc:message.configure(text=str(exc))
        selector.bind('<<ComboboxSelected>>',lambda e:draw());ttk.Button(controls,text='Show selected window',command=draw).pack(side='left',padx=8);draw()

    def prepare(self,key,payload):
        if self.session.job:return
        gc.collect()
        source=copy.deepcopy(payload)
        def task(cancelled):
            record=make_record(source['kind'],source['inputs'],source['result'])
            return {'kind':'export','inputs':{},'result':CalculationResult(Status.VALID,None,'reports'),
                'zip':csv_bundle(record,cancelled),'xlsx':excel_bytes(record,cancelled),'record':record}
        self.session.start('export:'+key,'export',{'mode':source['inputs'].get('mode','Standard')},task)

    def save(self,data,suffix):
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension=suffix,confirmoverwrite=True)
        if path:
            try:Path(path).write_bytes(data)
            except OSError:self.phase.configure(text='Could not save the selected file.')

    def render_reports(self):
        outer=ttk.Frame(self.content);outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,bg=self.bg,highlightthickness=0);scroll=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        frame=ttk.Frame(canvas,padding=12);item=canvas.create_window((0,0),window=frame,anchor='nw')
        frame.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        ttk.Button(frame,text='Open typed file for review',command=self.open_file).pack(anchor='w')
        preview=self.session.current.get('__preview__')
        if preview:
            record=preview['record'];ttk.Label(frame,text='Review only: '+record['calculation_type']+'; '+preview['info']['source_schema']+'; profile '+record['inputs'].get('mode','Standard')).pack(anchor='w')
            detail=tk.Text(frame,height=8,bg=self.card,fg=self.fg);detail.pack(fill='x');detail.insert('1.0',json.dumps({'inputs':record['inputs'],'units':record['input_metadata'],'sources':record['sources']},ensure_ascii=False,indent=2));detail.configure(state='disabled')
            ttk.Button(frame,text='Recalculate reviewed inputs',command=self.recalculate_import).pack(anchor='w')
        keys=[k for k,p in self.session.current.items() if p['kind'] in WORKFLOWS]
        if not keys:ttk.Label(frame,text='Calculate a workflow or review and recalculate a saved file.').pack(anchor='w');return
        select=ttk.Combobox(frame,values=keys,state='readonly');select.current(0);select.pack(fill='x')
        output=ttk.Frame(frame);output.pack(fill='both',expand=True)
        def show():
            for child in output.winfo_children():child.destroy()
            key=select.get();self.show(self.session.current[key],output,key)
        select.bind('<<ComboboxSelected>>',lambda e:show());show()

    def open_file(self):
        if self.session.job:return
        path=filedialog.askopenfilename(parent=self.root,filetypes=[('Typed analysis','*.xlsx *.zip *.csv')])
        if not path:return
        profile=self.profile.get()
        def task(cancelled):
            if Path(path).stat().st_size>(16 if profile=='Standard' else 32)*1024**2:raise ValueError('File exceeds profile byte limit.')
            record,info=read_bytes(Path(path).read_bytes(),Path(path).suffix.lower(),profile,cancelled)
            return {'kind':'file_preview','inputs':{},'result':CalculationResult(Status.VALID,None,'preview only'),'record':record,'info':info}
        self.session.start('__preview__','file_preview',{'mode':profile},task)

    def recalculate_import(self):
        if self.session.job:return
        record=copy.deepcopy(self.session.current['__preview__']['record'])
        if record['inputs'].get('mode','Standard')!=self.profile.get():self.phase.configure(text='Select the file’s declared execution profile first.');return
        def task(cancelled):
            result,differences=recalculate(record,cancelled)
            return {'kind':record['calculation_type'],'inputs':record['inputs'],'result':result,'differences':differences}
        self.session.start('__imported__',record['calculation_type'],record['inputs'],task)

    def close(self):
        self.closed=True;self.session.cancel()
        if self.after_id is not None:
            try:self.root.after_cancel(self.after_id)
            except tk.TclError:pass
        self.root.destroy();gc.collect()


def main():
    root=tk.Tk();ToolkitApp(root);root.mainloop()


if __name__=='__main__':main()
