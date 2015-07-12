# coding: utf-8
import re
from django.core.exceptions import FieldError
from django.db import models
from django.db.models import Q
from django.db.models.lookups import Search, Exact

from django.db.models.sql import compiler, AND

# from django.db.models.sql.expressions import SQLEvaluator
#
# DJANGO15 = (1, 5, 0, 'alpha', 0)
# DJANGO16 = (1, 6, 0, 'alpha', 0)
#
#
from django.db.models.sql.constants import ORDER_DIR
from django.db.models.sql.query import get_order_dir

from django.utils import six
from sphinxsearch.sql import SphinxWhereNode, SphinxExtraWhere
from sphinxsearch.utils import sphinx_escape


class SphinxQLCompiler(compiler.SQLCompiler):

    def compile(self, node, select_format=False):
        sql, params = super(SphinxQLCompiler, self).compile(node, select_format)
        if isinstance(node, Search):
            search_text = sphinx_escape(params[0])
            sql = sql % search_text
            params = []

        return sql, params

    # def get_columns(self, *args, **kwargs):
    #     result = columns = super(SphinxQLCompiler, self).get_columns(*args, **kwargs)
    #     if django.VERSION < DJANGO16:
    #         columns = result
    #     else:
    #         columns = result[0]
    #     db_table = self.query.model._meta.db_table
    #     for i, column in enumerate(columns):
    #         if column.startswith(db_table + '.'):
    #             column = column.partition('.')[2]
    #         # fix not accepted expression (bool(value)) AS v
    #         columns[i] = re.sub(r"^\((.*)\) AS ([\w\d\_]+)$", '\\1 AS \\2',
    #                             column)
    #     return result

    def get_group_by(self, select, order_by):
        res = super(SphinxQLCompiler, self).get_group_by(select, order_by)
        group_by = getattr(self.query, 'group_by', None)
        if group_by:
            return [r for r in res if r[0] in group_by]
        return res

    def _serialize(self, values_list):
        if isinstance(values_list, six.string_types):
            return values_list
        ensure_list = lambda s:  [s] if isinstance(s, six.string_types) else s
        values_list = [item for s in values_list for item in ensure_list(s)]
        positive_list = filter(lambda s: not s.startswith('-'), values_list)
        negative_list = filter(lambda s: s.startswith('-'), values_list)
        def quote(s, negative=True):
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

        positive = "|".join(map(quote, positive_list))
        if not positive_list:
            negative = '|'.join(quote(n, negative=False) for n in negative_list)
            template = '%s -(%s)'
        else:
            negative = ' '.join(map(quote, negative_list))
            template = '%s %s'
        result = template % (positive.strip(' '), negative.strip(' '))
        return result.strip(' ')

    def as_sql(self, with_limits=True, with_col_aliases=False):
        """ Patching final SQL query."""
        self.query = self.query.clone()
        where, self.query.where = self.query.where, SphinxWhereNode()
        match = getattr(self.query, 'match', None)
        if match:
            self._add_match_extra(match)
        self.query.match = dict()

        qn = self.quote_name_unless_alias
        connection = self.connection

        where_sql, where_params = where.as_sql(self, connection)
        if where_sql:
            self.query.add_extra(
                {'__where_result': where_sql}, where_params,
                ['__where_result = %s'], (True,), None, None)


        sql, args = super(SphinxQLCompiler, self).as_sql(with_limits,
                                                         with_col_aliases)
        if (sql, args) == ('', ()):
            return sql, args
        # removing unsupported OFFSET clause
        # replacing it with LIMIT <offset>, <limit>
        sql = re.sub(r'LIMIT ([\d]+) OFFSET ([\d]+)$', 'LIMIT \\2, \\1', sql)

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
        sql = re.sub(r'GROUP BY (([\w\d_]+)(, [\w\d_]+)*)', group_by, sql)

        # adding sphinx OPTION clause
        # TODO: syntax check for option values is not performed
        options = getattr(self.query, 'options', None)
        if options:
            sql += ' OPTION %s' % ', '.join(
                ["%s=%s" % i for i in options.items()]) or ''
    #
    #     # percents, added by raw formatting queries, escaped as %%
    #     sql = re.sub(r'(%[^s])', '%%\1', sql)
    #     if isinstance(sql, six.binary_type):
    #         sql = sql.decode("utf-8")
        e = self.connection.connection.literal
        print (sql % tuple(e(a) for a in args))
        return sql, args

    def get_group_ordering(self):
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
        expression = []
        all_field_expr = []
        all_fields_lookup = match.get('*')
        if all_fields_lookup:
            if isinstance(all_fields_lookup, six.string_types):
                expression.append(all_fields_lookup)
                all_field_expr.append(all_fields_lookup)
            else:
                for value in all_fields_lookup:
                    value_str = self._serialize(value)
                    expression.append(value_str)
                    all_field_expr.append(value_str)
        for sphinx_attr, lookup in match.items():
            if sphinx_attr == '*':
                continue
            field = self.query.model._meta.get_field(sphinx_attr)
            db_column = field.db_column or field.attname
            expression.append('@' + db_column)
            expression.append("(%s)" % self._serialize(lookup))
        decode = lambda _: _.decode("utf-8") if type(
            _) is six.binary_type else _
        match_expr = u"MATCH('%s')" % u' '.join(map(decode, expression))
        self.query.where.add(SphinxExtraWhere([match_expr], []), AND)


# Set SQLCompiler appropriately, so queries will use the correct compiler.
SQLCompiler = SphinxQLCompiler


class SQLInsertCompiler(compiler.SQLInsertCompiler, SphinxQLCompiler):
    pass


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SphinxQLCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SphinxQLCompiler):
    def as_sql(self):
        node = self.is_single_row_update()
        need_replace = False
        if node:
            need_replace = self.has_string_attrs()
        if node and need_replace:
            sql, args = self.as_replace(node)
        else:
            sql, args = super(SQLUpdateCompiler, self).as_sql()
        # e = self.connection.connection.literal
        # print (sql % tuple(e(a) for a in args))

        return sql, args

    def is_single_row_update(self):
        where = self.query.where
        node = None
        if len(where.children) == 1:
            node = where.children[0]
        if not isinstance(node, Exact):
            node = None
        if not node.lhs.field.primary_key:
            node = None
        return node

    def as_replace(self, where_node):
        """
        Performs single-row UPDATE as REPLACE INTO query.

        Must be used to change string attributes or indexed fields.
        """
        self.pre_sql_setup()
        if not self.query.values:
            return '', ()
        table = self.query.tables[0]
        qn = self.quote_name_unless_alias
        result = ['REPLACE INTO %s' % qn(table)]
        meta = self.query.model._meta
        self.query.values.append((meta.pk, self.query.model, where_node.rhs))
        columns, values, update_params = [], [], []

        for field, model, val in self.query.values:
            if hasattr(val, 'resolve_expression'):
                val = val.resolve_expression(self.query, allow_joins=False, for_save=True)
                if val.contains_aggregate:
                    raise FieldError("Aggregate functions are not allowed in this query")
            elif hasattr(val, 'prepare_database_save'):
                if field.rel:
                    val = field.get_db_prep_save(
                        val.prepare_database_save(field),
                        connection=self.connection,
                    )
                else:
                    raise TypeError("Database is trying to update a relational field "
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

    def has_string_attrs(self):
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
#
#
# class SQLDateCompiler(compiler.SQLDateCompiler, SphinxQLCompiler):
#     pass
