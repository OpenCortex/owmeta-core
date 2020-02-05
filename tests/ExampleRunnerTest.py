from __future__ import absolute_import
import unittest
import os
import subprocess as SP
import shutil
import shlex
import tempfile
from six import string_types
from os.path import join as p

from .TestUtilities import xfail_without_db


class ExampleRunnerTest(unittest.TestCase):

    """ Runs the examples to make sure we didn't break the API for them. """

    # Currently these are all failing because we aren't reproducing the actual data that
    # a user gets when they grab the code for the first time

    @classmethod
    def setUpClass(self):
        self.testdir = tempfile.mkdtemp(prefix=__name__ + '.')
        shutil.copytree('examples', p(self.testdir, 'examples'), symlinks=True)
        self.startdir = os.getcwd()
        os.chdir(p(self.testdir, 'examples'))

    def setUp(self):
        xfail_without_db()

    @classmethod
    def tearDownClass(self):
        os.chdir(self.startdir)
        shutil.rmtree(self.testdir)

    def execfile(self, example_file_name):
        self.exec_(["python", example_file_name])

    def exec_(self, command, **kwargs):
        if isinstance(command, string_types):
            command = shlex.split(command)
        fname = tempfile.mkstemp()[1]
        with open(fname, 'w+') as out:
            stat = SP.call(command,
                           stdout=out,
                           stderr=out,
                           **kwargs)
            out.seek(0)
            self.assertEqual(0, stat,
                "Example failed with status {}. Its output:\n{}".format(
                    stat,
                    out.read()))
        os.unlink(fname)

    def test_owm_save(self):
        os.mkdir(p(self.testdir, '.owm'))
        self.exec_("owm init --imports_context_id 'http://example.org'", cwd=self.testdir)
        self.exec_("owm save examples.owm_save_example", cwd=self.testdir)
