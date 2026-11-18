import csv,math,pathlib,json
import numpy as np
from scipy.optimize import minimize
R=pathlib.Path(__file__).resolve().parents[2]/'results/dpo_live_v2'
data={}
for x in csv.DictReader((R/'per_turn.csv').open()):
 if x['smoke']!='False':continue
 try:
  v=float(x['generation_wall_seconds']);load=float(x['running_requests'])
  if v>0:data.setdefault(x['task_id'],[]).append((math.log(v),int(x['arm']=='DPO'),load))
 except (ValueError,TypeError):continue
groups=[]
for task,v in data.items():
 a=np.asarray(v); X=np.column_stack((np.ones(len(a)),a[:,1],a[:,2]));y=a[:,0];groups.append((X,y))
def fit(z,ret=False):
 sig2,tau2=np.exp(z);xx=np.zeros((3,3));xy=np.zeros(3);logdet=0;total=0
 for X,y in groups:
  n=len(y);d=sig2+n*tau2;vix=(X-tau2/d*X.sum(axis=0))/sig2;viy=(y-tau2/d*y.sum())/sig2
  xx+=X.T@vix;xy+=X.T@viy;logdet+=(n-1)*np.log(sig2)+np.log(d);total+=n
 try:beta=np.linalg.solve(xx,xy)
 except np.linalg.LinAlgError:return 1e100
 quad=0
 for X,y in groups:
  e=y-X@beta;n=len(e);quad+=(e@e-tau2/(sig2+n*tau2)*e.sum()**2)/sig2
 ll=.5*(logdet+quad+total*np.log(2*np.pi))
 if ret:return beta,np.linalg.inv(xx),sig2,tau2,ll
 return ll
opt=minimize(fit,np.log([.5,.1]),method='L-BFGS-B',bounds=[(-12,8),(-12,8)])
b,c,s,t,ll=fit(opt.x,True)
out={'converged':bool(opt.success),'n_turns':sum(len(y) for _,y in groups),'n_tasks':len(groups),'beta':b.tolist(),'se':np.sqrt(np.diag(c)).tolist(),'adjusted_DPO_A0_ratio':float(np.exp(b[1])),'ratio_ci95':[float(np.exp(b[1]-1.96*np.sqrt(c[1,1]))),float(np.exp(b[1]+1.96*np.sqrt(c[1,1])))],'running_request_coef':float(b[2]),'waiting_requests_all_zero':True,'random_intercept_variance':float(t),'residual_variance':float(s)}
(R/'load_adjusted_H1.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
