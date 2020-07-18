# -*- coding: utf-8 -*-

"""
.. _owm_module:

owmeta_core
===========
owmeta-core is a platform for sharing relational data over the internet.
"""

from __future__ import print_function
__version__ = '0.11.3.dev0'
__author__ = 'OpenWorm.org authors and contributors'

import sys
import os
import logging
import uuid
from os.path import join as pth_join

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

BASE_SCHEMA_URL = 'http://schema.openworm.org/2020/07'

# The c extensions are incompatible with our code...
os.environ['WRAPT_DISABLE_EXTENSIONS'] = '1'
from .import_override import Overrider
from .module_recorder import ModuleRecorder as MR
from .mapper import Mapper

ImportOverrider = None
ModuleRecorder = None


OWMETA_PROFILE_DIR = os.environ.get('OWMETA_PROFILE_DIR', pth_join('~', '.owmeta'))
'''
Base directory in the user's profile for owmeta (e.g., shared configuration, bundle cache)
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
from .configure import Configurable
from .context import Context, ClassContext

__all__ = [
    "get_data",
    "disconnect",
    "connect",
    "Configurable",
]

DEF_CTX = Context()

RDF_CONTEXT = ClassContext(ident='http://www.w3.org/1999/02/22-rdf-syntax-ns',
        base_namespace='http://www.w3.org/1999/02/22-rdf-syntax-ns#')

RDFS_CONTEXT = ClassContext(ident='http://www.w3.org/2000/01/rdf-schema',
        imported=(RDF_CONTEXT,),
        base_namespace='http://www.w3.org/2000/01/rdf-schema#')

BASE_CONTEXT = ClassContext(imported=(RDFS_CONTEXT,),
        ident=BASE_SCHEMA_URL,
        base_namespace=BASE_SCHEMA_URL + '#')


def get_data(path):
    # get a resource from the installed package location

    from sysconfig import get_path
    from pkgutil import get_loader
    from glob import glob
    package_paths = glob(os.path.join(get_path('platlib'), '*'))
    sys.path = package_paths + sys.path
    installed_package_root = os.path.dirname(get_loader('owmeta_core').get_filename())
    sys.path = sys.path[len(package_paths):]
    filename = os.path.join(installed_package_root, path)
    return filename


class Connection(object):
    '''
    Connection to an owmeta_core database. Essentially, wraps a `~owmeta_core.data.Data`
    object.
    '''

    def __init__(self, conf):
        self.conf = conf

        self._context = Context(conf=self.conf)

        self.identifier = str(uuid.uuid4())
        '''
        Identifier for this connection.

        Primarily, so that this Connection can be passed to contextualize for a Context
        '''

    @property
    def transaction_manager(self):
        return self.__transaction_manager

    @transaction_manager.setter
    def transaction_manager(self, transaction_manager):
        self.__transaction_manager = transaction_manager

    @property
    def mapper(self):
        return self.conf['mapper']

    @property
    def rdf(self):
        return self.conf['rdf.graph']

    def disconnect(self):
        '''
        Close the database and stop listening to module loaders
        '''
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
        if target is not None and issubclass(target, Context):
            return target.contextualize(self._context)
        else:
            raise TypeError('Connections can only contextualize owmeta_core.context.Context'
                    ' or subclasses thereof. Received %s' % target)

    def __str__(self):
        conf = self.conf
        return 'Connection:{source}:{store_conf}'.format(
                source=conf.get('rdf.source'),
                store_conf=conf.get('rdf.store_conf', 'default'))


def disconnect(c=None):
    """ Close the connection. """
    if c:
        c.disconnect()


class ConnectionFailError(Exception):
    '''
    Thrown when a connection fails
    '''
    def __init__(self, cause, *args):
        if args:
            super(ConnectionFailError, self).__init__('owmeta_core connection failed: {}. {}'.format(cause, *args))
        else:
            super(ConnectionFailError, self).__init__('owmeta_core connection failed: {}'.format(cause))


def connect(configFile=None,
            conf=None):
    """
    Load desired configuration and open the database

    Parameters
    ----------
    configFile : str, optional
        The configuration file for owmeta_core.
    conf : dict, .Configuration, .Data, optional
        A configuration object for the connection. Takes precedence over `configFile`

    Returns
    -------
    Connection
        connection wrapping the configuration
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

    logging.getLogger('owmeta_core').info("Connected to database")

    # Base class names is empty because we won't be adding any objects to the
    # context automatically
    mapper = Mapper()
    conf['mapper'] = mapper
    # An "empty" context, that serves as the default when no context is defined

    ModuleRecorder.add_listener(mapper)

    return Connection(conf)
