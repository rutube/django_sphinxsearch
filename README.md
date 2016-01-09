# Django-sphinxsearch

[SphinxSearch](http://sphinxsearch.com) database backend for [Django](https://www.djangoproject.com/).

[![Build Status](https://travis-ci.org/rutube/django_sphinxsearch.svg)](https://travis-ci.org/rutube/django_sphinxsearch)
[![PyPI version](https://badge.fury.io/py/django_sphinxsearch.svg)](http://badge.fury.io/py/django_sphinxsearch)

* Not a [django_sphinx_db](https://github.com/smartfile/django-sphinx-db) fork
* `Django>=1.8,<1.10` supported

## Installation and usage

1. Install django-sphinxsearch package

    ```sh
    pip install django_sphinxsearch
    ```

2. Configure Django settings

    ```python

    INSTALLED_APPS += (
        'sphinxsearch',
    )

    SPHINX_DATABASE_NAME = 'sphinx'

    DATABASES[SPHINX_DATABASE_NAME] = {
        'ENGINE': 'sphinxsearch.backend.sphinx',
        'HOST': '127.0.0.1',
        'PORT': 9306,
    }

    DATABASE_ROUTERS = ['sphinxsearch.routers.SphinxRouter']
    ```

3. Create index definitions in sphinx.conf

    ```
    index testapp_testmodel
    {
        type              = rt
        path              = /data/sphinx/testapp/testmodel/

        rt_field          = sphinx_field
        rt_attr_uint      = attr_uint
        rt_attr_bool      = attr_bool
        rt_attr_bigint    = attr_bigint
        rt_attr_float     = attr_float
        rt_attr_multi     = attr_multi
        rt_attr_multi_64  = attr_multi_64
        rt_attr_timestamp = attr_timestamp
        rt_attr_string    = attr_string
        rt_attr_json      = attr_json
    }
    ```

4. Define Django model for index

    ```python

    from datetime import datetime
    from django.db import models

    from jsonfield.fields import JSONField

    from sphinxsearch import models as spx_models

    class TestModel(spx_models.SphinxModel):
        # Note that NULL values are not allowed for sphinx rt-index.

        # Indexed text field. If no attribute with same name defined, can't be
        # retrieved from index.
        sphinx_field = spx_models.SphinxField(default='')

        # Numeric attributes
        attr_uint = models.IntegerField(default=0)
        attr_bigint = models.BigIntegerField(default=0)
        attr_float = models.FloatField(default=0.0)
        attr_timestamp = spx_models.SphinxDateTimeField(default=datetime.now)
        attr_bool = models.BooleanField(default=False)

        # String attributes
        attr_string = models.CharField(max_length=32, default='')
        attr_json = JSONField(default={})

        # Multi-value fields (sets of integer values)
        attr_multi = spx_models.SphinxMultiField(default=[])
        attr_multi_64 = spx_models.SphinxMulti64Field(default=[])
    ```

5. Query index from your app

    ```python

    # Numeric attributes filtering
    TestModel.objects.filter(attr_uint=0, attr_float__gte=10, attr_multi__in=[1, 2])

    # For sphinxsearch>=2.2.7, string attr filtering enabled
    TestModel.objects.filter(attr_string='some test')

    # Use mysql-fulltext-search filtering:

    TestModel.objects.filter(sphinx_field__search='find me')

    # Run match queries
    TestModel.objects.match(
        'find in all fields',
        sphinx_field='only in this field')

    # Insert and update documents to index

    obj = TestModel.objects.create(**values)
    obj.attr_uint = 1
    obj.save()

    TestModel.objects.filter(attr_bool=True).update(attr_uint=2)
    ```

## Notes for production usage

* Sphinxsearch engine has some issues with SQL-syntax support, and they vary
from one version to another. I.e. float attributes are not comparable,
string attributes were not comparible till v2.2.7.
* Without limits sphinxsearch returns only 20 matched documents.
* uint attributes accept -1 but return it as unsigned 32bit integer.
* bigint accept 2**63 + 1 but return it as signed 64bit integer.
