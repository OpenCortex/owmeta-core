from __future__ import print_function
import sys
import json
from os import environ
from itertools import groupby
import logging

import six
from tqdm import tqdm
from pkg_resources import iter_entry_points

from .cli_command_wrapper import CLICommandWrapper, CLIUserError
from .cli_hints import CLI_HINTS
from .command import OWM
from .git_repo import GitRepoProvider
from .text_util import format_table
from .command_util import GeneratorWithData, GenericUserError, SubCommand


CLI_HINTS_GROUP = 'owmeta_core.cli_hints'
COMMANDS_GROUP = 'owmeta_core.commands'

L = logging.getLogger(__name__)


def additional_args(parser):
    'Add some additional options specific to CLI'
    # The "Default is '<blah>'" part of help is to match the cli_command_wrapper output
    parser.add_argument('--output-mode', '-o', default='text',
            help='How to print the results of a command'
            ' (if any). Default is \'text\'',
            choices=['json', 'text', 'table'])
    parser.add_argument('--columns',
            help='Comma-separated list of columns to display in "table" output mode')
    parser.add_argument('--text-field-separator', default='\t',
            help=r'Separator to use between fields in "text" output mode. Default is'
            r" '\t' (tab character)")
    parser.add_argument('--text-record-separator', default='\n',
            help='Separator to use between records in "text" output mode. Default is'
            r" '\n' (newline)")
    parser.add_argument('--progress',
            help='Progress reporter to use. Default is \'tqdm\'',
            choices=['tqdm', 'none'],
            default='tqdm')


def parse_progress(s):
    if s == 'tqdm':
        return tqdm


def die(message, status=1):
    print(message, file=sys.stderr)
    raise SystemExit(1)


NOT_SET = object()


class NSHandler(object):
    def __init__(self, command, **kwargs):
        self.command = command
        self.opts = dict(kwargs)

    def __getitem__(self, k):
        return self.opts[k]

    def __getattr__(self, k, default=NOT_SET):
        if default is NOT_SET:
            try:
                return self.opts[k]
            except KeyError:
                raise AttributeError()
        else:
            return self.opts.get(k, default)

    def __call__(self, ns):
        self.opts['output_mode'] = ns.output_mode
        self.opts['text_field_separator'] = ns.text_field_separator
        self.opts['text_record_separator'] = ns.text_record_separator
        self.opts['columns'] = ns.columns
        prog = parse_progress(ns.progress)
        if prog:
            self.command.progress_reporter = prog

    def __str__(self):
        return 'NSHandler' + str(self.opts)


class JSONSerializer(object):
    def __call__(self, o):
        from rdflib.graph import Graph
        from owmeta_core.context import Context
        if isinstance(o, Graph):
            # eventually, we will use something like JSON-LD
            return []
        elif isinstance(o, Context):
            return {'identifier': o.identifier,
                    'base_namespace': o.base_namespace}
        else:
            return list(o)


def _select(a, indexes):
    return [h for h, i in zip(a, range(len(a))) if i in indexes]


def columns_arg_to_list(arg):
    return [s.strip() for s in arg.split(',')]


def main():
    logging.basicConfig()
    top_command = _augment_subcommands_from_entry_points()
    p = top_command()
    p.log_level = 'WARN'
    p.message = print
    p.repository_provider = GitRepoProvider()
    p.non_interactive = False
    ns_handler = NSHandler(p)
    if environ.get('OWM_CLI_PROFILE'):
        from cProfile import Profile
        profiler = Profile()
        profiler.enable()
    out = None

    hints = dict()
    hints.update(CLI_HINTS)
    hints.update(_gather_hints_from_entry_points())

    try:
        out = CLICommandWrapper(p, hints_map=hints).main(
                argument_callback=additional_args,
                argument_namespace_callback=ns_handler)
    except (CLIUserError, GenericUserError) as e:
        s = str(e)
        if not s:
            from yarom.utils import FCN
            # In case someone forgets to add a helpful message for their user error
            s = 'Received error: ' + FCN(type(e))
        die(s)
    output_mode = ns_handler.output_mode
    text_field_separator = ns_handler.text_field_separator
    text_record_separator = ns_handler.text_record_separator

    if out is not None:
        if output_mode == 'json':
            json.dump(out, sys.stdout, default=JSONSerializer(), indent=2)
        elif output_mode == 'table':
            # `out.header` holds the *names* for each column whereas `out.columns` holds
            # accessors for each column. `out` must have either:
            # 1) Just `header`
            # 2) `header` and `columns`
            # 3) neither `header` nor `columns`
            # at least one to be valid.
            #
            # If `out` has only `header`, then `header must have one element which is the
            # header for a single result from `out`.
            #
            # If it has `header` and `columns` then the two must be of equal length and
            # each element of `header` names the result of the corresponding entry in
            # `columns`.
            #
            # If neither `header` nor `columns` is given, then a default header of
            # `['Value']` is used and the column accessor is the identify function.
            #
            # `out.default_columns` determines which columns to show by default. If there
            # is no `default_columns`, then all defined columns are shown. The columns can
            # be overriden by the `--columns` command line argument. If there is no
            # `header`, but `--columns` is provided, the user will get an error.

            # N.B.: we use getattr rather than hasattr because we want to make sure we
            # have the attribute AND that the columns/header isn't an empty or tuple/list
            if getattr(out, 'columns', None) and getattr(out, 'header', None):
                if ns_handler.columns:
                    selected_columns = [i for i, e in zip(range(len(out.header)), out.header)
                                        if e in columns_arg_to_list(ns_handler.columns)]
                    if not selected_columns:
                        die('The given list of columns is not valid for this command')
                elif getattr(out, 'default_columns', None):
                    selected_columns = [i for i, e in zip(range(len(out.header)), out.header)
                                        if e in out.default_columns]
                else:
                    selected_columns = list(range(len(out.header)))
            elif getattr(out, 'columns', None):
                raise Exception('Programmer error: A header must be provided if an output'
                                ' has multiple columns')
            elif getattr(out, 'header', None):
                if len(out.header) != 1:
                    raise Exception('Programmer error: Only one column in the header can be defined if'
                                    ' no columns are defined')
                if ns_handler.columns \
                        and columns_arg_to_list(ns_handler.columns) != out.header:
                    die('The given list of columns is not valid for this command')
                out = GeneratorWithData(out,
                                        columns=[lambda x: x],
                                        header=out.header)
                selected_columns = [0]
            elif ns_handler.columns:
                die('The given list of columns is not valid for this command')
            else:
                out = GeneratorWithData(out,
                                        columns=[lambda x: x],
                                        header=['Value'])
                selected_columns = [0]

            header = _select(out.header, selected_columns)
            columns = _select(out.columns, selected_columns)

            def mygen():
                if columns:
                    for m in out:
                        yield tuple(c(m) for c in columns)
                else:
                    for m in out:
                        yield (m,)
            print(format_table(mygen(), header=header))
        elif output_mode == 'text':
            if isinstance(out, dict):
                for k, v in out.items():
                    print('{}{}{}'.format(k, text_field_separator, v), end=text_record_separator)
            elif isinstance(out, six.string_types):
                print(out)
            else:
                try:
                    iterable = (x for x in out)
                except TypeError:
                    print(out)
                else:
                    for x in iterable:
                        if hasattr(out, 'text_format'):
                            print(out.text_format(x), end=text_record_separator)
                        else:
                            print(x, end=text_record_separator)

    if environ.get('OWM_CLI_PROFILE'):
        profiler.disable()
        profiler.dump_stats(environ['OWM_CLI_PROFILE'])


def _gather_hints_from_entry_points():
    res = dict()
    for entry_point in iter_entry_points(CLI_HINTS_GROUP):
        try:
            res.update(entry_point.load())
        except Exception:
            L.warning('Unable to add CLI hints for %s', entry_point)
    return res


def _augment_subcommands_from_entry_points():
    command_map = {(): OWM}
    unordered_commands = []
    for entry_point in iter_entry_points(COMMANDS_GROUP):
        name = str(entry_point.name).strip()
        path = tuple(name.split('.'))
        try:
            unordered_commands.append((path, entry_point.load()))
        except Exception:
            L.warning('Unable to add command', entry_point)
            pass
    level_ordered_commands = \
        sorted(unordered_commands, key=lambda x: (len(x[0]), x[0]))
    # Group by everything up-to a given command
    for indicator, level in groupby(level_ordered_commands,
            key=lambda x: (len(x[0]), x[0][:-1])):
        override_dict = dict()
        level_key = None
        for path, cmd in level:
            level_key = path[:-1]
            override_dict[path[-1]] = SubCommand(cmd)

        if level_key is not None:
            orig_cmd = command_map.get(level_key)
            if not orig_cmd:
                last = command_map[()]
                for idx, component in enumerate(level_key):
                    cmd = command_map.get(level_key[:idx+1])
                    if not cmd:
                        cmd = getattr(last, component).cmd
                        command_map[level_key[:idx+1]] = cmd
                    last = cmd
                orig_cmd = last

            override_dict['__module__'] = orig_cmd.__module__
            command_map[level_key] = type(orig_cmd.__name__, (orig_cmd,), override_dict)
            if level_key:
                setattr(command_map[level_key[:-1]], level_key[-1], SubCommand(command_map[level_key]))

    return command_map[()]


if __name__ == '__main__':
    main()
