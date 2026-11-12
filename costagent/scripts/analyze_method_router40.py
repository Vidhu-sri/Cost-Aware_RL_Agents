"""Read-only raw-result audit; write new derived seven-arm comparison artifacts."""
import csv,importlib.util,json,math
from collections import Counter
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
EVAL=ROOT/'costagent/artifacts/mixed-temperature-v1/evaluation'
OUT=EVAL/'method40-20261110-analysis'
NBOOT=20000
SEED=20261110
CALLS='billed_tool_calls_from_trace'
TOKENS='total_tokens_from_trace'
NEW='Method router'
LABELS={'A0':'A0 base','A1':'A1 stop-loss','A2':'A2 RFT','DPO':'DPO','A9-contrast':'SDPO contrast','Router':'DPO + phase controller (buggy pilot)',NEW:'RFT/DPO/SDPO + phase controller'}


def interval(values):
    values=np.asarray(values,dtype=float)
    valid=np.isfinite(values)
    if np.mean(~valid) >= .025:return None
    return np.quantile(values[valid],[.025,.975]).tolist()


def wilson(k,n):
    z=1.959963984540054;p=k/n;d=1+z*z/n
    center=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [100*(center-half),100*(center+half)]


def summarize(rows,rng):
    n=len(rows);solved=np.array([r['resolved'] is True for r in rows]);indices=rng.integers(n,size=(NBOOT,n));den=solved[indices].sum(1)
    summary={'n':n,'passes':int(solved.sum()),'verified_yield_pct':100*solved.mean(),'verified_yield_wilson_95ci':wilson(solved.sum(),n),
             'verification_counts':dict(Counter(r['verification_status'] for r in rows)),
             'timeouts':sum(r['timeout_flag'] for r in rows),'exceptions':sum(r['exception_flag'] for r in rows),
             'logged_exception_tasks':sum(r['exception_flag'] or r['worker_context_error_flag'] or r['worker_empty_tool_error_flag'] for r in rows),
             'worker_context_errors':sum(r['worker_context_error_flag'] for r in rows),'no_patch':sum(r['no_patch_flag'] for r in rows),
             'coverage_interpretable':sum(r['resolved'] is not None for r in rows),'passes_with_timeout':sum(r['resolved'] is True and r['timeout_flag'] for r in rows),
             'zero_solve_bootstrap_fraction':float((den==0).mean())}
    for key in [CALLS,TOKENS,'prompt_tokens_from_trace','completion_tokens_from_trace','llm_calls','duration_seconds']:
        values=np.array([r[key] for r in rows],dtype=float);draw=values[indices]
        with np.errstate(divide='ignore',invalid='ignore'):ratios=draw.sum(1)/den
        summary[key]={'total':float(values.sum()),'mean':float(values.mean()),'median':float(np.median(values)),
                      'mean_95ci':interval(draw.mean(1)), 'per_solve':float(values.sum()/solved.sum()),
                      'per_solve_95ci':interval(ratios),'solved_only_mean':float(values[solved].mean())}
    return summary


def compare(by_arm,baseline,arm,exact,seed):
    ids=sorted(t for t in by_arm[baseline] if by_arm[baseline][t]['resolved'] is not None and by_arm[arm][t]['resolved'] is not None)
    a=[by_arm[baseline][t] for t in ids];b=[by_arm[arm][t] for t in ids]
    out={'baseline':baseline,'arm':arm,**exact(a,b),'task_ids':ids,
         'excluded_ids':sorted(set(by_arm[baseline])-set(ids)),
         'baseline_only_ids':[t for t,x,y in zip(ids,a,b) if x['resolved'] is True and y['resolved'] is not True],
         'arm_only_ids':[t for t,x,y in zip(ids,a,b) if y['resolved'] is True and x['resolved'] is not True]}
    rng=np.random.default_rng(seed);ix=rng.integers(len(ids),size=(NBOOT,len(ids)))
    sa=np.array([r['resolved'] is True for r in a]);sb=np.array([r['resolved'] is True for r in b]);da=sa[ix].sum(1);db=sb[ix].sum(1)
    out['delta_resolve_pp']=float(100*(sb.mean()-sa.mean()));out['delta_resolve_pp_95ci']=interval(100*(sb[ix].mean(1)-sa[ix].mean(1)))
    out['undefined_ratio_bootstrap_fraction']=float(((da==0)|(db==0)).mean())
    for metric in [CALLS,TOKENS]:
        va=np.array([r[metric] for r in a]);vb=np.array([r[metric] for r in b]);diff=vb-va
        with np.errstate(divide='ignore',invalid='ignore'):ratios=vb[ix].sum(1)/db-va[ix].sum(1)/da
        from scipy.stats import wilcoxon
        p_calls = float(wilcoxon(diff, zero_method='wilcox', method='approx').pvalue) if np.any(diff) else 1.0
        out[metric]={'wilcoxon_signed_rank_two_sided_p':p_calls, 'mean_difference':float(diff.mean()),'mean_difference_95ci':interval(diff[ix].mean(1)),
                     'per_solve_difference':float(vb.sum()/sb.sum()-va.sum()/sa.sum()),'per_solve_difference_95ci':interval(ratios)}
    return out


def plot_results(result):
    import os
    os.environ.setdefault('MPLCONFIGDIR', '/tmp/costagent-mpl-cache')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    arms=['A0','A1','A2','DPO','A9-contrast',NEW]
    names=['Base','Stop-loss','RFT','DPO','SDPO','Method router']
    colors=['#61758a','#a58535','#30a58b','#0072b2','#8f65ae','#d55e00']
    fig,axes=plt.subplots(1,2,figsize=(10.4,4.8))
    for ax,metric,scale,label in zip(axes,[CALLS,TOKENS],[1,1000],['Mean billed tool calls / task','Mean recorded tokens / task (thousands)']):
        for arm,name,color in zip(arms,names,colors):
            r=result['arms'][arm]
            ax.scatter(r[metric]['mean']/scale,r['verified_yield_pct'],s=80 if arm==NEW else 55,c=color,label=name,marker='D' if arm==NEW else 'o',edgecolor='white',linewidth=.7,zorder=3)
        ax.set_xlabel(label);ax.set_ylabel('Verified passes / 40 tasks (%)');ax.set_ylim(6,27);ax.grid(axis='both',color='#e6e9ed',linewidth=.7);ax.set_axisbelow(True)
    axes[0].annotate('DPO: 9 solves',(result['arms']['DPO'][CALLS]['mean'],22.5),xytext=(-8,15),textcoords='offset points',ha='center',fontsize=9)
    axes[0].annotate('Router: 9 solves',(result['arms'][NEW][CALLS]['mean'],22.5),xytext=(0,-23),textcoords='offset points',ha='center',fontsize=9)
    handles,labels=axes[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.5,.06),ncol=6,frameon=False)
    fig.suptitle('Observed cost and verified success — 40 matched tasks, one seed',fontsize=13,y=.98)
    fig.text(.5,.025,'Descriptive point estimates; unknown verifications retained in coverage. See report for CIs and execution errors.',ha='center',fontsize=8,color='#555555')
    fig.tight_layout(rect=(0,.16,1,.94))
    for suffix in ['png','pdf','svg']:fig.savefig(OUT/f'pareto.{suffix}',dpi=220)
    plt.close(fig)


def main():
    spec=importlib.util.spec_from_file_location('prior_analysis',EVAL/'router40-20261108a-analysis/build_results_additions.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
    by_arm,flat=prior.load_runs()
    task_meta={r['instance_id']:r for r in map(json.loads,(ROOT/'data/tasks.jsonl').read_text().splitlines())}
    batch=json.loads((EVAL/'method40-20261110b/summary.json').read_text());records={};audit=[]
    for item in batch['attempts']:
        tid=item['task_id'];p=Path(item['result_dir']);outcome=json.loads((p/'outcome.json').read_text());tracefile=p/'traces'/f'trace_{tid}.json';trace=json.loads(tracefile.read_text());calls,prompt,completion=prior.trace_cost(trace)
        primary,exc,kind=prior.classify(item,outcome,False)
        row={'arm':NEW,'task_id':tid,'repo':task_meta[tid]['repo'],'resolved':item['resolved'],'verification_status':item['verification_status'],'primary_outcome':primary,
             'timeout_flag':bool(item['agent_timeout']),'exception_flag':exc,'exception_kind':kind,'no_patch_flag':not bool(item['patch_bytes']),
             'patch_bytes':item['patch_bytes'],'test_exit_code':item['test_exit_code'],CALLS:calls,'prompt_tokens_from_trace':prompt,
             'completion_tokens_from_trace':completion,TOKENS:prompt+completion,'llm_calls':outcome['total_llm_calls'],'duration_seconds':outcome['duration_seconds'],
             'patch_submission_seconds':outcome['patch_submission_seconds'],'agent_error':outcome['agent_error'],
             'task_dir_relative':str(p.relative_to(EVAL)),'outcome_token_count_matches_trace':outcome['token_usage']['total_tokens']==prompt+completion}
        if tid in records:raise ValueError('Duplicate task')
        records[tid]=row;flat.append(row)
        decisions=[json.loads(line) for line in (p/'router_decisions.jsonl').read_text().splitlines()]
        observed=[];triggers=[];sticky=False;violations=[]
        for d in decisions:
            if sticky and d['method']!='sdpo':violations.append('sticky_violation')
            sticky |= d['method']=='sdpo'
            if not observed or observed[-1]!=d['method']:observed.append(d['method'])
            if d['method']=='sdpo' and d['previous_method']!='sdpo':triggers.append(d['reason'])
        monitor=json.loads((p/'monitor.json').read_text());response_models=Counter();http_errors=[]
        for f in p.glob('model_response_*.bin'):
            try:response=json.loads(f.read_bytes())
            except (ValueError,UnicodeError):continue
            if response.get('choices'):response_models[response.get('model','unknown')]+=1
            elif response.get('error'):http_errors.append({'path':str(f),'error':response['error']})
        audit.append({'task_id':tid,'method_sequence':observed,'first_sdpo_triggers':triggers,'violations':violations,'method_requests':dict(Counter(d['method'] for d in decisions)),
                      'successful_response_models':dict(response_models),'http_errors':http_errors,'cleanup_ok':not monitor['remaining_owned_ids'],
                      'monitor_gap_samples':sum('monitor_error' in x for x in monitor['samples']),
                      'vanished_processes_handled':sum(x.get('vanished_during_sample',0) for x in monitor['samples'])})
    by_arm[NEW]=records
    assert len(records)==40 and set(records)==set(by_arm['A0'])
    for row in flat:
        p=EVAL/row['task_dir_relative'];worker=(p/'worker.log').read_text(errors='replace')
        row['worker_context_error_flag']='ContextWindowExceededError' in worker
        row['worker_empty_tool_error_flag']='Router would expose no tools' in worker
        row['trace_path']=str(p/'traces'/f"trace_{row['task_id']}.json")
        row['repo']=task_meta[row['task_id']]['repo']
    rng=np.random.default_rng(SEED);summaries={arm:summarize(list(rows.values()),rng) for arm,rows in by_arm.items()}
    comparisons=[compare(by_arm,'A0',arm,prior.exact_mcnemar,SEED+i) for i,arm in enumerate(['A1','A2','DPO','A9-contrast',NEW])]
    comparisons.append(compare(by_arm,'DPO',NEW,prior.exact_mcnemar,SEED+10))
    mainarms=['A0','A1','A2','DPO','A9-contrast',NEW]
    common=sorted(t for t in records if all(by_arm[a][t]['resolved'] is not None for a in mainarms))
    sensitivity={a:summarize([by_arm[a][t] for t in common],rng) for a in mainarms}
    result={'labels':LABELS,'arms':summaries,'paired_tests':comparisons,'common_interpretable_ids':common,'common_interpretable_summary':sensitivity,
            'router_audit':audit,'resamples':NBOOT,'bootstrap_seed':SEED,'original_interrupted_attempt':str(EVAL/'method40-20261110a/rerun/fastapi_14258'),
            'trace_usage_mismatches':[(r['arm'],r['task_id']) for r in flat if not r['outcome_token_count_matches_trace']],
            'method_notes':'Exploratory single-seed comparison; unknown verifications excluded pairwise. All-attempt costs include unknowns. Ratios include costs of all attempts divided by verified successes. CIs condition on nonzero solve bootstrap samples; omitted if undefined fraction >=2.5%. No non-inferiority margin prespecified. New router includes phase controls. Old pilot remains confounded.'}
    OUT.mkdir(exist_ok=True)
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (OUT/'per_task.json').write_text(json.dumps(flat,indent=2)+'\n')
    with (OUT/'per_task.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(sorted(flat,key=lambda r:(r['task_id'],r['arm'])))
    def ci(x,d=1):return 'not bounded' if x is None else f'[{x[0]:,.{d}f}, {x[1]:,.{d}f}]'
    lines=['# Completed method-router comparison','',result['method_notes'],'',
           '| Arm | Pass /40 | Mean calls | Mean LLM calls | Mean tokens | Calls/solve | Tokens/solve | Timeouts | Logged-error tasks | Ungraded |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for arm in mainarms+['Router']:
        r=summaries[arm];lines.append(f"| {LABELS[arm]} | {r['passes']} | {r[CALLS]['mean']:.2f} | {r['llm_calls']['mean']:.2f} | {r[TOKENS]['mean']:,.0f} | {r[CALLS]['per_solve']:.1f} | {r[TOKENS]['per_solve']:,.0f} | {r['timeouts']} | {r['logged_exception_tasks']} | {40-r['coverage_interpretable']} |")
    lines+=['','## Confidence intervals','', '| Arm | Verified yield % [Wilson 95% CI] | Mean calls [95% CI] | Calls/solve [95% CI] | Tokens/solve [95% CI] |','|---|---:|---:|---:|---:|']
    for arm in mainarms:
        r=summaries[arm];lines.append(f"| {LABELS[arm]} | {r['verified_yield_pct']:.1f} {ci(r['verified_yield_wilson_95ci'])} | {r[CALLS]['mean']:.2f} {ci(r[CALLS]['mean_95ci'])} | {r[CALLS]['per_solve']:.1f} {ci(r[CALLS]['per_solve_95ci'])} | {r[TOKENS]['per_solve']:,.0f} {ci(r[TOKENS]['per_solve_95ci'],0)} |")
    lines+=['','Verified yield uses all 40 attempts. Unknown verification is not asserted to be a model failure. Token totals sum recorded prompt and completion usage, including repeated context; cancelled/failed requests can be undercounted. Free tools get_status and submit_patch are excluded.','',
            '## Paired comparisons','', 'Difference is comparison arm minus baseline. Exact McNemar excludes uninterpretable task pairs. P-values are exploratory and not adjusted for multiple comparisons.','',
            '| Arm vs baseline | Paired n | Baseline only | Arm only | McNemar p | Calls Wilcoxon p | Delta solve pp [95% CI] | Delta calls/solve [95% CI] |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in comparisons:lines.append(f"| {r['arm']} vs {r['baseline']} | {r['paired_tasks']} | {r['baseline_only']} | {r['arm_only']} | {r['two_sided_exact_mcnemar_p']:.4f} | {r[CALLS]['wilcoxon_signed_rank_two_sided_p']:.4f} | {r['delta_resolve_pp']:+.1f} {ci(r['delta_resolve_pp_95ci'])} | {r[CALLS]['per_solve_difference']:+.1f} {ci(r[CALLS]['per_solve_difference_95ci'])} |")
    lines+=['','## New-router costs and outcomes','','```json\n'+json.dumps(summaries[NEW],indent=2)+'\n```','',
            '## Routing and execution audit','',f"SDPO reached on {sum('sdpo' in r['method_sequence'] for r in audit)}/40 tasks. Sticky violations: {sum(len(r['violations']) for r in audit)}. All task cleanup checks: {all(r['cleanup_ok'] for r in audit)}.",
            'First SDPO trigger counts: '+str(dict(Counter(t for r in audit for t in r['first_sdpo_triggers']))),
            'Worker context errors: '+', '.join(r['task_id'] for r in records.values() if r['worker_context_error_flag']),
            'fastapi_15661 test collection cannot import scripts.prepare_release (exit 2); this alone does not establish whether snapshot/environment or agent changes caused it. rich_3480 and rich_4006 have partial test output and exit 124; neither is a valid correctness result.',
            'Uninterpretable verifications: '+', '.join(f"{r['task_id']} (exit {r['test_exit_code']})" for r in records.values() if r['resolved'] is None),
            'Logged-error flags include recovered analyzer context exceptions; the new run has zero terminal agent exceptions but three tasks with these logged errors. Calls p-values use two-sided Wilcoxon signed rank with asymptotic tie handling on the same interpretable task pairs. The percentile bootstrap interval for solve-rate differences can exclude zero with sparse discordant pairs even when exact McNemar is not significant; use the exact test for significance, not that bootstrap interval.',
            'Original interrupted fastapi_14258 remains preserved; its incomplete cost is not included in the final-40 metrics. Two completed outcomes carried from batch a; the other 38 are from resumed batch b. This was an infrastructure restart, not a best-of sampling choice.',
            'The old pilot’s 26 empty-tool exceptions make its apparent cost/timeout advantage unsuitable for an efficiency claim. New router still has analyzer context-window failures; compare as observed execution outcomes, not a clean efficacy estimate.',
            '',f'## Common interpretable sensitivity set (n={len(common)})','', '| Arm | Pass | Mean calls | Mean tokens | Calls/solve |','|---|---:|---:|---:|---:|']
    for arm,r in sensitivity.items():lines.append(f"| {LABELS[arm]} | {r['passes']} | {r[CALLS]['mean']:.2f} | {r[TOKENS]['mean']:,.0f} | {r[CALLS]['per_solve']:.1f} |")
    (OUT/'results_table.md').write_text('\n'.join(lines)+'\n')
    plot_results(result)
    print(json.dumps({'output':str(OUT),'new':summaries[NEW],'paired_new':comparisons[-2:]},indent=2))

if __name__=='__main__':main()
