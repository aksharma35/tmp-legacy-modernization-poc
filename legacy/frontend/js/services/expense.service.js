/* Talks to the Flask API. Every other piece of the app goes through here. */
angular.module('expenseApp').factory('ExpenseService', ['$http', function ($http) {
  function data(res) { return res.data; }

  return {
    list: function () {
      return $http.get('/api/expenses').then(data);
    },
    add: function (expense) {
      return $http.post('/api/expenses', expense).then(data);
    },
    remove: function (id) {
      return $http['delete']('/api/expenses/' + id);
    },
    summary: function () {
      return $http.get('/api/summary').then(data);
    }
  };
}]);
