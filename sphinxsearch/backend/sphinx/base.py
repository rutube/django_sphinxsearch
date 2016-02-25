# coding: utf-8

from django.db.backends.mysql import base, creation


class SphinxOperations(base.DatabaseOperations):
    compiler_module = "sphinxsearch.backend.sphinx.compiler"

    def fulltext_search_sql(self, field_name):
        """ Formats full-text search expression."""
        return 'MATCH (\'@%s "%%s"\')' % field_name

    def force_no_ordering(self):
        """ Fix unsupported syntax "ORDER BY NULL"."""
        return []


class SphinxCreation(creation.DatabaseCreation):

    def create_test_db(self, *args, **kwargs):
        # NOOP, test using regular sphinx database.
        if self.connection.settings_dict.get('TEST_NAME'):
            # initialize connection database name
            test_name = self.connection.settings_dict['TEST_NAME']
            self.connection.close()
            self.connection.settings_dict['NAME'] = test_name
            self.connection.cursor()
            return test_name
        return self.connection.settings_dict['NAME']

    def destroy_test_db(self, *args, **kwargs):
        # NOOP, we created nothing, nothing to destroy.
        return


class DatabaseWrapper(base.DatabaseWrapper):
    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)
        self.ops = SphinxOperations(self)
        self.creation = SphinxCreation(self)
        # The following can be useful for unit testing, with multiple databases
        # configured in Django, if one of them does not support transactions,
        # Django will fall back to using clear/create
        # (instead of begin...rollback) between each test. The method Django
        # uses to detect transactions uses CREATE TABLE and DROP TABLE,
        # which ARE NOT supported by Sphinx, even though transactions ARE.
        # Therefore, we can just set this to True, and Django will use
        # transactions for clearing data between tests when all OTHER backends
        # support it.
        self.features.supports_transactions = True
        self.features.allows_group_by_pk = False
        self.features.uses_savepoints = False
        self.features.supports_column_check_constraints = False
