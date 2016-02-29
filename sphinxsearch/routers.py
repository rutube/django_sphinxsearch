# coding: utf-8

# $Id: $


from django.conf import settings


class SphinxRouter(object):
    """
    Routes database operations for Sphinx model to the sphinx database connection.
    """

    def is_sphinx_model(self, model_or_obj):
        from sphinxsearch.models import SphinxModel
        from sphinxsearch.sql import SphinxModelBase
        if type(model_or_obj) is not SphinxModelBase:
            model = model_or_obj.__class__
        else:
            model = model_or_obj
        is_sphinx_model = issubclass(model, SphinxModel) or type(model) is SphinxModelBase
        return is_sphinx_model

    def db_for_read(self, model, **kwargs):
        if self.is_sphinx_model(model):
            return getattr(settings, 'SPHINX_DATABASE_NAME', 'sphinx')

    def db_for_write(self, model, **kwargs):
        if self.is_sphinx_model(model):
            return getattr(settings, 'SPHINX_DATABASE_NAME', 'sphinx')

    def allow_relation(self, obj1, obj2, **kwargs):
        # Allow all relations...
        return True
