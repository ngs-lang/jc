"""jc - JSON Convert
JC cli module
"""

import sys
import os
import textwrap
import signal
import shlex
import subprocess
import json
from .lib import (__version__, parser_info, all_parser_info, parsers,
                  _get_parser, _parser_is_streaming)
from . import utils
from . import tracebackplus
from .exceptions import LibraryNotInstalled, ParseError

# make pygments import optional
try:
    import pygments
    from pygments import highlight
    from pygments.style import Style
    from pygments.token import (Name, Number, String, Keyword)
    from pygments.lexers import JsonLexer
    from pygments.formatters import Terminal256Formatter
    PYGMENTS_INSTALLED = True
except Exception:
    PYGMENTS_INSTALLED = False


JC_ERROR_EXIT = 100


class info():
    version = __version__
    description = 'JSON Convert'
    author = 'Kelly Brazil'
    author_email = 'kellyjonbrazil@gmail.com'
    website = 'https://github.com/kellyjonbrazil/jc'
    copyright = '© 2019-2022 Kelly Brazil'
    license = 'MIT License'


# We only support 2.3.0+, pygments changed color names in 2.4.0.
# startswith is sufficient and avoids potential exceptions from split and int.
if PYGMENTS_INSTALLED:
    if pygments.__version__.startswith('2.3.'):
        PYGMENT_COLOR = {
            'black': '#ansiblack',
            'red': '#ansidarkred',
            'green': '#ansidarkgreen',
            'yellow': '#ansibrown',
            'blue': '#ansidarkblue',
            'magenta': '#ansipurple',
            'cyan': '#ansiteal',
            'gray': '#ansilightgray',
            'brightblack': '#ansidarkgray',
            'brightred': '#ansired',
            'brightgreen': '#ansigreen',
            'brightyellow': '#ansiyellow',
            'brightblue': '#ansiblue',
            'brightmagenta': '#ansifuchsia',
            'brightcyan': '#ansiturquoise',
            'white': '#ansiwhite',
        }
    else:
        PYGMENT_COLOR = {
            'black': 'ansiblack',
            'red': 'ansired',
            'green': 'ansigreen',
            'yellow': 'ansiyellow',
            'blue': 'ansiblue',
            'magenta': 'ansimagenta',
            'cyan': 'ansicyan',
            'gray': 'ansigray',
            'brightblack': 'ansibrightblack',
            'brightred': 'ansibrightred',
            'brightgreen': 'ansibrightgreen',
            'brightyellow': 'ansibrightyellow',
            'brightblue': 'ansibrightblue',
            'brightmagenta': 'ansibrightmagenta',
            'brightcyan': 'ansibrightcyan',
            'white': 'ansiwhite',
        }


def set_env_colors(env_colors=None):
    """
    Return a dictionary to be used in Pygments custom style class.

    Grab custom colors from JC_COLORS environment variable. JC_COLORS env
    variable takes 4 comma separated string values and should be in the
    format of:

    JC_COLORS=<keyname_color>,<keyword_color>,<number_color>,<string_color>

    Where colors are: black, red, green, yellow, blue, magenta, cyan, gray,
                      brightblack, brightred, brightgreen, brightyellow,
                      brightblue, brightmagenta, brightcyan, white, default

    Default colors:

        JC_COLORS=blue,brightblack,magenta,green
    or
        JC_COLORS=default,default,default,default
    """
    input_error = False

    if env_colors:
        color_list = env_colors.split(',')
    else:
        color_list = ['default', 'default', 'default', 'default']

    if len(color_list) != 4:
        input_error = True

    for color in color_list:
        if color != 'default' and color not in PYGMENT_COLOR:
            input_error = True

    # if there is an issue with the env variable, just set all colors to default and move on
    if input_error:
        utils.warning_message(['Could not parse JC_COLORS environment variable'])
        color_list = ['default', 'default', 'default', 'default']

    # Try the color set in the JC_COLORS env variable first. If it is set to default, then fall back to default colors
    return {
        Name.Tag: f'bold {PYGMENT_COLOR[color_list[0]]}' if color_list[0] != 'default' else f"bold {PYGMENT_COLOR['blue']}",   # key names
        Keyword: PYGMENT_COLOR[color_list[1]] if color_list[1] != 'default' else PYGMENT_COLOR['brightblack'],                 # true, false, null
        Number: PYGMENT_COLOR[color_list[2]] if color_list[2] != 'default' else PYGMENT_COLOR['magenta'],                      # numbers
        String: PYGMENT_COLOR[color_list[3]] if color_list[3] != 'default' else PYGMENT_COLOR['green']                         # strings
    }


def piped_output(force_color):
    """
    Return False if stdout is a TTY. True if output is being piped to
    another program and foce_color is True. This allows forcing of ANSI
    color codes even when using pipes.
    """
    return not sys.stdout.isatty() and not force_color


def ctrlc(signum, frame):
    """Exit with error on SIGINT"""
    sys.exit(JC_ERROR_EXIT)


def parser_shortname(parser_arg):
    """Return short name of the parser with dashes and no -- prefix"""
    return parser_arg[2:]


def parsers_text(indent=0, pad=0):
    """Return the argument and description information from each parser"""
    ptext = ''
    padding_char = ' '
    for p in all_parser_info():
        parser_arg = p.get('argument', 'UNKNOWN')
        padding = pad - len(parser_arg)
        parser_desc = p.get('description', 'No description available.')
        indent_text = padding_char * indent
        padding_text = padding_char * padding
        ptext += indent_text + parser_arg + padding_text + parser_desc + '\n'

    return ptext


def about_jc():
    """Return jc info and the contents of each parser.info as a dictionary"""
    return {
        'name': 'jc',
        'version': info.version,
        'description': info.description,
        'author': info.author,
        'author_email': info.author_email,
        'website': info.website,
        'copyright': info.copyright,
        'license': info.license,
        'python_version': '.'.join((str(sys.version_info.major), str(sys.version_info.minor), str(sys.version_info.micro))),
        'python_path': sys.executable,
        'parser_count': len(all_parser_info()),
        'parsers': all_parser_info()
    }


def helptext():
    """Return the help text with the list of parsers"""
    parsers_string = parsers_text(indent=12, pad=17)

    helptext_string = f'''\
    jc converts the output of many commands and file-types to JSON

    Usage:  COMMAND | jc PARSER [OPTIONS]

            or magic syntax:

            jc [OPTIONS] COMMAND

    Parsers:
{parsers_string}
    Options:
            -a    about jc
            -C    force color output even when using pipes (overrides -m)
            -d    debug (-dd for verbose debug)
            -h    help (-h --parser_name for parser documentation)
            -m    monochrome output
            -p    pretty print output
            -q    quiet - suppress parser warnings (-qq to ignore streaming errors)
            -r    raw JSON output
            -u    unbuffer output
            -v    version info

    Examples:
            Standard Syntax:
                $ dig www.google.com | jc --dig -p

            Magic Syntax:
                $ jc -p dig www.google.com

            Parser Documentation:
                $ jc -h --dig
    '''
    return textwrap.dedent(helptext_string)


def help_doc(options):
    """
    Returns the parser documentation if a parser is found in the arguments,
    otherwise the general help text is returned.
    """
    for arg in options:
        parser_name = parser_shortname(arg)

        if parser_name in parsers:
            p_info = parser_info(arg, documentation=True)
            compatible = ', '.join(p_info.get('compatible', ['unknown']))
            documentation = p_info.get('documentation', 'No documentation available.')
            version = p_info.get('version', 'unknown')
            author = p_info.get('author', 'unknown')
            author_email = p_info.get('author_email', 'unknown')
            doc_text = \
                f'{documentation}\n'\
                f'Compatibility:  {compatible}\n\n'\
                f'Version {version} by {author} ({author_email})\n'

            return doc_text

    return helptext()


def versiontext():
    """Return the version text"""
    py_ver = '.'.join((str(sys.version_info.major), str(sys.version_info.minor), str(sys.version_info.micro)))
    versiontext_string = f'''\
    jc version:  {info.version}
    python interpreter version:  {py_ver}
    python path:  {sys.executable}

    {info.website}
    {info.copyright}'''
    return textwrap.dedent(versiontext_string)


def json_out(data, pretty=False, env_colors=None, mono=False, piped_out=False):
    """
    Return a JSON formatted string. String may include color codes or be
    pretty printed.
    """
    separators = (',', ':')
    indent = None

    if pretty:
        separators = None
        indent = 2

    if not mono and not piped_out:
        # set colors
        class JcStyle(Style):
            styles = set_env_colors(env_colors)

        return str(highlight(json.dumps(data, indent=indent, separators=separators, ensure_ascii=False),
                             JsonLexer(), Terminal256Formatter(style=JcStyle))[0:-1])

    return json.dumps(data, indent=indent, separators=separators, ensure_ascii=False)


def magic_parser(args):
    """
    Parse command arguments for magic syntax: jc -p ls -al

    Return a tuple:
        valid_command (bool)  is this a valid cmd? (exists in magic dict)
        run_command   (list)  list of the user's cmd to run. None if no cmd.
        jc_parser     (str)   parser to use for this user's cmd.
        jc_options    (list)  list of jc options
    """
    # bail immediately if there are no args or a parser is defined
    if len(args) <= 1 or args[1].startswith('--'):
        return False, None, None, []

    args_given = args[1:]
    options = []

    # find the options
    for arg in list(args_given):
        # parser found - use standard syntax
        if arg.startswith('--'):
            return False, None, None, []

        # option found - populate option list
        if arg.startswith('-'):
            options.extend(args_given.pop(0)[1:])

        # command found if iterator didn't already stop - stop iterating
        else:
            break

    # if -h, -a, or -v found in options, then bail out
    if 'h' in options or 'a' in options or 'v' in options:
        return False, None, None, []

    # all options popped and no command found - for case like 'jc -x'
    if len(args_given) == 0:
        return False, None, None, []

    # create a dictionary of magic_commands to their respective parsers.
    magic_dict = {}
    for entry in all_parser_info():
        magic_dict.update({mc: entry['argument'] for mc in entry.get('magic_commands', [])})

    # find the command and parser
    one_word_command = args_given[0]
    two_word_command = ' '.join(args_given[0:2])

    # try to get a parser for two_word_command, otherwise get one for one_word_command
    found_parser = magic_dict.get(two_word_command, magic_dict.get(one_word_command))

    return (
        bool(found_parser),                 # was a suitable parser found?
        args_given,                         # run_command
        found_parser,                       # the parser selected
        options                             # jc options to preserve
    )


def run_user_command(command):
    """
    Use subprocess to run the user's command. Returns the STDOUT, STDERR,
    and the Exit Code as a tuple.
    """
    proc = subprocess.Popen(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            close_fds=False,            # Allows inheriting file descriptors;
                            universal_newlines=True)    # useful for process substitution
    stdout, stderr = proc.communicate()

    return (
        stdout or '\n',
        stderr,
        proc.returncode
    )


def combined_exit_code(program_exit=0, jc_exit=0):
    exit_code = program_exit + jc_exit
    exit_code = min(exit_code, 255)
    return exit_code


def main():
    # break on ctrl-c keyboard interrupt
    signal.signal(signal.SIGINT, ctrlc)

    # break on pipe error. need try/except for windows compatibility
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except AttributeError:
        pass

    # enable colors for Windows cmd.exe terminal
    if sys.platform.startswith('win32'):
        os.system('')

    # parse magic syntax first: e.g. jc -p ls -al
    magic_options = []
    valid_command, run_command, magic_found_parser, magic_options = magic_parser(sys.argv)

    # set colors
    jc_colors = os.getenv('JC_COLORS')

    # set options
    options = []
    options.extend(magic_options)

    # find options if magic_parser did not find a command
    if not valid_command:
        for opt in sys.argv:
            if opt.startswith('-') and not opt.startswith('--'):
                options.extend(opt[1:])

    about = 'a' in options
    debug = 'd' in options
    verbose_debug = options.count('d') > 1
    force_color = 'C' in options
    mono = ('m' in options or bool(os.getenv('NO_COLOR'))) and not force_color
    help_me = 'h' in options
    pretty = 'p' in options
    quiet = 'q' in options
    ignore_exceptions = options.count('q') > 1
    raw = 'r' in options
    unbuffer = 'u' in options
    version_info = 'v' in options

    if verbose_debug:
        tracebackplus.enable(context=11)

    if not PYGMENTS_INSTALLED:
        mono = True

    if about:
        print(json_out(about_jc(),
              pretty=pretty,
              env_colors=jc_colors,
              mono=mono,
              piped_out=piped_output(force_color)))
        sys.exit(0)

    if help_me:
        print(help_doc(sys.argv))
        sys.exit(0)

    if version_info:
        print(versiontext())
        sys.exit(0)

    # if magic syntax used, try to run the command and error if it's not found, etc.
    magic_stdout, magic_stderr, magic_exit_code = None, None, 0
    if run_command:
        try:
            run_command_str = shlex.join(run_command)      # python 3.8+
        except AttributeError:
            run_command_str = ' '.join(run_command)        # older python versions

    if valid_command:
        try:
            magic_stdout, magic_stderr, magic_exit_code = run_user_command(run_command)
            if magic_stderr:
                print(magic_stderr[:-1], file=sys.stderr)

        except OSError as e:
            if debug:
                raise

            error_msg = os.strerror(e.errno)
            utils.error_message([
                f'"{run_command_str}" command could not be run: {error_msg}.'
            ])
            sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

        except Exception:
            if debug:
                raise

            utils.error_message([
                f'"{run_command_str}" command could not be run. For details use the -d or -dd option.'
            ])
            sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

    elif run_command is not None:
        utils.error_message([f'"{run_command_str}" cannot be used with Magic syntax. Use "jc -h" for help.'])
        sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

    # find the correct parser
    if magic_found_parser:
        parser = _get_parser(magic_found_parser)
        parser_name = parser_shortname(magic_found_parser)

    else:
        found = False
        for arg in sys.argv:
            parser_name = parser_shortname(arg)

            if parser_name in parsers:
                parser = _get_parser(arg)
                found = True
                break

        if not found:
            utils.error_message(['Missing or incorrect arguments. Use "jc -h" for help.'])
            sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

    # check for input errors (pipe vs magic)
    if not sys.stdin.isatty() and magic_stdout:
        utils.error_message(['Piped data and Magic syntax used simultaneously. Use "jc -h" for help.'])
        sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

    elif sys.stdin.isatty() and magic_stdout is None:
        utils.error_message(['Missing piped data. Use "jc -h" for help.'])
        sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

    # parse and print to stdout
    try:
        # differentiate between regular and streaming parsers

        # streaming
        if _parser_is_streaming(parser):
            result = parser.parse(sys.stdin,
                                  raw=raw,
                                  quiet=quiet,
                                  ignore_exceptions=ignore_exceptions)
            for line in result:
                print(json_out(line,
                               pretty=pretty,
                               env_colors=jc_colors,
                               mono=mono,
                               piped_out=piped_output(force_color)),
                      flush=unbuffer)

            sys.exit(combined_exit_code(magic_exit_code, 0))

        # regular
        else:
            data = magic_stdout or sys.stdin.read()
            result = parser.parse(data,
                                  raw=raw,
                                  quiet=quiet)
            print(json_out(result,
                           pretty=pretty,
                           env_colors=jc_colors,
                           mono=mono,
                           piped_out=piped_output(force_color)),
                  flush=unbuffer)

        sys.exit(combined_exit_code(magic_exit_code, 0))

    except (ParseError, LibraryNotInstalled) as e:
        if debug:
            raise

        utils.error_message([
            f'Parser issue with {parser_name}:', f'{e.__class__.__name__}: {e}',
            'If this is the correct parser, try setting the locale to C (LANG=C).',
            f'For details use the -d or -dd option. Use "jc -h --{parser_name}" for help.'
        ])
        sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

    except json.JSONDecodeError:
        if debug:
            raise

        utils.error_message(['There was an issue generating the JSON output.',
                             'For details use the -d or -dd option.'])
        sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))

    except Exception:
        if debug:
            raise

        streaming_msg = ''
        if _parser_is_streaming(parser):
            streaming_msg = 'Use the -qq option to ignore streaming parser errors.'

        utils.error_message([
            f'{parser_name} parser could not parse the input data.',
            f'{streaming_msg}',
            'If this is the correct parser, try setting the locale to C (LANG=C).',
            f'For details use the -d or -dd option. Use "jc -h --{parser_name}" for help.'
        ])
        sys.exit(combined_exit_code(magic_exit_code, JC_ERROR_EXIT))


if __name__ == '__main__':
    main()
