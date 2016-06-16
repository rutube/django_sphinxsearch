# coding: utf-8
from collections import OrderedDict
import re
from django.core.exceptions import FieldError
from django.db import models
from django.db.models.expressions import Random
from django.db.models.lookups import Search, Exact
from django.db.models.sql import compiler, AND
from django.db.models.sql.constants import ORDER_DIR
from django.db.models.sql.query import get_order_dir

from django.utils import six
from sphinxsearch import sql as sqls
from sphinxsearch.utils import sphinx_escape


class SphinxQLCompiler(compiler.SQLCompiler):
    # Options names that are not escaped by compiler. Don't pass user input
    # there.
    safe_options = ('ranker', 'field_weights', 'index_weights')

    def compile(self, node, select_format=False):
        sql, params = super(SphinxQLCompiler, self).compile(node, select_format)

        # substitute MATCH() arguments with sphinx-escaped params
        if isinstance(node, Search):
            search_text = sphinx_escape(params[0])
            sql = sql % search_text
            params = []

        return sql, params

    def get_order_by(self):
        res = super(SphinxQLCompiler, self).get_order_by()

        order_by = []
        for expr, params in res:
            if isinstance(expr.expression, Random):
                # Replacing ORDER BY RAND() ASC to ORDER BY RAND()
                assert params[0] == 'RAND() ASC', "Expected ordering clause"
                params = ('RAND()',) + params[1:]
            order_by.append((expr, params))
        return order_by

    def get_group_by(self, select, order_by):
        res = super(SphinxQLCompiler, self).get_group_by(select, order_by)

        # override GROUP BY columns for sphinxsearch's "GROUP N BY" support
        group_by = getattr(self.query, 'group_by', None)
        if group_by:
            fields = self.query.model._meta.fields
            field_columns = [f.column for f in fields if f.attname in group_by]
            return [r for r in res if r[0] in field_columns]

        return res

    @staticmethod
    def _quote(s, negative=True):
        """ Adds quotes and negates to match lookup expressions."""
        prefix = '-' if negative else ''
        if s.startswith('"'):
            return s
        negative = s.startswith('-')
        if not negative:
            return '"%s"' % s
        s = s[1:]
        if s.startswith('"'):
            return '%s%s' % (prefix, s)
        return '%s"%s"' % (prefix, s)

    def _serialize(self, values_list):
        """ Serializes list of sphinx MATCH lookup expressions

        :param values_list: list of match lookup expressions
        :type values_list: str, list, tuple
        :return: MATCH expression
        :rtype: str
        """""
        if isinstance(values_list, six.string_types):
            return values_list
        ensure_list = lambda s:  [s] if isinstance(s, six.string_types) else s
        values_list = [item for s in values_list for item in ensure_list(s)]
        positive_list = filter(lambda s: not s.startswith('-'), values_list)
        negative_list = filter(lambda s: s.startswith('-'), values_list)

        positive = "|".join(map(self._quote, positive_list))
        if not positive_list:
            negative = '|'.join(self._quote(n, negative=False)
                                for n in negative_list)
            template = '%s -(%s)'
        else:
            negative = ' '.join(map(self._quote, negative_list))
            template = '%s %s'
        result = template % (positive.strip(' '), negative.strip(' '))
        return result.strip(' ')

    def as_sql(self, with_limits=True, with_col_aliases=False, subquery=False):
        """ Patching final SQL query."""
        where, self.query.where = self.query.where, sqls.SphinxWhereNode()
        match = getattr(self.query, 'match', None)
        if match:
            # add match extra where
            self._add_match_extra(match)

        connection = self.connection

        where_sql, where_params = where.as_sql(self, connection)
        # moving where conditions to SELECT clause because of better support
        # of SQL expressions in sphinxsearch.

        if where_sql:
            # Without annotation queryset.count() receives 1 as where_result
            # and count it as aggregation result.
            self.query.add_annotation(
                sqls.SphinxWhereExpression(where_sql, where_params),
                '__where_result')
            # almost all where conditions are now in SELECT clause, so
            # WHERE should contain only test against that conditions are true
            self.query.add_extra(
                None, None,
                ['__where_result = %s'], (True,), None, None)

        sql, args = super(SphinxQLCompiler, self).as_sql(with_limits,
                                                         with_col_aliases)

        # empty SQL doesn't need patching
        if (sql, args) == ('', ()):
            return sql, args

        # removing unsupported by sphinxsearch OFFSET clause
        # replacing it with LIMIT <offset>, <limit>
        sql = re.sub(r'LIMIT (\d+) OFFSET (\d+)$', 'LIMIT \\2, \\1', sql)

        # patching GROUP BY clause
        group_limit = getattr(self.query, 'group_limit', '')
        group_by_ordering = self.get_group_ordering()
        if group_limit:
            # add GROUP <N> BY expression
            group_by = 'GROUP %s BY \\1' % group_limit
        else:
            group_by = 'GROUP BY \\1'
        if group_by_ordering:
            # add WITHIN GROUP ORDER BY expression
            group_by += group_by_ordering
        sql = re.sub(r'GROUP BY ((\w+)(, \w+)*)', group_by, sql)

        # adding sphinxsearch OPTION clause
        options = getattr(self.query, 'options', None)
        if options:
            keys = sorted(options.keys())
            values = [options[k] for k in keys if k not in self.safe_options]

            opts = []
            for k in keys:
                if k in self.safe_options:
                    opts.append("%s=%s" % (k, options[k]))
                else:
                    opts.append("%s=%%s" % k)
            sql += ' OPTION %s' % ', '.join(opts) or ''
            args += tuple(values)
        return sql, args

    def get_group_ordering(self):
        """ Returns group ordering clause.

        Formats WITHIN GROUP ORDER BY expression
        with columns in query.group_order_by
        """
        group_order_by = getattr(self.query, 'group_order_by', ())
        asc, desc = ORDER_DIR['ASC']
        if not group_order_by:
            return ''
        result = []
        for order_by in group_order_by:
            col, order = get_order_dir(order_by, asc)
            result.append("%s %s" % (col, order))
        return " WITHIN GROUP ORDER BY " + ", ".join(result)

    def _add_match_extra(self, match):
        """ adds MATCH clause to query.where """
        expression = []
        all_field_expr = []
        all_fields_lookup = match.get('*')

        # format expression to MATCH against any indexed fields
        if all_fields_lookup:
            if isinstance(all_fields_lookup, six.string_types):
                expression.append(all_fields_lookup)
                all_field_expr.append(all_fields_lookup)
            else:
                for value in all_fields_lookup:
                    value_str = self._serialize(value)
                    expression.append(value_str)
                    all_field_expr.append(value_str)

        # format expressions to MATCH against concrete fields
        for sphinx_attr, lookup in match.items():
            if sphinx_attr == '*':
                continue
            # noinspection PyProtectedMember
            field = self.query.model._meta.get_field(sphinx_attr)
            db_column = field.db_column or field.attname
            expression.append('@' + db_column)
            expression.append("(%s)" % self._serialize(lookup))

        # handle non-ascii characters in search expressions
        decode = lambda _: _.decode("utf-8") if type(
            _) is six.binary_type else _
        match_expr = u"MATCH('%s')" % u' '.join(map(decode, expression))

        # add MATCH() to query.where
        self.query.where.add(sqls.SphinxExtraWhere([match_expr], []), AND)


# Set SQLCompiler appropriately, so queries will use the correct compiler.
SQLCompiler = SphinxQLCompiler


class SQLInsertCompiler(compiler.SQLInsertCompiler, SphinxQLCompiler):
    pass


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SphinxQLCompiler):
    def as_sql(self):
        sql, params = super(SQLDeleteCompiler, self).as_sql()

        # empty SQL doesn't need patching
        if (sql, params) == ('', ()):
            return sql, params

        sql = re.sub(r'\(IN\((\w+),\s([\w\s\%,]+)\)\)', '\\1 IN (\\2)', sql)
        return sql, params


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SphinxQLCompiler):

    # noinspection PyMethodOverriding
    def as_sql(self):
        node = self.is_single_row_update()
        # determine whether use UPDATE (only fixed-length fields) or
        # REPLACE (internal delete + insert) syntax
        need_replace = False
        if node:
            need_replace = self._has_string_fields()
        if node and need_replace:
            sql, args = self.as_replace(node)
        else:

            match = getattr(self.query, 'match', None)
            if match:
                # add match extra where
                self._add_match_extra(match)

            sql, args = super(SQLUpdateCompiler, self).as_sql()
        return sql, args

    def is_single_row_update(self):
        where = self.query.where
        match = getattr(self.query, 'match', {})
        node = None
        if len(where.children) == 1:
            node = where.children[0]
        elif match:
            meta = self.query.model._meta
            pk_match = match.get(meta.pk.attname)
            if pk_match is not None:
                pk_value = list(pk_match.dict.keys())[0]
                return Exact(meta.pk.get_col(meta.db_table), pk_value)
        if not isinstance(node, Exact):
            node = None
        elif not node.lhs.field.primary_key:
            node = None
        return node

    def as_replace(self, where_node):
        """
        Performs single-row UPDATE as REPLACE INTO query.

        Must be used to change string attributes or indexed fields.
        """

        # It's a copy of compiler.SQLUpdateCompiler.as_sql method
        # that formats query more like INSERT than UPDATE
        self.pre_sql_setup()
        if not self.query.values:
            return '', ()
        table = self.query.tables[0]
        qn = self.quote_name_unless_alias
        result = ['REPLACE INTO %s' % qn(table)]
        # noinspection PyProtectedMember
        meta = self.query.model._meta
        self.query.values.append((meta.pk, self.query.model, where_node.rhs))
        columns, values, update_params = [], [], []

        for field, model, val in self.query.values:
            if hasattr(val, 'resolve_expression'):
                val = val.resolve_expression(self.query, allow_joins=False,
                                             for_save=True)
                if val.contains_aggregate:
                    raise FieldError(
                        "Aggregate functions are not allowed in this query")
            elif hasattr(val, 'prepare_database_save'):
                if field.rel:
                    val = field.get_db_prep_save(
                        val.prepare_database_save(field),
                        connection=self.connection,
                    )
                else:
                    raise TypeError(
                        "Database is trying to update a relational field "
                        "of type %s with a value of type %s. Make sure "
                        "you are setting the correct relations" %
                        (field.__class__.__name__, val.__class__.__name__))
            else:
                val = field.get_db_prep_save(val, connection=self.connection)

            # Getting the placeholder for the field.
            if hasattr(field, 'get_placeholder'):
                placeholder = field.get_placeholder(val, self, self.connection)
            else:
                placeholder = '%s'
            name = field.column
            columns.append(qn(name))
            if hasattr(val, 'as_sql'):
                sql, params = self.compile(val)
                values.append(sql)
                update_params.extend(params)
            elif val is not None:
                values.append(placeholder)
                update_params.append(val)
            else:
                values.append('NULL')
        if not values:
            return '', ()
        result.append('(')
        result.append(', '.join(columns))
        result.append(') VALUES (')
        result.append(', '.join(values))
        result.append(')')
        return ' '.join(result), tuple(update_params)

    def _has_string_fields(self):
        """ check whether query is updating text fields."""
        _excluded_update_fields = (
            models.CharField,
            models.TextField
        )
        for field, model, val in self.query.values:
            if isinstance(field, _excluded_update_fields):
                return True
        return False


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SphinxQLCompiler):
    pass
