"""Disposable offline same-tree collection qualification; never production code."""
import hashlib, importlib.util, json, os, subprocess, sys
from pathlib import Path

source=Path('/home/runner/work/repo'); policy=source/'.ci-policy'; output=Path('/out')
python='/opt/yueops-deps/venv/bin/python'
plugin=Path('/tmp/collection_probe.py')
plugin.write_text('''import hashlib,json,os,pickle,random\nfrom pathlib import Path\nimport pytest\n@pytest.hookimpl(trylast=True)\ndef pytest_configure(config): random.seed(817531)\ndef pytest_collection_finish(session):\n Path(os.environ["COLLECTION_OUTPUT"]).write_text(json.dumps({"nodeids":[item.nodeid for item in session.items],"rng":hashlib.sha256(pickle.dumps(random.getstate())).hexdigest()}))\n''')
serial=json.loads(subprocess.check_output(['bash','scripts/run-pytest-parallel.sh','--describe-ci-selection'],cwd=source))['serial_modules']
spec=importlib.util.spec_from_file_location('native_planner',policy/'scripts/pytest-shards.py');planner=importlib.util.module_from_spec(spec);spec.loader.exec_module(planner)
context={'policy_revision':'031b4cd34b1e6733a69e7eeaab8959c59b266c9e','board_revision':'0b5a9fe3511decc55dbf838d108a389d1ee6bb08','run_id':'2026103101','run_attempt':'1','runner_os':'Linux','runner_arch':'aarch64','runner_image':'sha256:97e9a5cea0788b2c78e9fdbde1447068b6b1eba9a744a9aeeb079299c7948f0f'}
plan=planner.plan(source,context,2,serial);planner.validate_plan(plan)
(output/'collection-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
hook=source/'conftest.py'; original=hook.read_bytes(); saved=Path('/tmp/qualified-hook.py'); cases={}
def collect(name, modules, seed=None):
 env=dict(os.environ,PATH='/opt/yueops-deps/venv/bin:'+os.environ['PATH'],PYTHONPATH='/tmp',COLLECTION_OUTPUT=str(output/(name+'.json')),PYTEST_ADDOPTS='')
 command=[python,'-m','pytest','--collect-only','-q','-p','collection_probe',*modules]
 if seed is not None: command += ['--yueto-shuffle-seed',str(seed)]
 with (output/(name+'.log')).open('w') as log:
  result=subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
 if result.returncode: raise RuntimeError(name+' collection returned '+str(result.returncode))
 cases[name]=json.loads((output/(name+'.json')).read_text())
for enabled in (False,True):
 label='enabled' if enabled else 'disabled'
 if not enabled:hook.rename(saved)
 else:saved.rename(hook)
 collect(label,['tests'])
 for assignment in plan['assignments']:collect(label+'-'+assignment['id'],assignment['modules'])
collect('seed-37-a',['tests'],37);collect('seed-37-b',['tests'],37);collect('seed-53',['tests'],53)
assert hook.read_bytes()==original
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source)
assert cases['enabled']==cases['disabled'], 'default full corpus/order/global RNG changed'
for assignment in plan['assignments']:
 name=assignment['id'];assert cases['enabled-'+name]==cases['disabled-'+name],name+' default shard changed'
for name in ('seed-37-a','seed-37-b','seed-53'):
 assert sorted(cases[name]['nodeids'])==sorted(cases['enabled']['nodeids']),name+' multiset differs'
 assert cases[name]['rng']==cases['enabled']['rng'],name+' changed global RNG'
assert cases['seed-37-a']==cases['seed-37-b'], 'seed repeat differs'
assert cases['seed-37-a']['nodeids']!=cases['enabled']['nodeids'], 'explicit seed did not shuffle'
assert cases['seed-37-a']['nodeids']!=cases['seed-53']['nodeids'], 'distinct seeds did not differ'
seen=set()
for assignment in plan['assignments']:
 nodes=cases['enabled-'+assignment['id']]['nodeids'];assert not seen.intersection(nodes);seen.update(nodes)
assert seen==set(cases['enabled']['nodeids'])
receipt={'status':'PASS_COLLECTION_QUALIFICATION_ONLY','source':'4e4630ec13c77b5b24bf51d2febd24e6a9a89eab','policy':context['policy_revision'],'board':context['board_revision'],'image':context['runner_image'],'hook_blob':'05613fb260c40650ff94397493fe0bf8132d1e8e','hook_sha256':hashlib.sha256(original).hexdigest(),'default_order_and_rng_unchanged':True,'shard_order_and_rng_unchanged':True,'seed_repeat_equal':True,'seed_multisets_equal':True,'seed_global_rng_unchanged':True,'complete_partition':True,'counts':{name:len(case['nodeids']) for name,case in cases.items()},'evidence_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.glob('*.json'))},'full_execution_gate':'NOT_RUN; production hold retained'}
(output/'qualification.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
