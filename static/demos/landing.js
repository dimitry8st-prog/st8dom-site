document.querySelectorAll('.hamb, .menuButton').forEach(function(button){
  const nav=document.querySelector('nav');
  button.addEventListener('click',function(){const open=nav.classList.toggle('open');button.setAttribute('aria-expanded',String(open));});
  nav.querySelectorAll('a').forEach(function(a){a.addEventListener('click',function(){nav.classList.remove('open');button.setAttribute('aria-expanded','false');});});
});
document.querySelectorAll('[data-service-tab]').forEach(function(button){button.addEventListener('click',function(){
  document.querySelectorAll('[data-service-tab]').forEach(function(b){const selected=b===button;b.classList.toggle('active',selected);b.setAttribute('aria-selected',String(selected));});
  document.querySelectorAll('[data-service-panel]').forEach(function(p){p.hidden=p.getAttribute('data-service-panel')!==button.getAttribute('data-service-tab');});
});});
document.querySelectorAll('.faqItem button').forEach(function(button){button.addEventListener('click',function(){const p=button.parentElement.querySelector('p');p.hidden=!p.hidden;button.setAttribute('aria-expanded',String(!p.hidden));button.querySelector('b').textContent=p.hidden?'+':'−';});});
