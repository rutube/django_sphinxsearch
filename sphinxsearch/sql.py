# coding: utf-8

# $Id: $
from collections import OrderedDict
import functools
from django.db import models
from django.db.models import Count, BooleanField
from django.db.models.base import ModelBase
from django.db.models.expressions import Col, Func, BaseExpression
from django.db.models.sql import Query
from django.db.models.sql.where import WhereNode, ExtraWhere
from django.utils.datastructures import OrderedSet


class SphinxCount(Count):
    """ Replaces Mysql-like COUNT('*') with COUNT(*) token."""
    template = '%(function)s(*)'

    def as_sql(self, compiler, connection, function=None, template=None):
        sql, params = super(SphinxCount, self).as_sql(
            compiler, connection, function=function, template=template)
        params.remove('*')
        return sql, params


class SphinxWhereExpression(BaseExpression):
    def __init__(self, where, where_params):
        self.where = where
        self.where_params = where_params
        super(SphinxWhereExpression, self).__init__(output_field=BooleanField())
    #
    # def resolve_expression(self, query=None, allow_joins=True, reuse=None, summarize=False, for_save=False):
    #     return self

    def as_sql(self, compiler, connection):
        return self.where, self.where_params


class SphinxExtraWhere(ExtraWhere):

    def as_sql(self, qn=None, connection=None):
        sqls = ["%s" % sql for sql in self.sqls]
        return " AND ".join(sqls), tuple(self.params or ())


class SphinxWhereNode(WhereNode):
    # def sql_for_columns(self, data, qn, connection, field_internal_type=None):
    #     table_alias, name, db_type = data
    #     if django.get_version() < "1.6":
    #         return connection.ops.field_cast_sql(db_type) % name
    #     return connection.ops.field_cast_sql(db_type, field_internal_type) % name

    def make_atom(self, child, qn, connection):
        """
        Transform search, the keyword should not be quoted.
        """
        return super(WhereNode, self).make_atom(child, qn, connection)
        lvalue, lookup_type, value_annot, params_or_value = child
        sql, params = super(SphinxWhereNode, self).make_atom(child, qn, connection)
        if lookup_type == 'search':
            if hasattr(lvalue, 'process'):
                try:
                    lvalue, params = lvalue.process(lookup_type, params_or_value, connection)
                except EmptyShortCircuit:
                    raise EmptyResultSet
            if isinstance(lvalue, tuple):
                # A direct database column lookup.
                field_sql = self.sql_for_columns(lvalue, qn, connection)
            else:
                # A smart object with an as_sql() method.
                field_sql = lvalue.as_sql(qn, connection)
            # TODO: There are a couple problems here.
            # 1. The user _might_ want to search only a specific field.
            # 2. However, since Django requires a field name to use the __search operator
            #    There is no way to do a search in _all_ fields.
            # 3. Because, using multiple __search operators is not supported.
            # So, we need to merge multiped __search operators into a single MATCH(), we
            # can't do that here, we have to do that one level up...
            # Ignore the field name, search all fields:
            params = ('@* %s' % params[0], )
            # _OR_ respect the field name, and search on it:
            #params = ('@%s %s' % (field_sql, params[0]), )
        if self._real_negated:
            col = lvalue.col
            if lookup_type == 'exact':
                sql = '%s <> %%s' % col
            elif lookup_type == 'in':
                params_placeholder = '(%s)' % (', '.join(['%s'] * len(params)))
                sql = '%s NOT IN %s' % (col, params_placeholder)
            else:
                raise ValueError("Negative '%s' lookup not supported" % lookup_type)
        return sql, params

    # def as_sql(self, qn, connection):
    #     if not hasattr(self, '_real_negated'):
    #         self._real_negated = self.negated
    #     # don't allow Django to add unsupported NOT (...) before all lookups
    #     self.negated = False
    #     # pass-through real negated value (OR connector not supported)
    #     if self._real_negated:
    #         for child in self.children:
    #             if type(child) is tuple:
    #                 child[0]._real_negated = True
    #             else:
    #                 child._real_negated = True
    #     sql_string, result_params = super(SphinxWhereNode, self).as_sql(qn, connection)
    #     self.negated = self._real_negated
    #     return sql_string, result_params



class SphinxQuery(Query):
    _clonable = ('options', 'match', 'group_limit', 'group_order_by',
                 'with_meta')
    #
    # aggregates_module = sphinx_aggregates
    #

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('where', SphinxWhereNode)
        super(SphinxQuery, self).__init__(*args, **kwargs)

    def clone(self, klass=None, memo=None, **kwargs):
        query = super(SphinxQuery, self).clone(klass=klass, memo=memo, **kwargs)
        for attr_name in self._clonable:
            value = getattr(self, attr_name, None)
            if value:
                setattr(query, attr_name, value)
        return query

    def add_match(self, *args, **kwargs):
        if not hasattr(self, 'match'):
            self.match = OrderedDict()
        for expression in args:
            self.match.setdefault('*', OrderedSet())
            if isinstance(expression, (list, tuple)):
                self.match['*'].update(expression)
            else:
                self.match['*'].add(expression)
        for field, expression in kwargs.items():
            self.match.setdefault(field, OrderedSet())
            if isinstance(expression, (list, tuple, set)):
                self.match[field].update(expression)
            else:
                self.match[field].add(expression)


    # def __str__(self):
    #     def to_str(text):
    #         if type(text) is unicode:
    #             # u'тест' => '\xd1\x82\xd0\xb5\xd1\x81\xd1\x82'
    #             return text.encode('utf-8')
    #         else:
    #             # 'тест' => u'\u0442\u0435\u0441\u0442' => '\xd1\x82\xd0\xb5\xd1\x81\xd1\x82'
    #             # 'test123' => 'test123'
    #             return str(text)
    #
    #     compiler = SphinxQLCompiler(self, connection, None)
    #     query, params = compiler.as_sql()
    #
    #     params = tuple(map(lambda p: to_str(p), params))
    #     return to_str(query % params)
    #
    # def __unicode__(self):
    #     compiler = SphinxQLCompiler(self, connection, None)
    #     query, params = compiler.as_sql()
    #     return unicode(query % params)

    def get_count(self, using):
        """
        Performs a COUNT() query using the current filter constraints.
        """
        obj = self.clone()
        obj.add_annotation(SphinxCount('*'), alias='__count', is_summary=True)
        number = obj.get_aggregation(using, ['__count'])['__count']
        if number is None:
            number = 0
        return number


class SphinxCol(Col):
    def as_sql(self, compiler, connection):
        # As column names in SphinxQL couldn't be escaped with `backticks`,
        # simply return column name
        return self.target.column, []


class SphinxModelBase(ModelBase):
    def __new__(cls, name, bases, attrs):
        for attr in attrs.values():
            if isinstance(attr, models.Field):
                col_patched = getattr(attr, '_col_patched', False)
                if not col_patched:
                    cls.patch_col_class(attr)
        return super(SphinxModelBase, cls).__new__(cls, name, bases, attrs)

    def add_to_class(cls, name, value):
        super(SphinxModelBase, cls).add_to_class(name, value)

    @classmethod
    def patch_col_class(cls, field):
        @functools.wraps(field.get_col)
        def wrapper(alias, output_field=None):
            col = models.Field.get_col(field, alias, output_field=output_field)
            col.__class__ = SphinxCol
            return col
        field.get_col = wrapper
