/* "Add expense" form. Classic directive with an isolated scope and a link function. */
angular.module('expenseApp').directive('expenseForm', ['$rootScope', '$filter', 'ExpenseService',
  function ($rootScope, $filter, ExpenseService) {
    return {
      restrict: 'E',
      scope: {},
      templateUrl: 'templates/expense-form.html',
      link: function (scope) {
        scope.categories = ['Food', 'Travel', 'Bills', 'Shopping'];

        function blank() {
          var today = new Date();
          today.setHours(0, 0, 0, 0);
          return { title: '', amount: null, category: 'Food', date: today };
        }

        scope.draft = blank();
        scope.saving = false;
        scope.serverError = null;

        scope.submit = function (form) {
          if (form.$invalid) {
            return;
          }
          scope.saving = true;
          scope.serverError = null;

          var payload = {
            title: scope.draft.title,
            amount: scope.draft.amount,
            category: scope.draft.category,
            date: $filter('date')(scope.draft.date, 'yyyy-MM-dd')
          };

          ExpenseService.add(payload).then(function () {
            scope.draft = blank();
            form.$setPristine();
            form.$setUntouched();
            $rootScope.$broadcast('expenses:changed');
          }, function (res) {
            scope.serverError = (res.data && res.data.error) || 'Could not save expense';
          })['finally'](function () {
            scope.saving = false;
          });
        };
      }
    };
  }
]);
