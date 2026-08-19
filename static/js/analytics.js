/**
 * Точка подключения аналитики.
 * Пока ANALYTICS_ID пуст, события копятся в window.dataLayer и не уходят наружу.
 * Когда появится идентификатор (например Яндекс.Метрика), замените заглушку ниже.
 */
(function () {
  "use strict";
  window.st8domAnalytics = function (eventName, payload) {
    if (!window.ST8DOM_ANALYTICS_ID) {
      return;
    }
    // Пример: ym(window.ST8DOM_ANALYTICS_ID, 'reachGoal', eventName, payload);
    console.debug("[analytics]", eventName, payload || {});
  };
})();
