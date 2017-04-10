# coding: utf-8

from django.db.backends.mysql import base, creation
from django.db.backends.mysql.base import server_version_re
from django.utils.functional import cached_property


class SphinxOperations(base.DatabaseOperations):

    def regex_lookup(self, lookup_type):
        raise NotImplementedError()

    compiler_module = "sphinxsearch.backend.sphinx.compiler"

    def fulltext_search_sql(self, field_name):
        """ Formats full-text search expression."""
        return 'MATCH (\'@%s "%%s"\')' % field_name

    def force_no_ordering(self):
        """ Fix unsupported syntax "ORDER BY NULL"."""
        return []


class SphinxValidation(base.DatabaseValidation):
    def _check_sql_mode(self, **kwargs):
        """ Disable sql_mode validation because it's unsupported
        >>> import django.db
        >>> cursor = django.db.connection
        >>> cursor.execute("SELECT @@sql_mode")
        # Error here after parsing searchd response
        """
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


class SphinxFeatures(base.DatabaseFeatures):
    # The following can be useful for unit testing, with multiple databases
    # configured in Django, if one of them does not support transactions,
    # Django will fall back to using clear/create
    # (instead of begin...rollback) between each test. The method Django
    # uses to detect transactions uses CREATE TABLE and DROP TABLE,
    # which ARE NOT supported by Sphinx, even though transactions ARE.
    # Therefore, we can just set this to True, and Django will use
    # transactions for clearing data between tests when all OTHER backends
    # support it.
    supports_transactions = True
    allows_group_by_pk = False
    uses_savepoints = False
    supports_column_check_constraints = False
    is_sql_auto_is_null_enabled = False


class DatabaseWrapper(base.DatabaseWrapper):
    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)
        self.ops = SphinxOperations(self)
        self.creation = SphinxCreation(self)
        self.features = SphinxFeatures(self)
        self.validation = SphinxValidation(self)

    def _start_transaction_under_autocommit(self):
        raise NotImplementedError()

    @cached_property
    def mysql_version(self):
        # Django>=1.10 makes if differently
        with self.temporary_connection():
            server_info = self.connection.get_server_info()
        match = server_version_re.match(server_info)
        if not match:
            raise Exception('Unable to determine MySQL version from version '
                            'string %r' % server_info)
        return tuple(int(x) for x in match.groups())
