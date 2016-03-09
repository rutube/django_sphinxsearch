# coding: utf-8

# $Id: $
import six
from datetime import datetime
from django.db import models

from jsonfield.fields import JSONField

from sphinxsearch import sql
from sphinxsearch import models as spx_models
from sphinxsearch import fields as spx_fields


class FieldMixin(spx_models.SphinxModel):
    class Meta:
        abstract = True
    sphinx_field = spx_models.SphinxField(default='')
    other_field = spx_models.SphinxField(default='')
    attr_uint = spx_fields.SphinxIntegerField(default=0, db_column='attr_uint_')
    attr_bigint = spx_models.SphinxBigIntegerField(default=0)
    attr_float = models.FloatField(default=0.0)
    attr_timestamp = spx_models.SphinxDateTimeField(default=datetime.now)
    attr_string = models.CharField(max_length=32, default='')
    attr_multi = spx_models.SphinxMultiField(default=[])
    attr_multi_64 = spx_models.SphinxMulti64Field(default=[])
    attr_json = JSONField(default={})
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
    attr_json = JSONField(default={})
    attr_bool = models.BooleanField(default=False)


class ForcedPKModel(FieldMixin, spx_models.SphinxModel):

    class Meta:
        db_table = 'testapp_testmodel'

    id = models.BigIntegerField(primary_key=True)


class CharPKModel(FieldMixin, spx_models.SphinxModel):

    docid = spx_models.SphinxField(primary_key=True)
    id = spx_models.SphinxBigIntegerField(unique=True)
