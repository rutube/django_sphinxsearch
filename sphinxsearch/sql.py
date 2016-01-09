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
        try:
            params.remove('*')
        except ValueError:
            pass
        return sql, params


class SphinxWhereExpression(BaseExpression):
    def __init__(self, where, where_params):
        self.where = where
        self.where_params = where_params
        super(SphinxWhereExpression, self).__init__(output_field=BooleanField())

    def as_sql(self, compiler, connection):
        return self.where, self.where_params


class SphinxExtraWhere(ExtraWhere):

    def as_sql(self, qn=None, connection=None):
        sqls = ["%s" % sql for sql in self.sqls]
        return " AND ".join(sqls), tuple(self.params or ())


class SphinxWhereNode(WhereNode):

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


class SphinxQuery(Query):
    _clonable = ('options', 'match', 'group_limit', 'group_order_by',
                 'with_meta')

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
        # Each field must be monkey-patched with SphinxCol class to prevent
        # `tablename`.`attr` appearing in SQL
        for attr in attrs.values():
            if isinstance(attr, models.Field):
                col_patched = getattr(attr, '_col_patched', False)
                if not col_patched:
                    cls.patch_col_class(attr)

        new_class = super(SphinxModelBase, cls).__new__(cls, name, bases, attrs)

        # if have overriden primary key, it should be the first local field,
        # because of JSONField feature at jsonfield.subclassing.Creator.__set__
        local_fields = new_class._meta.local_fields
        try:
            pk_idx = local_fields.index(new_class._meta.pk)
            if pk_idx > 0:
                local_fields.insert(0, local_fields.pop(pk_idx))
        except ValueError:
            pass

        return new_class

    def add_to_class(cls, name, value):
        col_patched = getattr(value, '_col_patched', False)
        if not col_patched and isinstance(value, models.Field):
            cls.patch_col_class(value)
        super(SphinxModelBase, cls).add_to_class(name, value)

    @classmethod
    def patch_col_class(cls, field):
        @functools.wraps(field.get_col)
        def wrapper(alias, output_field=None):
            col = models.Field.get_col(field, alias, output_field=output_field)
            col.__class__ = SphinxCol
            return col
        field.get_col = wrapper
