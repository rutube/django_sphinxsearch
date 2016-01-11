# coding: utf-8

# $Id: $
import sys
from datetime import datetime, timedelta
from unittest import expectedFailure

from django.conf import settings
from django.db import connections
from django.db.models import Sum
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from testapp import models


class SphinxModelTestCaseBase(TestCase):
    _id = 0

    model = models.TestModel

    def _fixture_teardown(self):
        # self.truncate_model()
        pass

    def truncate_model(self):
        c = connections[settings.SPHINX_DATABASE_NAME].cursor()
        c.execute("TRUNCATE RTINDEX %s" % self.model._meta.db_table)

    def setUp(self):
        c = connections[settings.SPHINX_DATABASE_NAME]
        self.no_string_compare = c.mysql_version < (2, 2, 7)
        self.truncate_model()
        self.now = datetime.now().replace(microsecond=0)
        self.defaults = self.get_model_defaults()
        self.spx_queries = CaptureQueriesContext(
            connections[settings.SPHINX_DATABASE_NAME])
        self.spx_queries.__enter__()
        self.obj = self.model.objects.create(**self.defaults)

    def get_model_defaults(self):
        return {
            'id': self.newid(),
            'sphinx_field': "hello sphinx field",
            'attr_uint': 100500,
            'attr_bool': True,
            'attr_bigint': 2 ** 33,
            'attr_float': 1.2345,
            'attr_multi': [1, 2, 3],
            'attr_multi_64': [2 ** 33, 2 ** 34],
            'attr_timestamp': self.now,
            'attr_string': "hello sphinx attr",
            "attr_json": {"json": "test"},
        }

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

    def tearDown(self):
        self.spx_queries.__exit__(*sys.exc_info())
        for query in self.spx_queries.captured_queries:
            print(query['sql'])


class SphinxModelTestCase(SphinxModelTestCaseBase):

    def testInsertAttributes(self):
        other = self.reload_object(self.obj)
        self.assertObjectEqualsToDefaults(other)

    def testSelectByAttrs(self):
        exclude = ['attr_multi', 'attr_multi_64', 'attr_json', 'sphinx_field']
        if self.no_string_compare:
            exclude.extend(['attr_string', 'attr_json'])
        for key in self.defaults.keys():
            if key in exclude:
                continue
            value = getattr(self.obj, key)
            try:
                other = self.model.objects.get(**{key: value})
            except self.model.DoesNotExist:
                self.fail("lookup failed for %s = %s" % (key, value))
            self.assertObjectEqualsToDefaults(other)

    def testExtraWhere(self):
        qs = list(self.model.objects.extra(select={'const': 0}, where=['const=0']))
        self.assertEqual(len(qs), 1)

    def testGroupByExtraSelect(self):
        qs = self.model.objects.all()
        qs = qs.extra(
            select={'extra': 'CEIL(attr_uint/3600)'})

        qs = qs.group_by('extra')
        qs = list(qs)
        self.assertEqual(len(qs), 1)

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
                   'attr_float', 'docid']
        if self.no_string_compare:
            exclude.extend(['attr_string'])
        for key in self.defaults.keys():
            if key in exclude:
                continue
            value = getattr(self.obj, key)
            count = self.model.objects.exclude(**{key: value}).count()
            self.assertEqual(count, 0)

    def testExcludeAttrByList(self):
        exclude = ['attr_multi', 'attr_multi_64', 'attr_json', 'sphinx_field',
                   'attr_float', 'docid']
        if self.no_string_compare:
            exclude.extend(['attr_string'])
        for key in self.defaults.keys():
            if key in exclude:
                continue
            value = getattr(self.obj, key)
            filter_kwargs = {"%s__in" % key: [value]}
            count = self.model.objects.exclude(**filter_kwargs).count()
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

    def testDjangoSearchMultiple(self):
        list(self.model.objects.filter(sphinx_field__search="@sdfsff 'sdfdf'",
                                       other_field__search="sdf"))

    def testAdminSupportIssues(self):
        exclude = ['attr_multi', 'attr_multi_64', 'attr_json', 'sphinx_field']
        if self.no_string_compare:
            exclude.extend(['attr_string', 'attr_json'])
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
            self.model.objects.create(id=id,
                                      attr_json={},
                                      attr_uint=i,
                                      attr_timestamp=self.now)
            expected.append(id)
        return expected

    def testExclude(self):
        attr_uint = self.defaults['attr_uint']
        attr_bool = self.defaults['attr_bool']
        not_bool = not attr_bool

        # check exclude works
        qs = list(self.model.objects.exclude(
            attr_uint=attr_uint, attr_bool=attr_bool))
        self.assertEqual(len(qs), 0)
        # check that it's really NOT (a AND b) as in Django documentation
        qs = list(self.model.objects.exclude(
            attr_uint=attr_uint, attr_bool=not_bool))
        self.assertEqual(len(qs), 1)

    def testExcludeByList(self):
        attr_multi = self.defaults['attr_multi']
        qs = list(self.model.objects.exclude(attr_multi__in=attr_multi))
        self.assertEqual(len(qs), 0)

        attr_uint = self.defaults['attr_uint']
        qs = list(self.model.objects.exclude(attr_uint__in=[attr_uint]))
        self.assertEqual(len(qs), 0)

    def testNumericIn(self):
        attr_uint = self.defaults['attr_uint']
        qs = list(self.model.objects.filter(attr_uint__in=[attr_uint]))
        self.assertEqual(len(qs), 1)

    def testMatchClause(self):
        qs = list(self.model.objects.match("doesnotexistinindex"))
        self.assertEqual(len(qs), 0)
        qs = list(self.model.objects.match("hello"))
        self.assertEqual(len(qs), 1)
        qs = list(self.model.objects.match("hello").match("world"))
        self.assertEqual(len(qs), 0)

    def testOptionClause(self):
        qs = list(self.model.objects.match("hello").options(
            ranker="expr('sum(lcs*user_weight)*1000+bm25')",
            field_weights="(sphinx_field=3,other_field=2)",
            index_weights="(testapp_testindex=2)",
            sort_method="kbuffer"
        ))
        self.assertEqual(len(qs), 1)

    def testOrderBy(self):
        expected = self.create_multiple_models()
        qs = list(self.model.objects.order_by('-attr_uint'))
        expected = [self.obj.id] + list(reversed(expected[1:]))
        self.assertEqual([q.id for q in qs], expected)
        list(self.model.objects.order_by())

    def testGroupBy(self):
        m1 = self.model.objects.create(id=self.newid(),
                                       attr_uint=10, attr_float=1)
        m2 = self.model.objects.create(id=self.newid(),
                                       attr_uint=10, attr_float=2)
        m3 = self.model.objects.create(id=self.newid(),
                                       attr_uint=20, attr_float=2)
        m4 = self.model.objects.create(id=self.newid(),
                                       attr_uint=10, attr_float=1)

        qs = self.model.objects.defer('attr_json', 'attr_multi', 'attr_multi_64')
        qs = list(qs.group_by('attr_uint',
                              group_limit=1,
                              group_order_by='-attr_float'))
        self.assertSetEqual({o.id for o in qs}, {self.obj.id, m2.id, m3.id})

    def testAggregation(self):
        s = self.model.objects.aggregate(Sum('attr_uint'))
        self.assertEqual(s['attr_uint__sum'], self.defaults['attr_uint'])

    def testSphinxFieldExact(self):
        sphinx_field = self.defaults['sphinx_field']
        other = self.model.objects.get(sphinx_field=sphinx_field)
        self.assertObjectEqualsToDefaults(other)

    def testSphinxFieldExactExclude(self):
        sphinx_field = self.defaults['sphinx_field']
        qs = list(self.model.objects.match('hello').exclude(sphinx_field=sphinx_field))
        self.assertEqual(len(qs), 0)

    def testCount(self):
        self.create_multiple_models()
        r = self.model.objects.filter(attr_uint__gte=-1).count()
        self.assertEqual(r, 11)

    def testCastToChar(self):
        if self.no_string_compare:
            self.skipTest("string compare not supported by server")
        self.obj.attr_string = 100500
        self.obj.save()
        self.defaults['attr_string'] = '100500'
        other = self.model.objects.get(attr_string=100500)
        self.assertObjectEqualsToDefaults(other)


class ForcedPKTestCase(SphinxModelTestCase):
    model = models.ForcedPKModel


class CharPKTestCase(SphinxModelTestCase):
    model = models.CharPKModel

    def get_model_defaults(self):
        defaults = super(CharPKTestCase, self).get_model_defaults()
        defaults['docid'] = str(defaults['id'])
        return defaults

    @expectedFailure
    def testDelete(self):
        super(CharPKTestCase, self).testDelete()




