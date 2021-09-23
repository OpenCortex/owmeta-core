# -*- coding: utf-8 -*-

from __future__ import absolute_import
import unittest
import logging
from owmeta_core.data import Data
import rdflib as R
import os
from os.path import join as p
import tempfile
import shutil
from pytest import mark

from .GraphDBInit import make_graph, has_bsddb


class _DatabaseBackendBT(object):
    ''' Integration tests for the database backend '''

    def setUp(self):
        self.testdir = tempfile.mkdtemp(prefix=__name__ + '.')
        self.dat = Data()
        self._configure(self.dat)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

    def tearDown(self):
        shutil.rmtree(self.testdir)

    def test_namespace_manager(self):
        self.dat.init()
        self.assertIsInstance(self.dat['rdf.namespace_manager'], R.namespace.NamespaceManager)

    def test_init_no_rdf_store(self):
        """ Should be able to init without these values """
        d = Data()
        d.init()

    def test(self):
        try:
            self.dat.init()
            g = make_graph(20)
            for x in g:
                self.dat['rdf.graph'].add(x)
            self.dat.destroy()

            self.dat.init()
            self.assertEqual(20, len(self.dat['rdf.graph']))
        finally:
            self.dat.destroy()


@unittest.skipIf(not os.environ.get('SQLITE_TEST'), 'SQLITE_TEST not defined')
@mark.sqlite_source
class SQLitePersistenceTest(_DatabaseBackendBT, unittest.TestCase):
    def _configure(self, conf):
        fname = p(self.testdir, 'sqlite.db')
        conf['rdf.source'] = 'sqlite'
        conf['rdf.store_conf'] = fname


class ZODBPersistenceTest(_DatabaseBackendBT, unittest.TestCase):
    def _configure(self, conf):
        fname = p(self.testdir, 'ZODB.fs')
        conf['rdf.source'] = 'ZODB'
        conf['rdf.store_conf'] = fname


@unittest.skipIf(not os.environ.get('MYSQL_TEST'), 'MYSQL_TEST not defined')
@unittest.skipIf(not os.environ.get('MYSQL_URI'), 'MYSQL_URI not defined')
@mark.mysql_source
class MySQLPersistenceTest(_DatabaseBackendBT, unittest.TestCase):
    def _configure(self, conf):
        conf['rdf.source'] = 'mysql'
        sqlalchemy_url = os.environ.get("MYSQL_URI")
        if not sqlalchemy_url:
            raise Exception('Must provide a database URI for MySQL source tests')
        conf['rdf.store_conf'] = sqlalchemy_url


@unittest.skipIf(not os.environ.get('POSTGRES_TEST'), 'POSTGRES_TEST not defined')
@unittest.skipIf(not os.environ.get('POSTGRES_URI'), 'POSTGRES_URI not defined')
@mark.postgres_source
class PostgresPersistenceTest(_DatabaseBackendBT, unittest.TestCase):
    def _configure(self, conf):
        conf['rdf.source'] = 'postgresql'
        sqlalchemy_url = os.environ.get("POSTGRES_URI")
        if not sqlalchemy_url:
            raise Exception('Must provide a database URI for Postgres source tests')
        conf['rdf.store_conf'] = sqlalchemy_url


@unittest.skipIf(not has_bsddb, "Sleepycat requires working bsddb")
class SleepycatPersistenceTest(_DatabaseBackendBT, unittest.TestCase):
    def _configure(self, conf):
        fname = p(self.testdir, 'Sleepycat_store')
        conf['rdf.source'] = 'Sleepycat'
        conf['rdf.store_conf'] = fname
