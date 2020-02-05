# -*- coding: utf-8 -*-
#

from setuptools import setup
import os
import sys


long_description = """
owmeta-core
===========

owmeta-core is a platform for sharing relational data over the internet.
"""


for line in open('owmeta_core/__init__.py'):
    if line.startswith("__version__"):
        version = line.split("=")[1].strip()[1:-1]

package_data_excludes = ['.*', '*.bkp', '~*']


def excludes(base):
    res = []
    for x in package_data_excludes:
        res.append(os.path.join(base, x))
    return res


setup(
    name='owmeta-core',
    zip_safe=False,
    setup_requires=['pytest-runner'],
    tests_require=[
        'pytest>=3.4.0',
        'pytest-cov>=2.5.1',
        'discover==0.4.0',
        'requests',
        'pytest-parallel'
    ],
    install_requires=[
        'bibtexparser~=1.1.0',
        'BTrees>=4.0.8',
        'gitpython>=2.1.1',
        'lazy-object-proxy==1.2.1',
        'libneuroml',
        'numpydoc>=0.7.0',
        'persistent>=4.0.8',
        'Pint==0.8.1',
        'pow-store-zodb==0.0.7',
        'rdflib>=4.1.2',
        'six~=1.10',
        'tqdm~=4.23',
        'termcolor==1.1.0',
        'transaction>=1.4.4',
        'wrapt~=1.11.1',
        'yarom~=0.12.0.dev0',
        'zc.lockfile',
        'ZConfig==3.0.4',
        'zdaemon==4.0.0',
        'zodb>=4.1.0',
        'rdflib-sqlalchemy~=0.4.0',
        'pyyaml',
    ],
    extras_require={
        # SQL source support
        'mysql_source_mysql_connector': [
            'mysql-connector-python'
        ],
        'mysql_source_mysqlclient': [
            'mysqlclient'
        ],
        'postgres_source_psycopg': [
            'psycopg2'
        ],
        'postgres_source_pg8000': [
            'pg8000'
        ]
    },
    version=version,
    packages=['owmeta_core',
              'owmeta_core.data_trans',
              'owmeta_core.commands'],
    author='OpenWorm.org authors and contributors',
    author_email='info@openworm.org',
    description='owmeta-core is a platform for sharing relational data over the internet.',
    long_description=long_description,
    license='MIT',
    url='https://owmeta-core.readthedocs.io/en/latest/',
    download_url='https://github.com/openworm/owmeta-core/archive/master.zip',
    entry_points={
        'console_scripts': ['owm = owmeta.cli:main']
    },
    package_data={'owmeta_core': ['default.conf']},
    classifiers=[
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Scientific/Engineering'
    ]
)
