# -*- coding: utf-8 -*-

"""
.. _owm_module:

owmeta
======

OpenWorm Unified Data Abstract Layer.

An introduction to owmeta can be found in the README on our
`Github page <https://github.com/openworm/owmeta>`_.

Most statements correspond to some action on the database.
Some of these actions may be complex, but intuitively ``a.B()``, the Query form,
will query against the database for the value or values that are related to ``a`` through ``B``;
on the other hand, ``a.B(c)``, the Update form, will add a statement to the database that ``a``
relates to ``c`` through ``B``. For the Update form, a Statement object describing the
relationship stated is returned as a side-effect of the update.

The Update form can also be accessed through the set() method of a Property and the Query form through the get()
method like::

    a.B.set(c)

and::

    a.B.get()

The get() method also allows for parameterizing the query in ways specific to the Property.

"""

from __future__ import print_function
__version__ = '0.11.3.dev0'
__author__ = 'Stephen Larson'

import sys
import os
import logging
import uuid

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

BASE_SCHEMA_URL = 'http://openworm.org/schema'

# The c extensions are incompatible with our code...
os.environ['WRAPT_DISABLE_EXTENSIONS'] = '1'
from .import_override import Overrider
from .module_recorder import ModuleRecorder as MR
from .mapper import Mapper

ImportOverrider = None
ModuleRecorder = None


BASE_MAPPER = Mapper(name='base')
'''
Handles some of the owmeta DataObjects regardless of whether there's been any connection. Used by Contexts outside
of a connection.
'''


def install_module_import_wrapper():
    global ImportOverrider
    global ModuleRecorder

    if ImportOverrider is None:
        ModuleRecorder = MR()
        ImportOverrider = Overrider(mapper=ModuleRecorder)
        ImportOverrider.wrap_import()
    else:
        LOGGER.info("Import overrider already installed")
    return ImportOverrider


install_module_import_wrapper()
ModuleRecorder.add_listener(BASE_MAPPER)
from .configure import Configureable
from .context import Context
import yarom

__all__ = [
    "get_data",
    "loadConfig",
    "disconnect",
    "connect",
    "config",
    ]

DEF_CTX = Context()

RDF_CONTEXT = Context(ident='http://www.w3.org/1999/02/22-rdf-syntax-ns',
                      base_namespace='http://www.w3.org/1999/02/22-rdf-syntax-ns#')

RDFS_CONTEXT = Context(ident='http://www.w3.org/2000/01/rdf-schema',
                       imported=(RDF_CONTEXT,),
                       base_namespace='http://www.w3.org/2000/01/rdf-schema#')

BASE_CONTEXT = Context(imported=(RDFS_CONTEXT,),
                       ident=BASE_SCHEMA_URL,
                       base_namespace=BASE_SCHEMA_URL + '#')


def get_data(path):
    # get a resource from the installed package location

    from sysconfig import get_path
    from pkgutil import get_loader
    from glob import glob
    package_paths = glob(os.path.join(get_path('platlib'), '*'))
    sys.path = package_paths + sys.path
    installed_package_root = os.path.dirname(get_loader('owmeta').get_filename())
    sys.path = sys.path[len(package_paths):]
    filename = os.path.join(installed_package_root, path)
    return filename


def config(key=None):
    """
    Gets the main configuration for the whole owmeta library.

    :return: the instance of the Configure class currently operating.
    """
    if key is None:
        return Configureable.default
    else:
        return Configureable.default[key]


class Connection(object):

    def __init__(self, conf):
        self.conf = conf

        self.identifier = str(uuid.uuid4())
        '''
        Identifier for this connection.

        Primarily, so that this Connection can be passed to contextualize for a Context
        '''

    def disconnect(self):
        self.conf.closeDatabase()
        ModuleRecorder.remove_listener(self.conf['mapper'])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.disconnect()

    def __call__(self, target):
        '''
        Contextualize the given `Context`
        '''
        # XXX: May be able to loosen th
        if target is not None and issubclass(target, Context):
            return target.contextualize(self)
        else:
            raise TypeError('Connections can only contextualize owmeta.context.Context'
                    ' or subclasses thereof. Received %s' % target)

    def __str__(self):
        conf = self.conf
        return 'Connection:{source}:{store_conf}'.format(
                source=conf.get('rdf.source'),
                store_conf=conf.get('rdf.store_conf', 'default'))


def loadConfig(f):
    """ Load configuration for the module. """
    from .data import Data
    return Data.open(f)


def disconnect(c=False):
    """ Close the database. """
    if c:
        c.disconnect()


class ConnectionFailError(Exception):
    def __init__(self, cause, *args):
        if args:
            super(ConnectionFailError, self).__init__('owmeta connection failed: {}. {}'.format(cause, *args))
        else:
            super(ConnectionFailError, self).__init__('owmeta connection failed: {}'.format(cause))


def connect(configFile=None,
            conf=None,
            dataFormat='n3'):
    """
    Load desired configuration and open the database

    :param configFile: (Optional) The configuration file for owmeta
    :param conf: (Optional) a configuration object for the connection. Takes precedence over `configFile`
    :param data: (Optional) specify the file to load into the library
    :param dataFormat: (Optional) file format of `data`. Currently n3 is supported
    """
    from .data import Data, DatabaseConflict

    if configFile is not None and not isinstance(configFile, str):
        conf = configFile
        configFile = None

    if conf:
        if not isinstance(conf, Data):
            conf = Data(conf)
    elif configFile:
        conf = Data.open(configFile)
    else:
        conf = Data({"rdf.source": "default"})

    try:
        conf.init_database()
    except DatabaseConflict as e:
        raise ConnectionFailError(e, "It looks like a connection is already opened by a living process")
    except Exception as e:
        raise ConnectionFailError(e)

    logging.getLogger('owmeta').info("Connected to database")

    # Base class names is empty because we won't be adding any objects to the
    # context automatically
    mapper = Mapper()
    conf['mapper'] = mapper
    # An "empty" context, that serves as the default when no context is defined

    yarom.MAPPER = mapper

    ModuleRecorder.add_listener(mapper)

    return Connection(conf)
