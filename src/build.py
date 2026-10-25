s=open('shell.html').read()
s=s.replace('/*CSS*/',open('style.css').read()).replace('/*DATA*/',open('data.json').read()).replace('/*JS*/',open('app.js').read())
open('../index.html','w').write(s); print(len(s))
