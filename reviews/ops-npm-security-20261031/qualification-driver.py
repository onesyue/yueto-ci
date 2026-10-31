"""Same Ops91 tree; only the four reviewed npm inputs toggle."""
import hashlib,importlib.util,json,os,subprocess
from pathlib import Path
source=Path('/home/runner/work/repo');out=Path('/out');policy=source/'.ci-policy'
paths=['frontend/package.json','frontend/package-lock.json','telegram-bot/yue/miniapp/package.json','telegram-bot/yue/miniapp/package-lock.json']
original={p:(source/p).read_bytes() for p in paths}
plugin=Path('/tmp/security_collection_probe.py');plugin.write_text('import json,os\nfrom pathlib import Path\ndef pytest_collection_finish(session): Path(os.environ["COLLECTION_OUTPUT"]).write_text(json.dumps([i.nodeid for i in session.items]))\n')
results={}
try:
 for mode in ('before','after'):
  for path in paths:
   (source/path).write_bytes(subprocess.check_output(['git','show','acf7f59a9a1a4ce15a7ef4b2f91bbd4a85ffb365:'+path],cwd=source) if mode=='before' else original[path])
  env=dict(os.environ,PYTHONPATH='/tmp',PYTEST_ADDOPTS='',COLLECTION_OUTPUT=str(out/(mode+'.json')))
  with (out/(mode+'.log')).open('w') as log:
   subprocess.run(['/opt/yueops-deps/venv/bin/python','-m','pytest','--collect-only','-q','-p','security_collection_probe','tests'],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
  results[mode]=json.loads((out/(mode+'.json')).read_text())
finally:
 for path,data in original.items():(source/path).write_bytes(data)
assert results['before']==results['after'] and results['after']
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source)
sp=importlib.util.spec_from_file_location('planner',policy/'scripts/pytest-shards.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
serial=json.loads(subprocess.check_output(['bash','scripts/run-pytest-parallel.sh','--describe-ci-selection'],cwd=source))['serial_modules']
ctx={'policy_revision':'b471312d7576cde0d3d69682b5dc4bf1d8cca7bb','board_revision':'0b5a9fe3511decc55dbf838d108a389d1ee6bb08','run_id':'2026103104','run_attempt':'1','runner_os':'Linux','runner_arch':'aarch64','runner_image':'sha256:97e9a5cea0788b2c78e9fdbde1447068b6b1eba9a744a9aeeb079299c7948f0f'}
plan=m.plan(source,ctx,16,serial);m.validate_plan(plan)
counts={};seen=set()
for a in plan['assignments']:
 nodes={n for n in results['after'] if n.split('::')[0] in a['modules']};assert not seen&nodes;seen|=nodes;counts[a['id']]=len(nodes)
assert seen==set(results['after'])
receipt={'status':'PASS_COLLECTION_QUALIFICATION_ONLY','source':'91ea64a329973b6c4f20451d41899ea16c925c5f','before_inputs':'acf7f59a9a1a4ce15a7ef4b2f91bbd4a85ffb365','after_inputs':'625cb93f369894bae7aad54dafb2b7f4d95008d4','controlled_paths':paths,'context':ctx,'ordered_nodeids_equal':True,'partition_no_loss_or_overlap':True,'count':len(results['after']),'partition_counts':counts,'evidence_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.json')},'full_execution_gate':'NOT_RUN; production hold retained'}
(out/'qualification.json').write_text(json.dumps(receipt,indent=2)+'\n')
