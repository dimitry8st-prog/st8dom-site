#!/usr/bin/env node
'use strict';
// Checks actual exported Code-node bodies and expressions. No network or side effects.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const file=process.argv[2]||path.resolve(__dirname,'../workflows/NNS_09_DIS_Robokassa.json');
const w=JSON.parse(fs.readFileSync(file,'utf8')),nodes=new Map(w.nodes.map(n=>[n.name,n]));
const clone=x=>JSON.parse(JSON.stringify(x));
function ctx(input,refs={}){
 return {$json:clone(input),$input:{first:()=>({json:clone(input)})},$:name=>{
  if(!Object.hasOwn(refs,name))throw Error('Missing mocked reference: '+name);
  return {first:()=>({json:clone(refs[name])})};
 }};
}
function run(name,input,refs={}){
 const n=nodes.get(name);assert.equal(n.type,'n8n-nodes-base.code');
 return clone(vm.runInNewContext('(function(){\n'+n.parameters.jsCode+'\n})()',ctx(input,refs),{timeout:1000})[0].json);
}
function expr(text,input,refs={}){
 assert.ok(text.startsWith('={{')&&text.endsWith('}}'));
 return vm.runInNewContext('('+text.slice(3,-2)+')',ctx(input,refs),{timeout:1000});
}
let count=0;function test(name,fn){fn();count++;console.log('PASS '+name);}
const raw={'Имя':'Тест-ДИС','Контакт':'@test_dis','Электронная почта':'learner@example.com','Услуга':'Экспресс-разбор','Сумма':4900,'Комментарий клиента':'Нужно упростить обработку обращений.',submittedAt:'2026-10-27T19:40:00.000Z',formMode:'test'};
const form=x=>run('Проверить форму',x);
const fp=form(raw);
function hashed(x){
 const n=nodes.get('ID заявки');assert.equal(n.parameters.action,'hash');assert.equal(n.parameters.type,'SHA256');
 assert.equal(n.parameters.encoding,'hex');assert.equal(n.parameters.dataPropertyName,'request_id');assert.equal(n.parameters.binaryData,false);
 return {...x,request_id:crypto.createHash('sha256').update(expr(n.parameters.value,x)).digest('hex')};
}
const base=hashed(fp),refsAi={'ID заявки':base};
const a={client_name:'Тест-ДИС',request_type:'Экспресс-разбор',request_summary:'Разобрать обработку обращений и определить следующие шаги.',payment_description:'Экспресс-разбор задачи по автоматизации обращений.',amount:'4900.00',priority:'normal'};
const response=x=>({choices:[{finish_reason:'stop',message:{content:JSON.stringify(x)}}]});
const ai=x=>run('Проверить JSON ИИ',x,refsAi);
const checked=ai(response(a)),refsPortal={'Проверить JSON ИИ':checked};
const link='https://st8dom.ru/orders/pay/'+'a'.repeat(43)+'/';
const p={request_id:base.request_id,order_id:81234,product_slug:'express-review',product_name:'Экспресс-разбор',amount:'4900.00',status:'payment_pending',payment_link:link,notification_status:'not_queued'};
const portal=x=>run('Проверить платёжную ссылку',x,refsPortal),cp=portal(p);
const notify=x=>run('Проверить постановку письма',x,{'Проверить платёжную ссылку':cp});
const badForm=x=>assert.throws(()=>form({...raw,...x}));
const badAi=x=>assert.throws(()=>ai(response({...a,...x})));
const badPortal=x=>assert.throws(()=>portal({...p,...x}));
test('Normal form and exact fixed price',()=>{assert.equal(fp.amount,'4900.00');assert.equal(fp.product_slug,'express-review');});
test('Second allowed service',()=>assert.equal(form({...raw,'Услуга':'AI-аудит процесса','Сумма':14900}).product_slug,'ai-audit'));
test('Retry original form keeps same ID',()=>assert.equal(hashed(form(clone(raw))).request_id,base.request_id));
test('New submittedAt changes ID',()=>assert.notEqual(hashed(form({...raw,submittedAt:'2026-10-27T19:41:00.000Z'})).request_id,base.request_id));
test('Decimal comma normalized',()=>assert.equal(form({...raw,'Сумма':'4900,00'}).amount,'4900.00'));
test('Unknown service rejected',()=>badForm({'Услуга':'Произвольный платёж'}));
test('Wrong amount rejected',()=>badForm({'Сумма':10}));
test('Excess decimal precision rejected',()=>badForm({'Сумма':'4900.001'}));
test('Invalid number rejected',()=>{for(const x of ['Infinity','NaN','',null])badForm({'Сумма':x});});
test('Malformed email rejected',()=>badForm({'Электронная почта':'bad-email'}));
test('CRLF email injection rejected',()=>badForm({'Электронная почта':'a@example.com\r\nBcc:b@example.com'}));
test('Multiple recipients rejected',()=>badForm({'Электронная почта':'a@example.com,b@example.com'}));
test('Required contact enforced',()=>badForm({'Контакт':' '}));
test('Contact matches portal 120-character bound',()=>badForm({'Контакт':'я'.repeat(121)}));
test('Unicode code-point length honored',()=>{assert.equal([...form({...raw,'Имя':'😊'.repeat(120)}).client_name].length,120);badForm({'Имя':'😊'.repeat(121)});});
test('Lone surrogate rejected',()=>badForm({'Имя':'broken\uD800'}));
test('Control character rejected',()=>badForm({'Имя':'Тест\u0000'}));
test('Long comment rejected',()=>badForm({'Комментарий клиента':'я'.repeat(2001)}));
test('Missing submission time rejected',()=>badForm({submittedAt:undefined}));
test('Invalid submission time rejected',()=>badForm({submittedAt:'yesterday'}));
test('Actual AI code accepts six valid fields',()=>assert.deepEqual(checked.portal_payload.analysis,a));
test('AI wrong amount rejected',()=>badAi({amount:'10.00'}));
test('AI extra key rejected',()=>badAi({payment_url:'https://attacker.example/'}));
test('AI altered name rejected',()=>badAi({client_name:'Другой клиент'}));
test('AI altered service rejected',()=>badAi({request_type:'AI-аудит процесса'}));
test('AI invalid priority rejected',()=>badAi({priority:'urgent'}));
test('AI injected link rejected',()=>badAi({request_summary:'Оплатить https://attacker.example/'}));
test('AI injected HTML rejected',()=>badAi({payment_description:'<script>alert(1)</script>'}));
test('AI executable URI rejected',()=>badAi({payment_description:'javascript:alert(1)'}));
test('AI missing field rejected',()=>{const x=clone(a);delete x.priority;assert.throws(()=>ai(response(x)));});
test('AI empty field rejected',()=>badAi({request_summary:' '}));
test('AI malformed JSON rejected',()=>assert.throws(()=>ai({choices:[{finish_reason:'stop',message:{content:'{broken'}}]})));
test('Truncated AI output rejected',()=>assert.throws(()=>ai({choices:[{finish_reason:'length',message:{content:JSON.stringify(a)}}]})));
test('Model refusal rejected',()=>assert.throws(()=>ai({choices:[{finish_reason:'stop',message:{content:JSON.stringify(a),refusal:'refused'}}]})));
test('HTTP AI expression sends schema and minimizes PII',()=>{
 const b=JSON.parse(expr(nodes.get('ИИ — обработать заявку').parameters.jsonBody,base,refsAi));
 assert.equal(b.model,'openai/gpt-4.1-mini');assert.equal(b.response_format.type,'json_schema');
 assert.equal(b.provider.require_parameters,true);assert.equal(b.response_format.json_schema.strict,true);
 assert.equal(b.response_format.json_schema.schema.additionalProperties,false);
 const u=JSON.parse(b.messages[1].content);assert.equal(u.amount,'4900.00');
 assert.equal(Object.hasOwn(u,'email'),false);assert.equal(Object.hasOwn(u,'contact'),false);
});
test('Create-order body ignores tampered table result',()=>{
 const b=JSON.parse(expr(nodes.get('Robokassa — создать ссылку').parameters.jsonBody,{amount:'1.00',email:'attacker@example.com'},refsPortal));
 assert.equal(b.amount,'4900.00');assert.equal(b.email,'learner@example.com');assert.equal(Object.keys(b).length,8);
});
test('Portal valid response accepted',()=>{assert.equal(cp.order_id,'81234');assert.equal(cp.status,'Ожидает оплату');});
test('Portal request mismatch rejected',()=>badPortal({request_id:'b'.repeat(64)}));
test('Portal amount mismatch rejected',()=>badPortal({amount:'1.00'}));
test('Portal product mismatch rejected',()=>badPortal({product_slug:'other'}));
test('Foreign payment URL rejected',()=>badPortal({payment_link:'https://attacker.example/orders/pay/'+'a'.repeat(43)+'/'}));
test('URL query or short token rejected',()=>{badPortal({payment_link:link+'?redirect=https://attacker.example/'});badPortal({payment_link:'https://st8dom.ru/orders/pay/short/'});});
test('Invalid order ID rejected',()=>{badPortal({order_id:0});badPortal({order_id:'81234'});});
test('Unknown payment status rejected',()=>badPortal({status:'hopefully_paid'}));
test('Already paid order remains paid in row',()=>assert.equal(portal({...p,status:'paid'}).status,'Оплачен'));
test('Actual refund_processing state recognized',()=>assert.equal(portal({...p,status:'refund_processing'}).status,'Возврат обрабатывается'));
test('Queued mail not claimed delivered',()=>{const x=notify({...p,notification_status:'pending'});assert.equal(x.notification_status,'pending');assert.match(x.completion_message,/поставлено в очередь/);assert.doesNotMatch(x.completion_message,/доставлено/i);});
test('Sent mail described as SMTP acceptance only',()=>{const x=notify({...p,notification_status:'sent'});assert.match(x.completion_message,/Почтовый сервер принял/);assert.doesNotMatch(x.completion_message,/доставлено/i);});
test('Unknown/failed/cancelled mail stops',()=>{for(const s of ['unknown','failed','cancelled','not_queued'])assert.throws(()=>notify({...p,notification_status:s}));});
test('Notification order mismatch rejected',()=>assert.throws(()=>notify({...p,order_id:999,notification_status:'pending'})));
test('Notification changed order status rejected',()=>assert.throws(()=>notify({...p,status:'paid',notification_status:'pending'})));
test('Runtime graph fully connected with valid targets',()=>{
 const seen=new Set(),q=['Форма заявки'];
 while(q.length){const x=q.shift();if(seen.has(x))continue;seen.add(x);for(const a of Object.values(w.connections[x]||{}))for(const b of a)for(const e of b){assert.ok(nodes.has(e.node));q.push(e.node);}}
 assert.equal(seen.size,13);assert.equal(w.nodes.filter(n=>n.type!=='n8n-nodes-base.stickyNote').length,13);
});
test('Named expression references exist and are upstream',()=>{
 const prev=new Set();for(const n of w.nodes.filter(n=>n.type!=='n8n-nodes-base.stickyNote')){
  for(const m of JSON.stringify(n.parameters).matchAll(/\$\(['"]([^'"]+)['"]\)/g)){assert.ok(nodes.has(m[1]));assert.ok(prev.has(m[1]),'Forward reference '+m[1]);}prev.add(n.name);
 }
});
test('All three DataTables use request_id and one assignable table',()=>{
 const tt=w.nodes.filter(n=>n.type==='n8n-nodes-base.dataTable');assert.equal(tt.length,3);
 for(const n of tt){assert.equal(n.parameters.dataTableId.value,'SELECT_TABLE_ID');assert.equal(n.parameters.dataTableId.mode,'id');assert.equal(n.parameters.matchType,'allConditions');assert.equal(n.parameters.filters.conditions[0].keyName,'request_id');assert.equal(n.parameters.filters.conditions[0].condition,'eq');}
});
test('One mail owner and no direct charge/refund/SMTP',()=>{
 assert.equal(w.nodes.filter(n=>n.name==='Email — уведомить клиента').length,1);assert.equal(w.nodes.some(n=>n.type==='n8n-nodes-base.emailSend'),false);
 const urls=w.nodes.filter(n=>n.type==='n8n-nodes-base.httpRequest').map(n=>n.parameters.url);assert.equal(urls.length,3);assert.equal(urls.some(s=>/RefundService|:20327/.test(s)),false);
});
test('Inactive export, no pinned data or embedded secret',()=>{
 assert.equal(w.active,false);assert.equal(Object.hasOwn(w,'pinData'),false);
 assert.doesNotMatch(JSON.stringify(w),/sk-or-v1-|SMTP_PASSWORD|ROBOKASSA_PASSWORD|N8N_ORDERS_API_TOKEN\s*=/);
 for(const n of w.nodes)for(const c of Object.values(n.credentials||{}))assert.equal(c.id,'');
});
console.log('\n'+count+' checks passed. Local unit/contract verification only; actual n8n import and delivery still require testing.');

