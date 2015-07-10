# coding: utf-8

# $Id: $
import functools
from django.db import models
from django.db.models import Count
from django.db.models.base import ModelBase
from django.db.models.expressions import Col
from django.db.models.sql import Query


class SphinxCount(Count):
    """ Replaces Mysql-like COUNT('*') with COUNT(*) token."""
    template = '%(function)s(*)'

    def as_sql(self, compiler, connection, function=None, template=None):
        sql, params = super(SphinxCount, self).as_sql(
            compiler, connection, function=function, template=template)
        params.remove('*')
        return sql, params


class SphinxQuery(Query):
    _clonable = ('options', 'match', 'group_limit', 'group_order_by',
                 'with_meta')
    #
    # aggregates_module = sphinx_aggregates
    #
    # def __init__(self, *args, **kwargs):
    #     kwargs.setdefault('where', compiler.SphinxWhereNode)
    #     super(SphinxQuery, self).__init__(*args, **kwargs)
    #
    # def clone(self, klass=None, memo=None, **kwargs):
    #     query = super(SphinxQuery, self).clone(klass=klass, memo=memo, **kwargs)
    #     for attr_name in self._clonable:
    #         value = getattr(self, attr_name, None)
    #         if value:
    #             setattr(query, attr_name, value)
    #     return query
    #
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
        qn = compiler.quote_name_unless_alias
        return "%s" % (qn(self.target.column,)), []


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
