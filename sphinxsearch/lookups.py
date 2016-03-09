# coding: utf-8

from django.db.models.lookups import In
from django.db.models.fields import Field

sphinx_lookups = Field.class_lookups.copy()


class SphinxIn(In):
    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.batch_process_rhs(compiler, connection)
        rhs_sql = ', '.join(['%s' for _ in range(len(rhs_params))])
        return '(IN(%s, %s))' % (lhs, rhs_sql), rhs_params


sphinx_lookups['in'] = SphinxIn
