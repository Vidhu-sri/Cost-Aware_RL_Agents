import pathlib,json,math
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from numpy.polynomial.hermite import hermgauss
R=pathlib.Path(__file__).resolve().parents[2]/'results/dpo_live_v2'
d=[]
for p in (R/'attempts').glob('*/*/done.json'):
 x=json.loads(p.read_text())
 if x.get('smoke') or x.get('verification_status') not in ('passed','failed','no_patch'):continue
 q=pathlib.Path(x['result_dir']);t=[json.loads(z) for z in (q/'turn_telemetry.jsonl').read_text().splitlines() if z]
 g=[z['generation_wall_seconds'] for z in t if isinstance(z.get('generation_wall_seconds'),(int,float)) and z['generation_wall_seconds']>0]
 if not g:continue
 steps=json.loads((q/'traces'/f'trace_{x["task_id"]}.json').read_text())['steps'];sub=any(c.get('function_name')=='submit_patch' for s in steps for c in s.get('tool_calls',[]))
 d.append((x['task_id'],int(x['resolved'] is True),math.log(sum(g)/len(g)),int(sub)))
groups=[]
for task in sorted({x[0] for x in d}):
 rr=[x for x in d if x[0]==task];X=np.array([[1,x[2],x[3]] for x in rr],float);y=np.array([x[1] for x in rr],float);groups.append((X,y))
z,w=hermgauss(30);z=np.sqrt(2)*z;logw=np.log(w)-.5*np.log(np.pi)
def nll(theta):
 beta=theta[:3];sigma=np.exp(theta[3]);total=0
 for X,y in groups:
  eta=X@beta;v=eta[:,None]+sigma*z[None,:];total-=logsumexp(logw+(y[:,None]*v-np.logaddexp(0,v)).sum(axis=0))
 return total
res=minimize(nll,[-2.,0.,1.,-2.],method='L-BFGS-B',bounds=[(-20,20),(-20,20),(-20,20),(-8,4)],options={'maxiter':500})
out={'converged':bool(res.success),'message':str(res.message),'n_attempts':len(d),'n_tasks':len(groups),'coefficients':{'intercept':float(res.x[0]),'log_generation_seconds_per_turn':float(res.x[1]),'explicit_submit':float(res.x[2])},'random_intercept_sd':float(np.exp(res.x[3])),'nll':float(res.fun),'warnings':[]}
if res.x[3]<-7.5:out['warnings'].append('Random-intercept variance optimized at the lower bound; coefficients approximate ordinary logistic regression.')
if abs(res.x[0])>=19.9 or res.x[3]>=3.9:out['warnings'].append('Parameter bound reached; fit is not reliably identified and coefficients should not be interpreted.')
# Hessian via central finite differences on first three coefficients, conditional on fitted random intercept.
h=.001;H=np.zeros((3,3))
for i in range(3):
 for j in range(3):
  e=np.zeros(4);f=np.zeros(4);e[i]=h;f[j]=h
  H[i,j]=(nll(res.x+e+f)-nll(res.x+e-f)-nll(res.x-e+f)+nll(res.x-e-f))/(4*h*h)
try:
 se=np.sqrt(np.diag(np.linalg.inv(H)))
 out['conditional_wald_ci95']={k:[float(v-1.96*se[i]),float(v+1.96*se[i])] for i,(k,v) in enumerate(out['coefficients'].items())}
except np.linalg.LinAlgError:out['warnings'].append('Hessian singular; no Wald intervals')
(R/'exploratory_logit.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
