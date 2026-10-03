const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
class Element {
  constructor() { this.handlers={};this.hidden=false;this.textContent='';this.value='0'; }
  addEventListener(name, fn) { this.handlers[name]=fn; }
  fire(name) { this.handlers[name](); }
}
const elements={};
for(const name of ['select','input','result','output','placeholder','status','reset','run']) elements[name]=new Element();
const examples=[{label:'Первый',input:'Вход 1',result:'Результат 1'}, {label:'Второй',input:'Вход 2',result:'<script>bad</script>'}];
const root={querySelector(selector){return elements[selector.match(/data-demo-(\w+)/)[1]];}};
const data={textContent:JSON.stringify(examples)};
const document={querySelector(){return root;},getElementById(){return data;}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/js/project-demos.js'),'utf8'),{document});
elements.run.fire('click');assert.equal(elements.output.textContent,'Результат 1');assert.equal(elements.result.hidden,false);
elements.select.value='1';elements.select.fire('change');assert.equal(elements.input.textContent,'Вход 2');assert.equal(elements.output.textContent,'');assert(elements.result.hidden);
elements.run.fire('click');assert.equal(elements.output.textContent,'<script>bad</script>');
elements.reset.fire('click');assert(elements.result.hidden);assert.equal(elements.output.textContent,'');
console.log('Demo UI: result, scenario change, reset and plain-text output verified.');
