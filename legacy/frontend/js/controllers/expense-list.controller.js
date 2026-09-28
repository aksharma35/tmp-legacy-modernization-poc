/* Expense list: search, sort and delete. Old-style controller on $scope. */
angular.module('expenseApp').controller('ExpenseListCtrl', ['$scope', '$rootScope', '$window', 'ExpenseService',
  function ($scope, $rootScope, $window, ExpenseService) {
    $scope.expenses = [];
    $scope.query = '';
    $scope.sortOptions = [
      { value: '-date', label: 'Newest first' },
      { value: 'date', label: 'Oldest first' },
      { value: '-amount', label: 'Highest amount' },
      { value: 'amount', label: 'Lowest amount' }
    ];
    $scope.sortField = '-date';

    function load() {
      ExpenseService.list().then(function (expenses) {
        $scope.expenses = expenses;
      });
    }

    // Show the "Clear" button only while a search is active.
    $scope.$watch('query', function (q) {
      $scope.searching = !!q;
    });

    $scope.clearSearch = function () {
      $scope.query = '';
    };

    $scope.remove = function (expense) {
      if (!$window.confirm('Delete "' + expense.title + '"?')) {
        return;
      }
      ExpenseService.remove(expense.id).then(function () {
        $rootScope.$broadcast('expenses:changed');
      });
    };

    $scope.$on('expenses:changed', load);
    load();
  }
]);
