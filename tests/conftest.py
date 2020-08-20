from collections import namedtuple
from contextlib import contextmanager
from http.server import HTTPServer, SimpleHTTPRequestHandler
import logging
from multiprocessing import Process, Queue
from subprocess import check_output, CalledProcessError
from os import chdir
import os
from os.path import join as p, exists, split as split_path, isdir, isabs
from textwrap import dedent
import shutil
import shlex
import tempfile

from owmeta_core.bundle import (Descriptor, Installer, find_bundle_directory,
                                AccessorConfig, Remote, Fetcher)
from owmeta_core.bundle.loaders import Loader
from owmeta_core.bundle.archive import Archiver
from owmeta_core.command import DEFAULT_OWM_DIR, OWM
from pytest import fixture
from rdflib.term import URIRef
from rdflib.graph import ConjunctiveGraph
import requests


L = logging.getLogger(__name__)


@fixture
def tempdir():
    with tempfile.TemporaryDirectory(prefix=__name__ + '.') as td:
        yield td


class ServerData():
    def __init__(self, server, request_queue):
        self.server = server
        self.requests = request_queue
        self.scheme = 'http'

    @property
    def url(self):
        return self.scheme + '://{}:{}'.format(*self.server.server_address)


@contextmanager
def _http_server():
    srvdir = tempfile.mkdtemp(prefix=__name__ + '.')
    process = None
    request_queue = Queue()
    try:
        server = make_server(request_queue)

        def pfunc():
            chdir(srvdir)
            server.serve_forever()

        process = Process(target=pfunc)

        server_data = ServerData(server, request_queue)

        def start():
            process.start()
            wait_for_started(server_data)

        server_data.start = start
        yield server_data
    finally:
        if process:
            process.terminate()
            process.join()
        shutil.rmtree(srvdir)


@fixture
def https_server():
    import ssl
    with _http_server() as server_data:
        server_data.server.socket = \
                ssl.wrap_socket(server_data.server.socket,
                        certfile=p('tests', 'cert.pem'),
                        keyfile=p('tests', 'key.pem'),
                        server_side=True)
        server_data.start()
        server_data.ssl_context = ssl.SSLContext()
        server_data.ssl_context.load_verify_locations(p('tests', 'cert.pem'))
        server_data.scheme = 'https'
        yield server_data


@fixture
def http_server():
    with _http_server() as server_data:
        server_data.start()
        yield server_data


def make_server(request_queue):
    class _Handler(SimpleHTTPRequestHandler):
        def handle_request(self, code):
            request_queue.put(dict(
                method=self.command,
                path=self.path,
                headers={k.lower(): v for k, v in self.headers.items()}))
            self.send_response(code)
            self.end_headers()

        def do_POST(self):
            self.handle_request(201)

    port = 8000
    while True:
        try:
            server = HTTPServer(('127.0.0.1', port), _Handler)
            break
        except OSError as e:
            if e.errno != 98:
                raise
            port += 1

    return server


def wait_for_started(server_data, max_tries=10):
    done = False
    tries = 0
    while not done and tries < max_tries:
        tries += 1
        try:
            requests.head(server_data.url)
            done = True
        except Exception:
            L.info("Unable to connect to the bundle server. Trying again.", exc_info=True)


@fixture
def owm_project_with_customizations(request):
    return contextmanager(_owm_project_helper(request))


@fixture
def core_bundle(request):
    CoreBundle = namedtuple('CoreBundle', ('id', 'version', 'source_directory', 'remote'))
    version_mark = request.node.get_closest_marker('core_bundle_version')
    if not version_mark:
        raise Exception('Must specify a version of the core bundle')
    version = version_mark.args[0]
    source_directory = find_bundle_directory('bundles', 'openworm/owmeta-core', version)

    class TestAC(AccessorConfig):
        def __eq__(self, other):
            return other is self

        def __hash__(self):
            return object.__hash__(self)

    class TestBundleLoader(Loader):
        def __init__(self, ac):
            pass

        def bundle_versions(self):
            return [1]

        @classmethod
        def can_load_from(cls, ac):
            if isinstance(ac, TestAC):
                return True
            return False

        def can_load(self, ident, version): return True

        def load(self, ident, version):
            shutil.copytree(source_directory, self.base_directory)

    TestBundleLoader.register()
    remote = Remote('test', (TestAC(),))

    yield CoreBundle(
            'openworm/owmeta-core',
            version,
            source_directory,
            remote)


def _owm_project_helper(request):
    def f(*args, **kwargs):
        res = _shell_helper(*args, **kwargs)
        try:
            default_context_id = 'http://example.org/data'
            res.sh(f'owm -b init --default-context-id "{default_context_id}"')

            add_core_bundle = request.node.get_closest_marker('core_bundle')
            if add_core_bundle:
                core_bundle = request.getfixturevalue('core_bundle')
                bundles_directory = p(res.test_homedir, '.owmeta', 'bundles')
                fetcher = Fetcher(bundles_directory, (core_bundle.remote,))
                fetcher.fetch(core_bundle.id, core_bundle.version)

            res.owmdir = p(res.testdir, DEFAULT_OWM_DIR)
            res.default_context_id = default_context_id

            def owm(**kwargs):
                r = OWM(owmdir=p(res.testdir, '.owm'), **kwargs)
                r.userdir = p(res.test_homedir, '.owmeta')
                return r

            res.owm = owm

            yield res
        finally:
            shutil.rmtree(res.testdir)
    return f


@fixture
def owm_project(request):
    with contextmanager(_owm_project_helper(request))() as f:
        yield f


@fixture
def shell_helper():
    res = _shell_helper()
    try:
        yield res
    finally:
        shutil.rmtree(res.testdir)


@fixture
def shell_helper_with_customizations():
    @contextmanager
    def f(*args, **kwargs):
        res = _shell_helper(*args, **kwargs)
        try:
            yield res
        finally:
            shutil.rmtree(res.testdir)
    return f


def _shell_helper(customizations=None):
    res = Data()
    os.mkdir(res.test_homedir)
    with open(p('tests', 'pytest-cov-embed.py'), 'r') as f:
        ptcov = f.read()
    # Added so pytest_cov gets to run for our subprocesses
    with open(p(res.testdir, 'sitecustomize.py'), 'w') as f:
        f.write(ptcov)
        f.write('\n')

    def apply_customizations():
        if customizations:
            with open(p(res.testdir, 'sitecustomize.py'), 'a') as f:
                f.write(dedent(customizations))

    res.apply_customizations = apply_customizations
    return res


class Data(object):
    exception = None

    def __init__(self):
        self.testdir = tempfile.mkdtemp(prefix=__name__ + '.')
        self.test_homedir = p(self.testdir, 'homedir')

    def __str__(self):
        items = []
        for m in vars(self):
            if (m.startswith('_') or m == 'sh'):
                continue
            items.append(m + '=' + repr(getattr(self, m)))
        return 'Data({})'.format(', '.join(items))

    def copy(self, source, dest):
        if isdir(source):
            return shutil.copytree(source, p(self.testdir, dest))
        else:
            return shutil.copy(source, p(self.testdir, dest))

    def make_module(self, module):
        if isabs(module):
            raise Exception('Must use a relative path. Given ' + str(module))
        modpath = p(self.testdir, module)
        os.makedirs(modpath)
        last_dname = None
        dname = modpath
        while last_dname != dname and dname != self.testdir:
            open(p(dname, '__init__.py'), 'x').close()
            base = ''
            while not base and last_dname != dname:
                last_dname = dname
                dname, base = split_path(modpath)

        return modpath

    def writefile(self, name, contents=None):
        if contents is None:
            contents = name
        fname = p(self.testdir, name)
        with open(fname, 'w') as f:
            if exists(contents):
                print(open(contents).read(), file=f)
            else:
                print(dedent(contents), file=f)
            f.flush()
        return fname

    def sh(self, *command, **kwargs):
        if not command:
            return None
        env = dict(os.environ)
        env['PYTHONPATH'] = self.testdir + ((os.pathsep + env['PYTHONPATH'])
                                            if 'PYTHONPATH' in env
                                            else '')
        env['HOME'] = self.test_homedir
        env.update(kwargs.pop('env', {}))
        outputs = []
        for cmd in command:
            try:
                outputs.append(check_output(shlex.split(cmd), env=env, cwd=self.testdir, **kwargs).decode('utf-8'))
            except CalledProcessError as e:
                if e.output:
                    print(dedent('''\
                    ----------stdout from "{}"----------
                    {}
                    ----------{}----------
                    ''').format(cmd, e.output.decode('UTF-8'),
                               'end stdout'.center(14 + len(cmd))))
                if getattr(e, 'stderr', None):
                    print(dedent('''\
                    ----------stderr from "{}"----------
                    {}
                    ----------{}----------
                    ''').format(cmd, e.stderr.decode('UTF-8'),
                               'end stderr'.center(14 + len(cmd))))
                raise
        return outputs[0] if len(outputs) == 1 else outputs

    __repr__ = __str__


@fixture
def bundle():
    with bundle_helper(Descriptor('test')) as data:
        yield data


@fixture
def bundle_archive():
    with bundle_archive_helper(Descriptor('test')) as data:
        yield data


@fixture
def custom_bundle_archive():
    yield bundle_archive_helper


@fixture
def custom_bundle():
    yield bundle_helper


@contextmanager
def bundle_helper(descriptor, graph=None, bundles_directory=None, homedir=None, **kwargs):
    '''
    Helper for creating bundles for testing.

    Uses `~owmeta_core.bundle.Installer` to lay out a bundle

    Parameters
    ----------
    descriptor : Descriptor
        Describes the bundle
    graph : rdflib.graph.ConjunctiveGraph, optional
        Graph from which the bundle contexts will be generated. If not provided, a graph
        will be created with the triple ``(ex:a, ex:b, ex:c)`` in a context named ``ex:ctx``,
        where ``ex:`` expands to ``http://example.org/``
    bundles_directory : str, optional
        The directory where the bundles should be installed. If not provided, creates a
        temporary directory to house the bundles and cleans them up afterwards
    homedir : str, optional
        Test home directory. If not provided, one will be created based on test directory
    '''
    res = BundleData()
    with tempfile.TemporaryDirectory(prefix=__name__ + '.') as testdir:
        res.testdir = testdir
        res.test_homedir = homedir or p(res.testdir, 'homedir')
        res.bundle_source_directory = p(res.testdir, 'bundle_source')
        res.bundles_directory = bundles_directory or p(res.test_homedir, '.owmeta', 'bundles')
        if not homedir:
            os.mkdir(res.test_homedir)
        os.mkdir(res.bundle_source_directory)
        if not bundles_directory:
            os.makedirs(res.bundles_directory)

        # This is a bit of an integration test since it would be a PITA to maintain the bundle
        # format separately from the installer
        res.descriptor = descriptor
        if graph is None:
            graph = ConjunctiveGraph()
            ctxg = graph.get_context(URIRef('http://example.org/ctx'))
            ctxg.add((URIRef('http://example.org/a'),
                      URIRef('http://example.org/b'),
                      URIRef('http://example.org/c')))
        res.installer = Installer(res.bundle_source_directory,
                                  res.bundles_directory,
                                  graph=graph,
                                  **kwargs)
        res.bundle_directory = res.installer.install(res.descriptor)
        yield res


@contextmanager
def bundle_archive_helper(*args, pre_pack_callback=None, **kwargs):
    with bundle_helper(*args, **kwargs) as bundle_data:
        if pre_pack_callback:
            pre_pack_callback(bundle_data)
        bundle_data.archive_path = Archiver(bundle_data.testdir).pack(
                bundle_directory=bundle_data.bundle_directory,
                target_file_name='bundle.tar.xz')
        yield bundle_data


class BundleData(object):
    pass
