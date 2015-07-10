# coding: utf-8

# $Id: $
from datetime import datetime
from django.conf import settings
from django.db import connections
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
import sys
from testapp.models import TestModel


class SphinxModelTestCase(TestCase):
    _id = 0

    def _fixture_teardown(self):
        # self.truncate_model()
        pass

    def truncate_model(self):
        c = connections['sphinx'].cursor()
        c.execute("TRUNCATE RTINDEX %s" % self.model._meta.db_table)

    def setUp(self):
        self.model = TestModel
        self.truncate_model()
        self.now = datetime.now().replace(microsecond=0)
        self.defaults = {
            'id': self.newid(),
            'sphinx_field': "sphinx_field",
            'attr_uint': 100500,
            'attr_bool': True,
            'attr_bigint': 2**33,
            'attr_float': 1.2345,
            'attr_multi': [1,2,3],
            'attr_multi_64': [2**33, 2**34],
            'attr_timestamp': self.now,
            'attr_string': "hello sphinx world",
            "attr_json": {"json": "test"},
        }
        self.spx_queries = CaptureQueriesContext(connections['sphinx'])
        self.spx_queries.__enter__()
        self.obj = self.model.objects.create(**self.defaults)

    @classmethod
    def newid(cls):
        cls._id += 1
        return cls._id

    def reload_object(self, obj):
        return obj._meta.model.objects.get(pk=obj.pk)

    def assertObjectEqualsToDefaults(self, other):
        result = {k: getattr(other, k) for k in self.defaults.keys()
                  if k != 'sphinx_field'}
        for k in self.defaults.keys():
            if k == 'sphinx_field':
                continue
            self.assertEqual(result[k], self.defaults[k])

    def testInsertAttributes(self):
        other = self.reload_object(self.obj)
        self.assertObjectEqualsToDefaults(other)

    def testSelectByAttrs(self):
        exclude = ['attr_multi', 'attr_multi_64', 'attr_json', 'sphinx_field']
        for key in self.defaults.keys():
            if key in exclude:
                continue
            value = getattr(self.obj, key)
            try:
                other = self.model.objects.get(**{key: value})
            except self.model.DoesNotExist:
                self.fail("lookup failed for %s = %s" % (key, value))
            self.assertObjectEqualsToDefaults(other)

    def testSelectByMulti(self):
        multi_lookups = dict(
            attr_multi=self.obj.attr_multi[0],
            attr_multi_64=self.obj.attr_multi_64[0],
            attr_multi__in=[self.obj.attr_multi[0], 100],
            attr_multi_64__in=[self.obj.attr_multi_64[0], 1]
        )
        for k, v in multi_lookups.items():
            other = self.model.objects.get(**{k: v})
            self.assertObjectEqualsToDefaults(other)

    def testExcludeByAttrs(self):
        exclude = ['attr_multi', 'attr_multi_64', 'attr_json', 'sphinx_field',
                   'attr_float'
                   ]
        for key in self.defaults.keys():
            if key in exclude:
                continue
            value = getattr(self.obj, key)
            count = self.model.objects.notequal(**{key: value}).count()
            self.assertEqual(count, 0)

    def testNumericAttrLookups(self):
        numeric_lookups = dict(
            attr_uint__gte=0,
            attr_timestamp__gte=self.now,
            attr_multi__gte=0
        )

        for k, v in numeric_lookups.items():
            other = self.model.objects.get(**{k: v})
            self.assertObjectEqualsToDefaults(other)

    def tearDown(self):
        self.spx_queries.__exit__(*sys.exc_info())
        for query in self.spx_queries.captured_queries:
            print(query['sql'])
