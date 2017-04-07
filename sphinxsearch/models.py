# coding: utf-8
from copy import copy

from django.conf import settings
from django.db import connections
from django.db.models import QuerySet
from django.db.models.expressions import RawSQL

from sphinxsearch import sql, compat
from sphinxsearch.fields import *
from sphinxsearch.utils import sphinx_escape


class SphinxQuerySet(QuerySet):
    def __init__(self, model, **kwargs):
        kwargs.setdefault('query', sql.SphinxQuery(model))
        super(SphinxQuerySet, self).__init__(model, **kwargs)

    def _filter_or_exclude(self, negate, *args, **kwargs):
        args = list(args)
        kwargs = copy(kwargs)
        for key, value in list(kwargs.items()):
            field, lookup = self.__get_field_lookup(key)
            if self.__check_search_lookup(field, lookup, value):
                kwargs.pop(key, None)
            elif self.__check_in_lookup(field, lookup, value, negate):
                kwargs.pop(key, None)
            elif self.__check_sphinx_field_exact(field, lookup, value, negate):
                kwargs.pop(key, None)
            elif self.__check_mva_field_lookup(field, lookup, value, negate):
                kwargs.pop(key, None)
            pass

        return super(SphinxQuerySet, self)._filter_or_exclude(negate, *args,
                                                              **kwargs)

    def __get_field_lookup(self, key):
        tokens = key.split('__')
        if len(tokens) == 1:
            field_name, lookup = tokens[0], 'exact'
        elif len(tokens) == 2:
            field_name, lookup = tokens
        else:
            raise ValueError("Nested field lookup found")
        if field_name == 'pk':
            field = self.model._meta.pk
        else:
            field = self.model._meta.get_field(field_name)
        return field, lookup

    def _negate_expression(self, negate, lookup):
        if isinstance(lookup, (tuple, list)):
            result = []
            for v in lookup:
                result.append(self._negate_expression(negate, v))
            return result
        else:
            if not isinstance(lookup, six.string_types):
                lookup = six.text_type(lookup)

            if not lookup.startswith('"'):
                lookup = '"%s"' % lookup
            if negate:
                lookup = '-%s' % lookup
            return lookup

    def match(self, *args, **kwargs):
        """ Enables full-text searching in sphinx (MATCH expression).

        qs.match('sphinx_expression_1', 'sphinx_expression_2')
            compiles to
        MATCH('sphinx_expression_1 sphinx_expression_2)

        qs.match(field1='sphinx_loopup1',field2='sphinx_loopup2')
            compiles to
        MATCH('@field1 sphinx_lookup1 @field2 sphinx_lookup2')
        """
        qs = self._clone()
        qs.query.add_match(*args, **kwargs)
        return qs

    def options(self, **kw):
        """ Setup OPTION clause for query."""
        qs = self._clone()
        try:
            qs.query.options.update(kw)
        except AttributeError:
            qs.query.options = kw
        return qs

    def with_meta(self):
        """ Force call SHOW META after fetching queryset data from searchd."""
        qs = self._clone()
        qs.query.with_meta = True
        return qs

    def group_by(self, *args, **kwargs):
        """
        :param args: list of fields to group by
        :type args: list-like

        Keyword params:
        :param group_limit: (GROUP <N> BY), limits number of group members to N
        :type group_limit: int
        :param group_order_by: (WITHIN GROUP ORDER BY), sort order within group
        :type group_order_by: list-like
        :return: new queryset with grouping
        :rtype: SphinxQuerySet
        """
        group_limit = kwargs.get('group_limit', 0)
        group_order_by = kwargs.get('group_order_by', ())

        if not isinstance(group_order_by, (list, tuple)):
            group_order_by = [group_order_by]

        def fix_arg_name(group_arg):
            if group_arg.startswith('-'):
                negate = True
                group_arg = group_arg[1:]
                # if group_arg isn't name of db_column, lets fix it
                try:
                    fld = self.model._meta.get_field(group_arg)
                    group_arg = fld.column
                except:
                    pass
            else:
                negate = False

            if negate:
                group_arg = '-%s' % group_arg
            return group_arg

        group_order_by = list(map(fix_arg_name, group_order_by))

        qs = self._clone()
        qs.query.group_by = qs.query.group_by or []
        for field_name in args:
            if field_name not in qs.query.extra_select:
                field = self.model._meta.get_field(field_name)
                qs.query.group_by.append(field.attname)
            else:
                qs.query.group_by.append(RawSQL(field_name, []))
        qs.query.group_limit = group_limit
        qs.query.group_order_by = group_order_by
        return qs

    def __check_mva_field_lookup(self, field, lookup, value, negate):
        """ Replaces some MVA field lookups with valid sphinx expressions."""

        if not isinstance(field, (SphinxMultiField, SphinxMulti64Field)):
            return False

        transforms = {
            'exact': "IN(%s, %%s)",
            'gte': "LEAST(%s) >= %%s",
            'ge': "LEAST(%s) > %%s",
            'lt': "GREATEST(%s) < %%s",
            'lte': "GREATEST(%s) <= %%s"
        }

        if lookup in transforms.keys():
            tpl = transforms[lookup]
            condition = tpl % field.column
            if negate:
                condition = "NOT (%s)" % condition
            self.query.add_extra(None, None, [condition], [value], None, None)
            return True
        else:
            raise ValueError("Invalid lookup for MVA: %s" % lookup)

    def __check_search_lookup(self, field, lookup, value):
        """ Replaces field__search lookup with MATCH() call."""
        if lookup != 'search':
            return False
        self.query.add_match(**{field.name: sphinx_escape(value)})
        return True

    def __check_in_lookup(self, field, lookup, value, negate):
        if lookup != 'in':
            return False
        if not isinstance(value, (tuple, list)):
            value = [value]
        placeholders = ', '.join(['%s'] * len(value))
        condition = "IN(%s, %s)" % (field.column, placeholders)
        value = [field.get_prep_value(v) for v in value]
        if negate:
            condition = "NOT (%s)" % condition
        self.query.add_extra(None, None, [condition], value, None, None)
        return True

    def __check_sphinx_field_exact(self, field, lookup, value, negate):
        if not isinstance(field, SphinxField):
            return False
        if lookup != 'exact':
            raise ValueError("Unsupported lookup for SphinxField")
        if negate:
            value = '-%s' % value
        self.query.add_match(**{field.name: value})
        return True

    def _fetch_meta(self):
        c = connections[settings.SPHINX_DATABASE_NAME].cursor()
        try:
            c.execute("SHOW META")
            self.meta = dict([c.fetchone()])
        except UnicodeDecodeError:
            self.meta = {}
        finally:
            c.close()

    def iterator(self):
        for row in super(SphinxQuerySet, self).iterator():
            yield row
        if getattr(self.query, 'with_meta', False):
            self._fetch_meta()

    if compat.DJ_11:
        # Django-1.11 does not use iterator() call when materializing, so
        # with_meta() should be handled separately.

        def _fetch_all(self):
            super(SphinxQuerySet, self)._fetch_all()
            if getattr(self.query, 'with_meta', False):
                self._fetch_meta()


class SphinxManager(models.Manager):
    use_for_related_fields = True

    def get_queryset(self):
        """ Creates new queryset for model.

        :return: model queryset
        :rtype: SphinxQuerySet
        """

        # Determine which fields are sphinx fields (full-text data) and
        # defer loading them. Sphinx won't return them.
        # TODO: we probably need a way to keep these from being loaded
        # later if the attr is accessed.
        sphinx_fields = [field.name for field in self.model._meta.fields
                         if isinstance(field, SphinxField)]

        return SphinxQuerySet(self.model).defer(*sphinx_fields)

    def options(self, **kw):
        return self.get_queryset().options(**kw)

    def match(self, expression):
        return self.get_queryset().match(expression)

    def group_by(self, *args, **kw):
        return self.get_queryset().group_by(*args, **kw)

    def get(self, *args, **kw):
        return self.get_queryset().get(*args, **kw)


class SphinxModel(six.with_metaclass(sql.SphinxModelBase, models.Model)):
    class Meta:
        abstract = True

    objects = SphinxManager()

    _excluded_update_fields = (
        models.CharField,
        models.TextField
    )
