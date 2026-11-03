# yueto #73 review at e0968ee30053d685b9d8c7a8a61661495a2e57e7

for node in module.body:
    if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('\\''RUNTIME'\\'','\\''LINK'\\''):
        constants[node.targets[0].id]=ast.literal_eval(node.value)
sources={}
outputs={}
for ns,(runtime,*_) in constants['\\''RUNTIME'\\''].items():
    path='\\''i18n/catalog/'\\''+ns+'\\''.json'\\''
    data=blob(head,path)
    sources[path]=hashlib.sha256(data).hexdigest()
    rendered=(json.dumps(json.loads(data),ensure_ascii=False,indent=2)+'\\''\\n'\\'').encode()
    outputs[runtime]=hashlib.sha256(rendered).hexdigest()
path='\\''i18n/catalog/link.json'\\''
data=blob(head,path)
sources[path]=hashlib.sha256(data).hexdigest()
for lang,runtime in constants['\\''LINK'\\''].items():
    rendered=(json.dumps(json.loads(data)[lang],ensure_ascii=False,indent=2)+'\\''\\n'\\'').encode()
    outputs[runtime]=hashlib.sha256(rendered).hexdigest()
expected={'\\''version'\\'':1,'\\''sources'\\'':sources,'\\''outputs'\\'':outputs}
assert json.loads(blob(head,'\\''i18n/catalog/SOURCE-DIGEST.json'\\''))==expected,'\\''manifest mismatch'\\''
print('\\''SOURCE-DIGEST.json: all 10 source hashes and 11 expected-output hashes match exact review head'\\'')
result=subprocess.run(['\\''git'\\'','\\''diff'\\'','\\''--check'\\'',base,head],capture_output=True)
assert result.returncode==0,'\\''diff formatting check failed'\\''
print('\\''git diff --check: passed'\\'')
'" in /Users/j/Projects/yueto
 succeeded in 8ms:
i18n/catalog/ops.bot.json: valid unique string map; canonical formatting; 13 new/changed entries preserve placeholders, HTML and newlines; 6 removed keys
i18n/catalog/ops.miniapp.json: valid unique string map; canonical formatting; 14 new/changed entries preserve placeholders, HTML and newlines; 15 removed keys
SOURCE-DIGEST.json: all 10 source hashes and 11 expected-output hashes match exact review head
git diff --check: passed

codex
- `i18n/catalog/ops.bot.json:852`、`i18n/catalog/ops.miniapp.json:472`：未发现需修正的缺陷、秘密泄露或测试弱化；译文、占位符和 HTML 标记一致。
- `i18n/catalog/SOURCE-DIGEST.json:8`：全部来源及预期输出摘要与指定 head 一致；JSON 和差异格式校验通过。

VERDICT: approve
57,439
- `i18n/catalog/ops.bot.json:852`、`i18n/catalog/ops.miniapp.json:472`：未发现需修正的缺陷、秘密泄露或测试弱化；译文、占位符和 HTML 标记一致。
- `i18n/catalog/SOURCE-DIGEST.json:8`：全部来源及预期输出摘要与指定 head 一致；JSON 和差异格式校验通过。

VERDICT: approve
