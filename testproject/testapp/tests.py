# coding: utf-8

# $Id: $
from datetime import datetime, timedelta
from unittest import skip
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
        c = connections[settings.SPHINX_DATABASE_NAME].cursor()
        c.execute("TRUNCATE RTINDEX %s" % self.model._meta.db_table)

    def setUp(self):
        self.model = TestModel
        self.truncate_model()
        self.now = datetime.now().replace(microsecond=0)
        self.defaults = {
            'id': self.newid(),
            'sphinx_field': "hello sphinx field",
            'attr_uint': 100500,
            'attr_bool': True,
            'attr_bigint': 2**33,
            'attr_float': 1.2345,
            'attr_multi': [1,2,3],
            'attr_multi_64': [2**33, 2**34],
            'attr_timestamp': self.now,
            'attr_string': "hello sphinx attr",
            "attr_json": {"json": "test"},
        }
        self.spx_queries = CaptureQueriesContext(
            connections[settings.SPHINX_DATABASE_NAME])
        self.spx_queries.__enter__()
        self.obj = self.model.objects.create(**self.defaults)

    @classmethod
    def newid(cls):
        cls._id += 1
        return cls._id

    def reload_object(self, obj):
        return obj._meta.model.objects.get(pk=obj.pk)

    def assertObjectEqualsToDefaults(self, other, defaults=None):
        defaults = defaults or self.defaults
        result = {k: getattr(other, k) for k in defaults.keys()
                  if k != 'sphinx_field'}
        for k in defaults.keys():
            if k == 'sphinx_field':
                continue
            self.assertEqual(result[k], defaults[k])

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

    def testUpdates(self):
        new_values = {
            'attr_uint': 200,
            'attr_bool': False,
            'attr_bigint': 2**35,
            'attr_float': 5.4321,
            'attr_multi': [6,7,8],
            'attr_multi_64': [2**34, 2**35],
            'attr_timestamp': self.now + timedelta(seconds=60),
        }

        for k, v in new_values.items():
            setattr(self.obj, k, v)

        # Check UPDATE mode (string attributes are not updated)
        self.obj.save(update_fields=new_values.keys())

        other = self.reload_object(self.obj)
        self.assertObjectEqualsToDefaults(other, defaults=new_values)

        # Check REPLACE mode (string and json attributes are updated by
        # replacing whole row only)
        string_defaults = {
            'sphinx_field': "another_field",
            'attr_string': "another string",
            'attr_json': {"json": "other", 'add': 3},
        }
        new_values.update(string_defaults)
        for k, v in string_defaults.items():
            setattr(self.obj, k, v)

        self.obj.save()

        other = self.reload_object(self.obj)
        self.assertObjectEqualsToDefaults(other, defaults=new_values)

    def testBulkUpdate(self):
        qs = self.model.objects.filter(attr_uint=self.defaults['attr_uint'])
        qs.update(attr_bool=not self.defaults['attr_bool'])
        other = self.reload_object(self.obj)
        self.assertFalse(other.attr_bool)

    def testDelete(self):
        self.assertEqual(self.model.objects.count(), 1)
        self.obj.delete()
        self.assertEqual(self.model.objects.count(), 0)

    def testDjangoSearch(self):
        other = self.model.objects.filter(sphinx_field__search="hello")[0]
        self.assertEqual(other.id, self.obj.id)

    @skip("FIXME")
    def testDjangoSearchMultiple(self):
        list(self.model.objects.filter(sphinx_field__search="@sdfsff 'sdfdf'",
                                       other_field__search="sdf"))

    def testAdminSupportIssues(self):
        exclude = ['attr_multi', 'attr_multi_64', 'attr_json', 'sphinx_field']
        for key in self.defaults.keys():
            if key in exclude:
                continue
            value = getattr(self.obj, key)
            try:
                key = '%s__exact' % key
                other = self.model.objects.get(**{key: value})
            except self.model.DoesNotExist:
                self.fail("lookup failed for %s = %s" % (key, value))
            self.assertObjectEqualsToDefaults(other)

    def test64BitNumerics(self):
        new_values = {
            # 32 bit unsigned int
            'attr_uint': 2**31 + 1,
            'attr_multi': [2**31 + 1],
            # 64 bit signed int
            'attr_bigint': 2**63 + 1 - 2**64,
            'attr_multi_64': [2**63 + 1 - 2**64]
        }
        for k, v in new_values.items():
            setattr(self.obj, k, v)

        # Check UPDATE mode (string attributes are not updated)
        self.obj.save(update_fields=new_values.keys())

        other = self.reload_object(self.obj)
        self.assertObjectEqualsToDefaults(other, defaults=new_values)

    def testOptionsClause(self):
        self.defaults['id'] = self.newid()
        self.model.objects.create(**self.defaults)

        qs = list(self.model.objects.options(
            max_matches=1, ranker='bm25').all())
        self.assertEqual(len(qs), 1)

    def testLimit(self):
        expected = self.create_multiple_models()
        qs = list(self.model.objects.all()[2:4])
        self.assertEqual([q.id for q in qs], expected[2:4])

    def create_multiple_models(self):
        expected = [self.obj.id]
        for i in range(10):
            id = self.newid()
            self.model.objects.create(id=id, attr_json={},
                                      attr_uint=i,
                                      attr_timestamp=self.now)
            expected.append(id)
        return expected

    def testOrderBy(self):
        expected = self.create_multiple_models()
        qs = list(self.model.objects.order_by('-attr_uint'))
        expected = [self.obj.id] + list(reversed(expected[1:]))
        self.assertEqual([q.id for q in qs], expected)



    def tearDown(self):
        self.spx_queries.__exit__(*sys.exc_info())
        for query in self.spx_queries.captured_queries:
            print(query['sql'])
