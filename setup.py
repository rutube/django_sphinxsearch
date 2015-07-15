from distutils.core import setup

setup(
    name='django_sphinxsearch',
    version='0.0.1',
    packages=[
        'sphinxsearch',
        'sphinxsearch.backend',
        'sphinxsearch.backend.sphinx',

    ],
    url='http://github.com/tumb1er/django_sphinxsearch',
    license='Beer License',
    author='tumbler',
    author_email='zimbler@gmail.com',
    description='Sphinxsearch database backend for django',
)
