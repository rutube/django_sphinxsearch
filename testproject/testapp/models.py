# coding: utf-8

# $Id: $
import json

import six
from datetime import datetime
from django.db import models

from jsonfield.fields import JSONField

from sphinxsearch import sql
from sphinxsearch import models as spx_models


class Django10CompatJSONField(JSONField):

    def from_db_value(self, value, expression, connection, context):
        # In Django-1.10 python value is loaded in this method
        if value is None:
            return None
        return json.loads(value)


class FieldMixin(spx_models.SphinxModel):
    class Meta:
        abstract = True
    sphinx_field = spx_models.SphinxField(default='')
    other_field = spx_models.SphinxField(default='')
    attr_uint = spx_models.SphinxIntegerField(default=0, db_column='attr_uint_')
    attr_bigint = spx_models.SphinxBigIntegerField(default=0)
    attr_float = models.FloatField(default=0.0)
    attr_timestamp = spx_models.SphinxDateTimeField(default=datetime.now)
    attr_string = models.CharField(max_length=32, default='')
    attr_multi = spx_models.SphinxMultiField(default=[])
    attr_multi_64 = spx_models.SphinxMulti64Field(default=[])
    attr_json = Django10CompatJSONField(default={})
    attr_bool = models.BooleanField(default=False)


class TestModel(FieldMixin, spx_models.SphinxModel):
    pass


class DefaultDjangoModel(models.Model):
    pass


class OverridenSphinxModel(six.with_metaclass(sql.SphinxModelBase, models.Model)):
    class Meta:
        managed = False

    _excluded_update_fields = (
       models.CharField,
       models.TextField
    )

    objects = spx_models.SphinxManager()

    sphinx_field = spx_models.SphinxField(default='')
    other_field = spx_models.SphinxField(default='')
    attr_uint = spx_models.SphinxIntegerField(default=0, db_column='attr_uint_')
    attr_bigint = spx_models.SphinxBigIntegerField(default=0)
    attr_float = models.FloatField(default=0.0)
    attr_timestamp = spx_models.SphinxDateTimeField(default=datetime.now)
    attr_string = models.CharField(max_length=32, default='')
    attr_multi = spx_models.SphinxMultiField(default=[])
    attr_multi_64 = spx_models.SphinxMulti64Field(default=[])
    attr_json = Django10CompatJSONField(default={})
    attr_bool = models.BooleanField(default=False)


class ForcedPKModel(FieldMixin, spx_models.SphinxModel):

    class Meta:
        db_table = 'testapp_testmodel'

    id = models.BigIntegerField(primary_key=True)


class ModelWithAllDbColumnFields(spx_models.SphinxModel):
    class Meta:
        db_table = 'testapp_testmodel_aliased'

    sphinx_field = spx_models.SphinxField(default='', db_column='_sphinx_field')
    other_field = spx_models.SphinxField(default='', db_column='_other_field')
    attr_uint = spx_models.SphinxIntegerField(default=0, db_column='_attr_uint_')
    attr_bigint = spx_models.SphinxBigIntegerField(default=0, db_column='_attr_bigint')
    attr_float = models.FloatField(default=0.0, db_column='_attr_float')
    attr_timestamp = spx_models.SphinxDateTimeField(default=datetime.now,
                                                    db_column='_attr_timestamp')
    attr_string = models.CharField(max_length=32, default='',
                                   db_column='_attr_string')

    attr_multi = spx_models.SphinxMultiField(default=[],
                                             db_column='_attr_multi')
    attr_multi_64 = spx_models.SphinxMulti64Field(default=[],
                                                  db_column='_attr_multi_64')
    attr_json = Django10CompatJSONField(default={}, db_column='_attr_json')
    attr_bool = models.BooleanField(default=False, db_column='_attr_bool')


class CharPKModel(FieldMixin, spx_models.SphinxModel):

    docid = spx_models.SphinxField(primary_key=True)
    id = spx_models.SphinxBigIntegerField(unique=True)
