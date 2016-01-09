# coding: utf-8

# $Id: $
from datetime import datetime
from django.db import models

from jsonfield.fields import JSONField

from sphinxsearch import models as spx_models


class FieldMixin(spx_models.SphinxModel):
    class Meta:
        abstract = True
    sphinx_field = spx_models.SphinxField(default='')
    other_field = spx_models.SphinxField(default='')
    attr_uint = models.IntegerField(default=0)
    attr_bigint = models.BigIntegerField(default=0)
    attr_float = models.FloatField(default=0.0)
    attr_timestamp = spx_models.SphinxDateTimeField(default=datetime.now)
    attr_string = models.CharField(max_length=32, default='')
    attr_multi = spx_models.SphinxMultiField(default=[])
    attr_multi_64 = spx_models.SphinxMulti64Field(default=[])
    attr_json = JSONField(default={})
    attr_bool = models.BooleanField(default=False)


class TestModel(FieldMixin, spx_models.SphinxModel):
    pass


class ForcedPKModel(FieldMixin, spx_models.SphinxModel):

    class Meta:
        db_table = 'testapp_testmodel'

    id = models.BigIntegerField(primary_key=True)