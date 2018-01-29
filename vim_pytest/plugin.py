from multiprocessing import Process, Pipe
import os
import signal
import threading

import neovim
import pytest

from .pytest_plugin import pytest_process
from .signs import Signs



WIN_NAME = 'Results.pytest'

class TestSession:

    def __init__(self, vim_plugin, buffer, lineno):
        self.vp = vim_plugin
        self.buffer = buffer
        self.lineno = lineno
        self.num_collected = 0
        self.num_started = 0
        self.stdout = None

    def __call__(self):
        path = self.buffer.name
        self.vp.echo('Running pytest on %s' % path)
        thread = threading.Thread(target=self.loop, args=(path, self.lineno))
        thread.start()

    def loop(self, path, lineno):
        conn, other = Pipe()
        proc = Process(target=pytest_process, args=(other, lineno, [path]))
        self.proc = proc
        proc.start()
        while True:
            try:
                obj = conn.recv()
            except EOFError:
                break
            name, *args = obj
            if name == 'quit':
                break
            try:
                func = getattr(self, 'msg_%s' % name)
            except AttributeError:
                self.vp.echo('Unhandled event: %s' % name)
            else:
                try:
                    func(*args)
                except:
                    self.handle_exception()
            if name == 'error':
                break
        proc.join()
        self.proc = None

    def handle_exception(self):
        import traceback
        self.vp.vim.async_call(
            self.vp.error,
            'Exception in message thread.\n%s' % traceback.format_exc(),
        )

    def msg_protocol(self, item):
        self.num_started += 1
        self.vp.vim.async_call(
            self.vp.echo,
            ('Running test %d/%d' % (self.num_started, self.num_collected))
        )

    def msg_collectionfinish(self, items):
        self.num_collected = len(items)
        for item in items:
            sign = self.vp.signs.add(self.buffer, item['nodeid'], item['lineno'])
            sign.state('collected')

    def msg_stage(self, stage, item):
        self.vp.signs.get(item['nodeid']).state('stage_%s' % stage)

    def msg_logreport(self, nodeid, stage, outcome):
        self.vp.signs.get(nodeid).state('outcome_%s' % outcome)

    def msg_sessionfinish(self, outcomes):
        self.outcomes = outcomes

    def msg_stdout(self, stdout):
        self.stdout = stdout
        self.vp.vim.async_call(self.show_results)

    def msg_error(self, msg):
        self.vp.vim.async_call(
            self.vp.error,
            'Exception in pytest process: %s ' % msg
        )

    def show_results(self):
        lines = self.make_lines()
        if self.bad_outcomes:
            self.vp.split_fill(lines)
        else:
            self.vp.split_delete()
        self.vp.show_summary()

    def make_lines(self):
        return self.stdout.split('\n')[1:-1]

    @property
    def bad_outcomes(self):
        return set(self.outcomes) - {'passed', 'skipped', 'xfailed', 'xpassed'}


class SplitMixin:

    def __init__(self):
        self.max_split_size = self.vim.eval('g:vp_max_split_size')

    def split_buffer(self):
        return self.vim.buffers[self.split_buffer_id()]

    def split_buffer_id(self):
        return self.vim.eval('buffer_number("%s")' % WIN_NAME)

    def split_fill(self, lines):
        if self.split_buffer_id() > -1:
            self.split_update_size()
        else:
            self.split_create()
        self.split_buffer()[:] = lines

    def split_create(self):
        new_size = min(
            self.max_split_size,
            len(self.test_session.make_lines()),
            self.vim.eval('winheight("%") / 2'),
        )
        self.vim.command('botright %d new %s' % (new_size, WIN_NAME))
        self.vim.command('wincmd p')

    def split_update_size(self):
        new_size = min(
            self.max_split_size,
            len(self.test_session.make_lines()),
            self.vim.eval('(winheight("%%") + winheight("%s")) / 2 + 1' % WIN_NAME),
        )
        self.vim.command('exe %d "resize %d"' % (self.split_buffer_id(), new_size))

    def split_delete(self):
        if self.split_buffer_id() > -1:
            self.vim.command('exe "bdelete" buffer_number("%s")' % WIN_NAME)

    def split_toggle(self):
        if self.split_buffer_id() > -1:
            self.split_delete()
        else:
            self.split_fill(self.test_session.make_lines())
            self.show_summary()


@neovim.plugin
class Plugin(SplitMixin):

    def __init__(self, vim):
        self.vim = vim
        self.signs = Signs(vim)
        self.test_session = None
        super().__init__()

    def echo(self, msg):
        escaped = str(msg).replace('"', '\\"')
        self.vim.command('echo "%s"' % escaped)

    def echo_okay(self, msg, *args, **kwargs):
        self.echo_color(msg, hl='pytestWarning', *args, **kwargs)

    def echo_bad(self, msg, *args, **kwargs):
        self.echo_color(msg, hl='pytestError', *args, **kwargs)

    def echo_good(self, msg, *args, **kwargs):
        self.echo_color(msg, hl='pytestSuccess', *args, **kwargs)

    def echo_color(self, msg, hl='Normal', *args, **kwargs):
        self.vim.call('VPEcho', msg, hl, *args, **kwargs)

    def error(self, obj):
        self.vim.err_write('VP: %s\n' % obj)

    @neovim.command('VP', range='', nargs='*', sync=False)
    def run(self, args, range):
        try:
            func = getattr(self, 'cmd_%s' % args[0])
        except AttributeError:
            self.error('Subcommand not found: %s' % args[0])
        else:
            func()

    def cmd_file(self):
        self.run_tests()

    def cmd_function(self):
        self.run_tests(self.vim.current.window.cursor[0])

    def cmd_toggle(self):
        if not self.test_session or not self.test_session.stdout:
            self.error('No test results to show.')
            return
        self.split_toggle()

    def cmd_stop(self):
        try:
            pid = self.test_session.proc.pid
        except AttributeError:
            self.error('Pytest isn\'t running.')
            return
        self.echo('Stopping pytest run (PID %d).' % pid)
        try:
            os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            self.error('Pytest isn\'t running.')
            return
        self.test_session.proc.join()
        self.echo('Stopped pytest.')

    def cmd_nosigns(self):
        self.signs.remove_all()

    def run_tests(self, lineno=None):
        self.signs.remove_all()
        self.test_session = TestSession(self, self.vim.current.buffer, lineno)
        self.test_session()

    def show_summary(self):
        total = self.test_session.num_started
        outcomes = self.test_session.outcomes
        if total:
            if all(o == 'passed' for o in outcomes):
                func = self.echo_good
            elif not self.test_session.bad_outcomes:
                func = self.echo_okay
            else:
                func = self.echo_bad
            text = ', '.join(('%d %s' % (v, k)) for k, v in outcomes.items())
            func('%d tests done: %s' % (total, text))
        else:
            self.echo_okay('No tests found.')
