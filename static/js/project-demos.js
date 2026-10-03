(function () {
  'use strict';
  const root = document.querySelector('[data-project-demo]');
  const data = document.getElementById('demo-examples');
  if (!root || !data) return;
  const examples = JSON.parse(data.textContent);
  const select = root.querySelector('[data-demo-select]');
  const input = root.querySelector('[data-demo-input]');
  const result = root.querySelector('[data-demo-result]');
  const output = root.querySelector('[data-demo-output]');
  const placeholder = root.querySelector('[data-demo-placeholder]');
  const status = root.querySelector('[data-demo-status]');
  function current() { return examples[Number(select.value)] || examples[0]; }
  function reset() {
    input.textContent = current().input;
    output.textContent = '';
    result.hidden = true;
    placeholder.hidden = false;
    status.textContent = 'Выбран пример: ' + current().label;
  }
  select.addEventListener('change', reset);
  root.querySelector('[data-demo-reset]').addEventListener('click', reset);
  root.querySelector('[data-demo-run]').addEventListener('click', function () {
    output.textContent = current().result;
    result.hidden = false;
    placeholder.hidden = true;
    status.textContent = 'Учебный результат показан. Рабочие сервисы не вызывались.';
  });
})();
