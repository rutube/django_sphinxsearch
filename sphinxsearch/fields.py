# coding: utf-8

# $Id: $
import datetime
import time

from sphinxsearch.lookups import sphinx_lookups
from django.core import exceptions
from django.db import models
from django.utils import six


class SphinxField(models.TextField):
    """ Non-selectable indexed string field

    In sphinxsearch config terms, sql_field_string or rt_field.
    """
    class_lookups = sphinx_lookups.copy()


class SphinxDateTimeField(models.FloatField):
    """ Sphinx timestamp field for sql_attr_timestamp and rt_attr_timestamp.

    NB: sphinxsearch doens't store microseconds, if necessary, describe
        field as sql_attr_float in config.
    """

    def get_prep_value(self, value):
        if isinstance(value, (datetime.datetime, datetime.date)):
            return time.mktime(value.timetuple())
        elif isinstance(value, six.integer_types + (float,)):
            return value
        else:
            raise ValueError("Invalid value for UNIX_TIMESTAMP")

    def from_db_value(self, value, expression, connection, context):
        return datetime.datetime.fromtimestamp(value)


class SphinxIntegerField(models.IntegerField):
    class_lookups = sphinx_lookups.copy()


class SphinxBigIntegerField(models.BigIntegerField):
    class_lookups = sphinx_lookups.copy()


class SphinxMultiField(models.IntegerField):
    class_lookups = sphinx_lookups.copy()

    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, six.integer_types):
            return value
        return [super(SphinxMultiField, self).get_prep_value(v) for v in value]

    def from_db_value(self, value, expression, connection, context):
        if value is None:
            return value
        if value == '':
            return []
        try:
            return list(map(int, value.split(',')))
        except (TypeError, ValueError):
            raise exceptions.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
                params={'value': value},
            )

    def to_python(self, value):
        if value is None:
            return value
        try:
            return list(map(int, value.split(',')))
        except (TypeError, ValueError):
            raise exceptions.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
                params={'value': value},
            )


class SphinxMulti64Field(SphinxMultiField):
    pass