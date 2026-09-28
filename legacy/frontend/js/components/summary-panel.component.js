/* Summary panel. A 1.5-style component that reloads whenever expenses change. */
angular.module('expenseApp').component('summaryPanel', {
  templateUrl: 'templates/summary-panel.html',
  controller: ['$scope', 'ExpenseService', function ($scope, ExpenseService) {
    var ctrl = this;

    function load() {
      ExpenseService.summary().then(function (summary) {
        ctrl.summary = summary;
      });
    }

    ctrl.$onInit = load;
    $scope.$on('expenses:changed', load);
  }]
});
