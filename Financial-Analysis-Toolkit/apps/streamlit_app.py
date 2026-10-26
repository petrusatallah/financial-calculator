"""Primary S7 six-module Streamlit interface; no framework-side finance."""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

import pandas as pd
import streamlit as st
from financial_toolkit.workspace_s7 import Session,MODULES,fingerprint,presentation,chart_window
from financial_toolkit.forms_s7 import (WORKFLOWS,defaults,build,SIMPLE_TVM_OPTIONS,
    SIMPLE_BOND_OPTIONS,SIMPLE_TVM_EXAMPLE,SIMPLE_BOND_EXAMPLE,SIMPLE_PAYMENT_FREQUENCIES,
    simple_tvm_request,simple_bond_request,simple_appraisal_result,SIMPLE_APPRAISAL_OPTIONS)
from financial_toolkit.reporting_s7 import read_bytes,recalculate,make_record,csv_bundle,excel_bytes
from financial_toolkit.result import CalculationResult,Status
from financial_toolkit.validation import InputError
from apps.manual_returns_streamlit import render as render_manual_returns
from apps.portfolio_streamlit import render_markowitz, render_compare


def run():
    st.set_page_config(page_title='Financial Analyst Toolkit',layout='wide')
    if 's7_workspace' not in st.session_state:st.session_state.s7_workspace=Session()
    session=st.session_state.s7_workspace
    session.poll()
    theme=st.sidebar.selectbox('Appearance',['Dark','Light'],key='s7_theme')
    bg,fg,card=('#111827','#e5e7eb','#1f2937') if theme=='Dark' else ('#f8fafc','#111827','#ffffff')
    st.markdown(f'''<style>:root,.stApp{{--background-color:{bg};--secondary-background-color:{card};--text-color:{fg};color-scheme:{theme.lower()};}}
    .stApp,[data-testid="stSidebar"]{{background:{bg};color:{fg};}}
    [data-testid="stExpander"],[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{{background:{card};color:{fg};}}
    input,textarea{{background:{card}!important;color:{fg}!important;}} h1,h2,h3,p,label{{color:{fg};}}</style>''',unsafe_allow_html=True)
    st.sidebar.title('Financial Analyst Toolkit')
    module=st.sidebar.radio('Module',MODULES,key='s7_module')
    simple_module=module in ('Time Value of Money','Cash Flow','Bond Analytics')
    if simple_module:
        financial=profile='Standard'
    else:
        financial=st.sidebar.selectbox('Financial controls',['Standard','Advanced'],key='s7_financial')
        profile=st.sidebar.selectbox('Execution profile',['Standard','Advanced'],key='s7_profile')
        st.sidebar.caption('Financial controls select features. Execution profile sets independent resource limits.')
    st.title(module)
    st.caption('Results remain in this session until it closes.' if simple_module else
               'Manual return entries remain in this session until it closes.' if module in ('Investment Appraisal','Portfolio Analytics and Optimization') else
               'Session only. Save an Excel workbook or CSV bundle explicitly to keep an analysis.')
    if st.sidebar.button('Cancel current operation',key='s7_cancel',disabled=session.job is None):session.cancel()
    st.sidebar.button('Refresh operation',key='s7_refresh')
    st.sidebar.caption(session.phase)
    if session.phase.startswith(('INVALID:','INCOMPLETE:')) and session.job is None:st.error(session.phase)
    if module=='Time Value of Money':
        render_simple_tvm(session,profile,theme)
    elif module=='Bond Analytics':
        render_simple_bonds(session,profile,theme)
    elif module=='Cash Flow':
        render_cash_flow()
    elif module=='Reporting and Visualization':
        render_reports(session,profile,theme)
    elif module=='Investment Appraisal':
        investment_tab, = st.tabs(['Investments'])
        with investment_tab:render_manual_returns('Investments',financial)
    elif module=='Portfolio Analytics and Optimization':
        markowitz_tab, compare_tab = st.tabs(['Markowitz Optimization','Compare Portfolios'])
        with markowitz_tab:render_markowitz(financial)
        with compare_tab:render_compare(financial)
    else:
        kinds=[k for k,v in WORKFLOWS.items() if v[0]==module]
        tabs=st.tabs([WORKFLOWS[k][1] for k in kinds])
        for kind,tab in zip(kinds,tabs):
            with tab:render_form(session,kind,profile,financial,theme)
    @st.fragment(run_every=.4)
    def progress():
        changed=session.poll()
        if session.job:st.info(session.phase+'…')
        elif changed:st.rerun()
    progress()


def _simple_result(session,key,profile,theme):
    payload=session.current.get(key)
    if not payload:return
    if payload['result'].ok:
        st.subheader('Summary, formula and explanation')
        if key!='tvm_regular':
            st.write('Bond price is the present value of each coupon plus 100% of face value at maturity. Yield is nominal annual, compounded at the coupon frequency.')
            st.caption(f"Coupon each period: {payload['result'].diagnostics['coupon_per_period']:,.2f}")
    show(payload,profile,theme,key)


def render_simple_tvm(session,profile,theme):
    st.subheader('Regular payments')
    st.caption('Signed cash flows: enter an outflow as negative and an inflow as positive. Payments occur at the end of each period.')
    label=st.selectbox('Solve For',list(SIMPLE_TVM_OPTIONS),key='simple_tvm_target')
    target=SIMPLE_TVM_OPTIONS[label]
    labels={'pv':'Present Value (PV)','fv':'Future Value (FV)',
            'pmt':'Payment each period (PMT)','annual_rate':'Interest rate (nominal annual, %)',
            'years':'Years to maturity (e.g., 2 years)'}
    unknown='annual_rate' if target=='rate' else target
    values={}
    for name in ('pv','fv','pmt','annual_rate','years'):
        if name==unknown or (name=='years' and target=='periods'):continue
        values[name]=st.text_input(labels[name],value=SIMPLE_TVM_EXAMPLE[name],
                                   key='simple_tvm_'+name)
    frequency=st.segmented_control('Payment frequency',list(SIMPLE_PAYMENT_FREQUENCIES),
        default='Annually (1)',key='simple_tvm_payment_frequency')
    values['payment_frequency']=SIMPLE_PAYMENT_FREQUENCIES.get(frequency,'')
    st.caption('The entered interest rate is nominal annual; years × payments per year gives the number of payment periods.')
    session.changed('tvm_regular',fingerprint('simple_tvm',{'target':target,'values':values,'profile':profile}))
    left,right=st.columns(2)
    if left.button('Calculate',key='simple_tvm_calculate',disabled=session.job is not None):
        try:
            calculation,inputs=simple_tvm_request(target,values,profile)
            session.start('tvm_regular',calculation,inputs)
            st.rerun()
        except (ValueError,TypeError) as exc:st.error(str(exc))
    def reset():
        session.clear('tvm_regular')
        for key in list(st.session_state):
            if key.startswith('simple_tvm_'):del st.session_state[key]
    right.button('Reset',key='simple_tvm_reset',on_click=reset)
    _simple_result(session,'tvm_regular',profile,theme)


def render_simple_bonds(session,profile,theme):
    st.caption('Prices are full prices at a coupon date. Redemption is 100% of face value at maturity; accrued interest is not modelled.')
    for bond_type,tab in zip(('fixed','zero'),st.tabs(['Fixed-Rate Bonds','Zero-Coupon Bonds'])):
        with tab:
            label=st.selectbox('Solve For',list(SIMPLE_BOND_OPTIONS[bond_type]),
                               key=f'simple_bond_{bond_type}_target')
            target=SIMPLE_BOND_OPTIONS[bond_type][label]
            labels={'face':'Face Value','coupon_rate':'Coupon Rate (nominal annual, %)',
                    'annual_yield':'Yield to Maturity (nominal annual, %)',
                    'years':'Years to Maturity','frequency':'Coupon Payments per Year',
                    'price':'Bond Price (full price at a coupon date)'}
            fields=['face']
            if bond_type=='fixed':fields.append('coupon_rate')
            fields+=['annual_yield','years']
            if bond_type=='fixed':fields.append('frequency')
            fields.append('price')
            values={}
            for name in fields:
                if name==target:continue
                values[name]=st.text_input(labels[name],value=SIMPLE_BOND_EXAMPLE[bond_type][name],
                    key=f'simple_bond_{bond_type}_{name}')
            key='bond_simple_'+bond_type
            session.changed(key,fingerprint(key,{'target':target,'values':values,'profile':profile}))
            left,right=st.columns(2)
            if left.button('Calculate',key=key+'_calculate',disabled=session.job is not None):
                try:
                    calculation,inputs=simple_bond_request(bond_type,target,values,profile)
                    session.start(key,calculation,inputs)
                    st.rerun()
                except (ValueError,TypeError) as exc:st.error(str(exc))
            def reset(which=bond_type,session_key=key):
                session.clear(session_key)
                for name in list(st.session_state):
                    if name.startswith('simple_bond_'+which+'_'):del st.session_state[name]
            right.button('Reset',key=key+'_reset',on_click=reset)
            _simple_result(session,key,profile,theme)


def render_cash_flow():
    st.caption('Cash Flow 0 occurs today. Later cash flows occur at the end of equally spaced periods; all rates are per same period.')
    prefix='simple_cash_flow_'
    choice=st.selectbox('Solve For',list(SIMPLE_APPRAISAL_OPTIONS),
                        key=prefix+'target')
    kind=SIMPLE_APPRAISAL_OPTIONS[choice]
    count_key=prefix+'count'
    if count_key not in st.session_state:st.session_state[count_key]=2
    count=st.session_state[count_key]
    flows=[st.text_input('Initial investment / Cash Flow 0',value='-100',key=prefix+'flow_0')]
    for index in range(1,count+1):
        flows.append(st.text_input(f'Cash Flow {index}',value='60' if index<=2 else '0',
                                   key=prefix+f'flow_{index}'))
    left,right=st.columns(2)
    if left.button('Add period',key=prefix+'add'):
        st.session_state[count_key]=count+1
        st.session_state.pop(prefix+'result',None)
        st.rerun()
    if right.button('Remove last period',key=prefix+'remove',disabled=count<=1):
        st.session_state.pop(prefix+f'flow_{count}',None)
        st.session_state[count_key]=count-1
        st.session_state.pop(prefix+'result',None)
        st.rerun()
    rate=st.text_input('Discount rate (% per period)',value='10',key=prefix+'rate') if kind=='npv' else None
    signature=(kind,tuple(flows),rate)
    run,reset=st.columns(2)
    if run.button('Calculate',key=prefix+'calculate'):
        try:
            result,view=simple_appraisal_result(kind,flows,rate)
            st.session_state[prefix+'result']=(signature,result,view)
        except ValueError as exc:st.error(str(exc))
    def clear():
        for key in list(st.session_state):
            if key.startswith(prefix):del st.session_state[key]
    reset.button('Reset',key=prefix+'reset',on_click=clear)
    saved=st.session_state.get(prefix+'result')
    if saved and saved[0]!=signature:st.info('Inputs changed — calculate again.')
    elif saved:
        _,result,view=saved
        if not result.ok:st.error(f'{result.status}: {result.message}')
        else:
            if kind=='npv':st.success(f'NPV: {result.value:,.6f}')
            else:st.success('IRR: '+', '.join(f'{root*100:.6f}%' for root in result.value)+' per period')
            st.write(view['formula']);st.write(view['substitution'])
            for step in view['steps']:st.write(step)
            st.info(view['interpretation'])
            for warning in result.warnings:st.warning(warning)


def render_form(session,kind,profile,financial,theme):
    if kind in ('bond_floating','bond_option') and financial!='Advanced':
        st.info('Select Advanced financial controls for this model. The execution profile can remain Standard.');return
    fields=WORKFLOWS[kind][2]
    stored=session.values.setdefault(kind,defaults(kind));raw=defaults(kind)
    for field in fields:
        if field.advanced and financial!='Advanced':continue
        key=f's7_{kind}_{field.key}';value=stored.get(field.key,field.default)
        if field.kind=='choice':
            raw[field.key]=st.selectbox(field.label,field.choices,index=field.choices.index(value) if value in field.choices else 0,key=key)
        elif field.kind=='bool':raw[field.key]=st.checkbox(field.label,value=bool(value),key=key)
        elif field.kind=='table':raw[field.key]=st.text_area(field.label,value=str(value),height=150,key=key)
        else:raw[field.key]=st.text_input(field.label,value=str(value),key=key)
        stored[field.key]=raw[field.key]
    signature=fingerprint(kind,{'form':raw,'profile':profile,'financial':financial})
    session.changed(kind,signature)
    left,right=st.columns(2)
    if left.button('Calculate' if kind!='live_data' else 'Retrieve latest available',key='s7_run_'+kind,disabled=session.job is not None):
        session.current.pop(kind,None);session.current.pop('export:'+kind,None)
        try:
            calculation,inputs=build(kind,raw,profile,financial)
            if kind=='live_data':
                from financial_toolkit.providers_s5 import fetch_data
                def task(cancelled):
                    result=fetch_data(**inputs,cancelled=cancelled)
                    return {'kind':'market_data','inputs':{'rows':result.diagnostics.get('observations',[]),'mode':profile},'result':result}
                session.start(kind,kind,inputs,task)
            else:session.start(kind,calculation,inputs)
            st.rerun()
        except (ValueError,TypeError) as exc:st.error(str(exc))
    def reset():
        session.clear(kind);session.values[kind]=defaults(kind)
        for k in list(st.session_state):
            if k.startswith('s7_'+kind+'_'):del st.session_state[k]
    right.button('Clear / reset',key='s7_reset_'+kind,on_click=reset)
    payload=session.current.get(kind)
    if payload:
        show(payload,profile,theme,kind)
        if payload['result'].ok:export_controls(session,kind,payload)
        mc=payload['result'].diagnostics.get('monte_carlo',{})
        if 'seed' in mc:st.caption(f'Actual seed: {mc["seed"]}. Enter it in Seed to reuse; clear Seed for automatic generation.')


def show(payload,profile,theme,key):
    result=payload['result'];view=presentation(payload['kind'],payload['inputs'],result)
    if result.ok:
        st.success(view['summary']+' '+view['unit'] if result.value is not None else 'Calculation complete — see metrics and workings')
    else:st.error(f'{result.status}: {result.message}')
    for warning in view['warnings']:st.warning(warning)
    st.info(view['interpretation'])
    simple=key=='tvm_regular' or key.startswith('bond_simple_')
    if simple and result.ok:st.write(view['formula'])
    for name,rows in view['tables'].items():
        if simple and name=='Summary metrics':continue
        page_size=200 if profile=='Standard' else 500
        pages=max(1,(len(rows)+page_size-1)//page_size)
        page=st.number_input(f'{name} page (of {pages})',1,pages,1,key=f'{key}_page_{name}')-1
        st.dataframe(rows[page*page_size:(page+1)*page_size],width='stretch')
    if view['charts']:
        index=st.selectbox('Chart',range(len(view['charts'])),format_func=lambda i:view['charts'][i]['title'],key=key+'_chart')
        chart=view['charts'][index];n=len(chart['x'])
        start=st.number_input('Chart start row',0,max(0,n-1),0,key=key+'_chart_start')
        count=st.number_input('Chart row count',1,max(1,n),min(n,1000),key=key+'_chart_count')
        try:
            window=chart_window(chart,profile,start,count)
            frame=pd.DataFrame(window['series'],index=window['x'])
            kind=window.get('kind','line')
            if kind=='bar':st.bar_chart(frame,x_label=window['x_label'],y_label=window['y_label'])
            elif kind=='scatter':
                frame.index.name=window['x_label'];st.scatter_chart(frame.reset_index(),x=window['x_label'],y=list(window['series'])[0])
            elif kind=='heatmap':
                import altair as alt
                cells=[{'Asset':str(x),'Other asset':name,'Correlation':value} for name,ys in window['series'].items() for x,value in zip(window['x'],ys)]
                st.altair_chart(alt.Chart(pd.DataFrame(cells)).mark_rect().encode(x='Asset:N',y='Other asset:N',color=alt.Color('Correlation:Q',scale=alt.Scale(domain=[-1,1],scheme='redblue')),tooltip=['Asset','Other asset','Correlation']))
            else:st.line_chart(frame,x_label=window['x_label'],y_label=window['y_label'])
        except (ValueError,TypeError) as exc:st.warning(str(exc))
    with st.expander('Inputs, formula, assumptions and full-precision workings'):
        st.write(view['formula']);st.json({'inputs':view['inputs'],'assumptions':view['assumptions'],'diagnostics':view['diagnostics']})


def export_controls(session,key,payload):
    if st.button('Prepare Excel and CSV reports',key='s7_prepare_'+key,disabled=session.job is not None):
        source=copy.deepcopy(payload)
        def task(cancelled):
            record=make_record(source['kind'],source['inputs'],source['result'])
            bundle=csv_bundle(record,cancelled);book=excel_bytes(record,cancelled)
            return {'kind':'export','inputs':{},'result':CalculationResult(Status.VALID,None,'reports'),
                'xlsx':book,'zip':bundle,'record':record}
        session.start('export:'+key,'export',{'mode':source['inputs'].get('mode','Standard')},task);st.rerun()
    exports=session.current.get('export:'+key)
    if exports and payload['result'].ok:
        st.download_button('Download Excel',exports['xlsx'],'analysis.xlsx',key='s7_xlsx_'+key)
        st.download_button('Download CSV bundle',exports['zip'],'analysis_csv.zip',key='s7_csv_'+key)


def render_reports(session,profile,theme):
    uploaded=st.file_uploader('Open typed Excel, CSV bundle or legacy typed CSV',type=['xlsx','zip','csv'],key='s7_upload')
    if st.button('Review imported file',key='s7_review_file',disabled=session.job is not None):
        try:
            if uploaded is None:raise InputError('Choose a file first.')
            data=uploaded.getvalue();suffix='.'+uploaded.name.rsplit('.',1)[-1].lower()
            def task(cancelled):
                record,info=read_bytes(data,suffix,profile,cancelled)
                return {'kind':'file_preview','inputs':{},'result':CalculationResult(Status.VALID,None,'preview only'),
                    'record':record,'info':info}
            session.start('__preview__','file_preview',{'mode':profile},task);st.rerun()
        except (ValueError,TypeError) as exc:st.error(str(exc))
    preview=session.current.get('__preview__')
    if preview:
        record=preview['record'];st.subheader('Import review — not yet recalculated')
        st.write({'calculation':record['calculation_type'],'source_schema':preview['info']['source_schema'],
            'execution_profile':record['inputs'].get('mode','Standard'),'source_provenance':record['sources']})
        with st.expander('Imported inputs and explicit units'):st.json({'inputs':record['inputs'],'units':record['input_metadata']})
        if st.button('Recalculate reviewed inputs',key='s7_recalculate_import',disabled=session.job is not None):
            if record['inputs'].get('mode','Standard')!=profile:st.error('Select the execution profile shown in this file before recalculating.')
            else:
                source=copy.deepcopy(record)
                def task(cancelled):
                    result,differences=recalculate(source,cancelled)
                    return {'kind':source['calculation_type'],'inputs':source['inputs'],'result':result,'differences':differences}
                session.start('__imported__',source['calculation_type'],source['inputs'],task);st.rerun()
    keys=[k for k,p in session.current.items() if p['kind'] in WORKFLOWS and p['result'] is not None]
    if not keys:st.caption('Calculate a workflow or review and recalculate a saved file to report it.');return
    key=st.selectbox('Current session analysis',keys,key='s7_report_selection')
    payload=session.current[key]
    if 'differences' in payload:st.write(payload['differences'])
    show(payload,profile,theme,'report_'+key)
    if payload['result'].ok:export_controls(session,key,payload)


if __name__=='__main__':run()
