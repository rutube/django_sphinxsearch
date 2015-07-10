# coding: utf-8

# $Id: $
from django.db import models

from jsonfield.fields import JSONField

from sphinxsearch import models as spx_models


class TestModel(spx_models.SphinxModel):
    sphinx_field = spx_models.SphinxField()
    other_field = spx_models.SphinxField()
    attr_uint = models.IntegerField()
    attr_bigint = models.BigIntegerField()
    attr_float = models.FloatField()
    attr_timestamp = spx_models.SphinxDateTimeField()
    attr_string = models.CharField(max_length=32)
    attr_multi = spx_models.SphinxMultiField()
    attr_multi_64 = spx_models.SphinxMulti64Field()
    attr_json = JSONField()
    attr_bool = models.NullBooleanField()
