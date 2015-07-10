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

    def _fixture_teardown(self):
        self.truncate_model()

    def truncate_model(self):
        c = connections['sphinx'].cursor()
        c.execute("TRUNCATE RTINDEX %s" % self.model._meta.db_table)

    def setUp(self):
        self.model = TestModel
        self.truncate_model()
        self.now = datetime.now().replace(microsecond=0)
        self._id = 0
        self.defaults = {
            'id': self.newid,
            'sphinx_field': "sphinx_field",
            'attr_uint': 100500,
            'attr_bool': True,
            'attr_bigint': 2**33,
            'attr_float': 1.2345,
            'attr_multi': [1,2,3],
            'attr_multi_64': [2**33, 2**34],
            'attr_timestamp': self.now,
            'attr_string': "string attr",
            "attr_json": {"json": "test"},
        }
        self.spx_queries = CaptureQueriesContext(connections['sphinx'])
        self.spx_queries.__enter__()

    @property
    def newid(self):
        self._id += 1
        return self._id

    def tearDown(self):
        self.spx_queries.__exit__(*sys.exc_info())
        for query in self.spx_queries.captured_queries:
            print(query['sql'])

    def testInsertAttributes(self):
        obj = self.model.objects.create(**self.defaults)

        other = self.reload_object(obj)
        result = {k: getattr(other, k) for k in self.defaults.keys()
                  if k != 'sphinx_field'}

        for k in self.defaults.keys():
            if k == 'sphinx_field':
                continue
            self.assertEqual(result[k], self.defaults[k])

    def reload_object(self, obj):
        return obj._meta.model.objects.get(pk=obj.pk)


