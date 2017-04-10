from distutils.core import setup
import sys

if sys.version_info < (3, 0):
    mysql = 'MySQL-python'
else:
    mysql = 'PyMySQL'

try:
    # noinspection PyPackageRequirements
    from pypandoc import convert
    read_md = lambda f: convert(f, 'rst')
except ImportError:
    print("warning: pypandoc not found, could not convert Markdown to RST")
    read_md = lambda f: open(f, 'r').read()

setup(
    name='django_sphinxsearch',
    version='0.8.1',
    long_description=read_md('README.md'),
    packages=[
        'sphinxsearch',
        'sphinxsearch.backend',
        'sphinxsearch.backend.sphinx',
    ],
    url='http://github.com/rutube/django_sphinxsearch',
    license='Beerware',
    author='tumbler',
    author_email='zimbler@gmail.com',
    description='Sphinxsearch database backend for django>=1.8',
    setup_requires=[
        'Django>=1.8',
        mysql
    ],
)
