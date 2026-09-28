/*
 * <react-component name="SummaryPanel"></react-component>
 *
 * Mounts a migrated React component inside the legacy AngularJS page.
 * Needs dist-bridge/react-bridge.js (window.ReactBridge) loaded first.
 *
 * It translates between the two worlds:
 *   AngularJS $broadcast('expenses:changed')  ->  React prop `version` + 1
 *   React calls props.onChanged()             ->  AngularJS $broadcast('expenses:changed')
 */
angular.module('expenseApp').directive('reactComponent', ['$rootScope', function ($rootScope) {
  return {
    restrict: 'E',
    link: function (scope, element, attrs) {
      var version = 0;

      function props() {
        return {
          version: version,
          onChanged: function () {
            scope.$applyAsync(function () {
              $rootScope.$broadcast('expenses:changed');
            });
          }
        };
      }

      var handle = window.ReactBridge.mount(element[0], attrs.name, props());

      var stopListening = $rootScope.$on('expenses:changed', function () {
        version += 1;
        handle.update(props());
      });

      scope.$on('$destroy', function () {
        stopListening();
        handle.unmount();
      });
    }
  };
}]);
