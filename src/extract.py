import openpyxl, json
wb=openpyxl.load_workbook('/workspace/hobby-project/source/01M55QMJGWWV6D2HSQS0E9JJV5.xlsx',data_only=True)
out={}
for name in ['Licence_Funnel','Interaction_Rules','Golden_Events','Expected_Results','Value_Score','Metric_Dictionary','Dashboard_Spec','Agent_Test_Questions','Risk_Register','Roadmap_Gates','Renewal_Criteria']:
    rows=[r for r in wb[name].iter_rows(values_only=True) if any(c is not None for c in r)]
    h=[str(x) for x in rows[0]]
    out[name]=[{h[i]:('' if v is None else str(v)) for i,v in enumerate(r)} for r in rows[1:]]
open('data.json','w').write(json.dumps(out,ensure_ascii=False))
print({k:len(v) for k,v in out.items()})
