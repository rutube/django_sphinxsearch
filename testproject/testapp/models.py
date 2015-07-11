# coding: utf-8

# $Id: $
from django.db import models

from jsonfield.fields import JSONField

from sphinxsearch import models as spx_models


class TestModel(spx_models.SphinxModel):
    sphinx_field = spx_models.SphinxField(default='')
    other_field = spx_models.SphinxField(default='')
    attr_uint = models.IntegerField(default=0)
    attr_bigint = models.BigIntegerField(default=0)
    attr_float = models.FloatField(default=0.0)
    attr_timestamp = spx_models.SphinxDateTimeField()
    attr_string = models.CharField(max_length=32, default='')
    attr_multi = spx_models.SphinxMultiField(default=[])
    attr_multi_64 = spx_models.SphinxMulti64Field(default=[])
    attr_json = JSONField()
    attr_bool = models.BooleanField(default=False)
