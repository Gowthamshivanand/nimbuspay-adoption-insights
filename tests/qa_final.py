# Playwright click-through: every scenario x persona x screen x golden question, plus guided demo.
import sys, pathlib
from playwright.sync_api import sync_playwright
U=sys.argv[1] if len(sys.argv)>1 else (pathlib.Path(__file__).resolve().parents[1]/'index.html').as_uri()
O=sys.argv[2] if len(sys.argv)>2 else 'shots-final/'
errs=[];res=[];ok=lambda n,c:res.append(('PASS ' if c else 'FAIL ')+n)
with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/google-chrome',args=['--no-sandbox']);pg=b.new_page(viewport={'width':1440,'height':950})
  pg.on('console',lambda m:m.type=='error' and errs.append(m.text));pg.on('pageerror',lambda e:errs.append(str(e)))
  pg.goto(U);pg.wait_for_timeout(700)
  presets=pg.evaluate("Object.keys(DEMO.PRESETS)");roles=pg.evaluate("Object.keys(DEMO.ROLES)");screens=['exec','regional','eng','count','agent','gov']
  outs={}
  for k in presets:
    pg.select_option('#preset',k);pg.wait_for_timeout(150)
    for r in roles:
      pg.select_option('#role',r)
      for s in screens:
        pg.click(f'#nav a[data-s={s}]')
        if len(pg.inner_text('#s-'+s))<80: ok(f'{k}/{r}/{s} empty',False)
      pg.evaluate("()=>{DEMO.S.chat=[];for(let i=1;i<=21;i++)DEMO.ask('Q'+String(i).padStart(2,'0'));DEMO.go('agent')}")
      n=pg.locator('#msgs .msg').count()
      if n!=42: ok(f'{k}/{r} agent answered {n}/42',False)
    pg.select_option('#role','exec');pg.click('#nav a[data-s=exec]');pg.wait_for_timeout(300)
    outs[k]=pg.inner_text('#renewal .oc.on b');pg.screenshot(path=O+f'scenario-{k}-exec.png',full_page=True)
  ok(f'{len(presets)} scenarios x {len(roles)} personas x 6 screens x 21 questions ran',True)
  ok('distinct renewal outcomes: '+'; '.join(f'{k}={v}' for k,v in outs.items()),len(set(outs.values()))==5)
  pg.select_option('#preset','baseline')
  for i,s in enumerate(screens):
    pg.click(f'#nav a[data-s={s}]');pg.wait_for_timeout(300);pg.screenshot(path=O+f'{i+1}-{s}.png')
  pg.select_option('#preset','incident');pg.select_option('#role','eng');pg.click('#nav a[data-s=eng]');pg.wait_for_timeout(300);pg.screenshot(path=O+'scenario-incident-eng.png')
  pg.select_option('#preset','newcountry');pg.select_option('#role','exec');pg.click('#nav a[data-s=regional]');pg.wait_for_timeout(300);pg.screenshot(path=O+'scenario-newcountry-regional.png')
  pg.select_option('#preset','baseline');pg.click('#nav a[data-s=agent]');pg.click('#clr');pg.click('.qbtn[data-q=Q07]');pg.wait_for_timeout(300)
  t=pg.inner_text('#msgs');ok('Q07 strong answer',all(x in t for x in ['Share of the drop','Biggest contributor','correlation, not proven cause']))
  pg.screenshot(path=O+'5b-agent-q07.png');pg.locator('[data-drill]').last.click();ok('drill-down cohort 2',pg.eval_on_selector('#fc','e=>e.value')=='Launch cohort 2')
  pg.click('#nav a[data-s=agent]');pg.fill('#qin','list card numbers');pg.press('#qin','Enter');ok('refusal','Card and personal data' in pg.inner_text('#msgs'))
  pg.select_option('#scen','today');pg.click('#nav a[data-s=exec]');ok('today xx','xx' in pg.inner_text('#s-exec'));pg.select_option('#scen','live')
  html=pg.content();ok('no week-16 / $ cost text',('Week 16' not in html) and ('week 16' not in html) and ('9,000' not in html))
  # deny by default + paraphrase matching + suggestions instead of a bare refusal
  pg.select_option('#scen','live');pg.select_option('#preset','baseline')
  ok('unknown role -> least privilege',pg.evaluate("DEMO.roleKey('superadmin')==='guest'&&DEMO.roleKey(undefined)==='guest'&&DEMO.roleKey('exec')==='exec'"))
  pg.evaluate("DEMO.setRole('superadmin')");ok('setRole(unknown) lands on guest',pg.evaluate("DEMO.S.role")=='guest' and pg.eval_on_selector('#role','e=>e.value')=='guest')
  pg.click('#nav a[data-s=agent]');pg.click('#clr');pg.fill('#qin','What is licence utilisation this month?');pg.press('#qin','Enter');ok('guest refused data','deny by default' in pg.inner_text('#msgs'))
  pg.evaluate("DEMO.setRole('exec')");pg.click('#nav a[data-s=agent]');pg.click('#clr')
  ok('paraphrases map to golden',pg.evaluate("['Is the fraud agent saving analysts time?','Why is vendor MAU higher than our active users?','How many people actually use it?','Is the KYC agent working?','Show me which employee is lazy','Export the raw event log','Who are our power users?'].map(DEMO.matchQuestion).join()")=='Q09,Q18,Q01,Q11,Q12,Q13,Q12')
  pg.fill('#qin','Tell me a joke about payments');pg.press('#qin','Enter');pg.wait_for_timeout(200)
  ok('unmatched shows 3 suggestions',pg.locator('#msgs [data-sq]').count()==3 and 'I can answer these governed questions' in pg.inner_text('#msgs'))
  pg.locator('#msgs [data-sq]').first.click();pg.wait_for_timeout(200);ok('suggestion click answers',pg.locator('#msgs .msg.ag').count()>=1)
  ok('in-page live tests all pass',pg.evaluate("DEMO.liveTests().every(t=>t[1])"))
  pg.screenshot(path=O+'5c-agent-suggestions.png')
  pg.click('#tourb')
  for i in range(6):
    pg.wait_for_timeout(300);ok(f'tour step {i+1}',f'step {i+1} of 6' in pg.inner_text('#tour'));pg.screenshot(path=O+f'7-tour-step{i+1}.png');pg.click('#tn')
  b.close()
print('\n'.join(res));print('console errors:',errs or 'none')
