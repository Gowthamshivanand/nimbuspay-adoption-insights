import openpyxl, json, os, sys
# Usage: python src/extract.py [path/to/workbook.xlsx]  (default: the workbook in the repo root; it is not committed)
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
WB=sys.argv[1] if len(sys.argv)>1 else os.path.join(ROOT,'NimbusPay_Supporting_Workbook_v10.xlsx')
if not os.path.exists(WB): sys.exit(f'Workbook not found: {WB} (pass its path as the first argument)')
wb=openpyxl.load_workbook(WB,data_only=True)
out={}
for name in ['Licence_Funnel','Interaction_Rules','Golden_Events','Expected_Results','Value_Score','Metric_Dictionary','Dashboard_Spec','Agent_Test_Questions','Risk_Register','Roadmap_Gates','Renewal_Criteria']:
    rows=[r for r in wb[name].iter_rows(values_only=True) if any(c is not None for c in r)]
    h=[str(x) for x in rows[0]]
    out[name]=[{h[i]:('' if v is None else str(v)) for i,v in enumerate(r)} for r in rows[1:]]
open(os.path.join(HERE,'data.json'),'w').write(json.dumps(out,ensure_ascii=False))
print({k:len(v) for k,v in out.items()})
