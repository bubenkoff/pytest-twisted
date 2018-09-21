import sys
import textwrap

import pytest


def assert_outcomes(run_result, outcomes):
    formatted_output = format_run_result_output_for_assert(run_result)

    try:
        result_outcomes = run_result.parseoutcomes()
    except ValueError:
        assert False, formatted_output

    for name, value in outcomes.items():
        assert result_outcomes.get(name) == value, formatted_output


def format_run_result_output_for_assert(run_result):
    tpl = """
    ---- stdout
    {}
    ---- stderr
    {}
    ----
    """
    return textwrap.dedent(tpl).format(
        run_result.stdout.str(), run_result.stderr.str()
    )


def skip_if_reactor_not(expected_reactor):
    actual_reactor = pytest.config.getoption("reactor", "default")
    return pytest.mark.skipif(
        actual_reactor != expected_reactor,
        reason="reactor is {} not {}".format(actual_reactor, expected_reactor),
    )


def skip_if_no_async_await():
    return pytest.mark.skipif(
        sys.version_info < (3, 5),
        reason="async/await syntax not support on Python <3.5",
    )


@pytest.fixture
def cmd_opts(request):
    reactor = request.config.getoption("reactor", "default")
    return ("--reactor={}".format(reactor),)


def test_fail_later(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer

    def test_fail():
        def doit():
            try:
                1 / 0
            except:
                d.errback()

        d = defer.Deferred()
        reactor.callLater(0.01, doit)
        return d
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", *cmd_opts)
    assert_outcomes(rr, {"failed": 1})


def test_succeed_later(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer

    def test_succeed():
        d = defer.Deferred()
        reactor.callLater(0.01, d.callback, 1)
        return d
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", *cmd_opts)
    assert_outcomes(rr, {"passed": 1})


def test_non_deferred(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer

    def test_succeed():
        return 42
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", *cmd_opts)
    assert_outcomes(rr, {"passed": 1})


def test_exception(testdir, cmd_opts):
    test_file = """
    def test_more_fail():
        raise RuntimeError("foo")
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", *cmd_opts)
    assert_outcomes(rr, {"failed": 1})


def test_inlineCallbacks(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer
    import pytest
    import pytest_twisted

    @pytest.fixture(scope="module", params=["fs", "imap", "web"])
    def foo(request):
        return request.param

    @pytest_twisted.inlineCallbacks
    def test_succeed(foo):
        yield defer.succeed(foo)
        if foo == "web":
            raise RuntimeError("baz")
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 2, "failed": 1})

def test_inlineCallbacks_exception(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer
    import pytest
    import pytest_twisted

    @pytest_twisted.inlineCallbacks
    def test_succeed():
        yield defer.succeed(42)
        raise Exception('blue')
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"failed": 1})



@skip_if_no_async_await()
def test_async_callbacks(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer
    import pytest
    import pytest_twisted

    @pytest.fixture(scope="module", params=["fs", "imap", "web"])
    def foo(request):
        return request.param

    @pytest_twisted.async_callbacks
    async def test_succeed(foo):
        await defer.succeed(foo)
        if foo == "web":
            raise RuntimeError("baz")
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 2, "failed": 1})


def test_twisted_greenlet(testdir, cmd_opts):
    test_file = """
    import pytest, greenlet

    MAIN = None

    @pytest.fixture(scope="session", autouse=True)
    def set_MAIN(request, twisted_greenlet):
        global MAIN
        MAIN = twisted_greenlet

    def test_MAIN():
        assert MAIN is not None
        assert MAIN is greenlet.getcurrent()
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 1})


def test_blockon_in_fixture(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer
    import pytest
    import pytest_twisted

    @pytest.fixture(scope="module", params=["fs", "imap", "web"])
    def foo(request):
        d1, d2 = defer.Deferred(), defer.Deferred()
        reactor.callLater(0.01, d1.callback, 1)
        reactor.callLater(0.02, d2.callback, request.param)
        pytest_twisted.blockon(d1)
        return d2

    @pytest_twisted.inlineCallbacks
    def test_succeed(foo):
        x = yield foo
        if x == "web":
            raise RuntimeError("baz")
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 2, "failed": 1})


@skip_if_no_async_await()
def test_blockon_in_fixture_async(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer
    import pytest
    import pytest_twisted

    @pytest.fixture(scope="module", params=["fs", "imap", "web"])
    def foo(request):
        d1, d2 = defer.Deferred(), defer.Deferred()
        reactor.callLater(0.01, d1.callback, 1)
        reactor.callLater(0.02, d2.callback, request.param)
        pytest_twisted.blockon(d1)
        return d2

    @pytest_twisted.async_callbacks
    async def test_succeed(foo):
        x = await foo
        if x == "web":
            raise RuntimeError("baz")
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 2, "failed": 1})


@skip_if_no_async_await()
def test_async_fixture(testdir, cmd_opts):
    test_file = """
    from twisted.internet import reactor, defer
    import pytest
    import pytest_twisted

    @pytest.fixture(scope="function", params=["fs", "imap", "web"])
    async def foo(request):
        d1, d2 = defer.Deferred(), defer.Deferred()
        reactor.callLater(0.01, d1.callback, 1)
        reactor.callLater(0.02, d2.callback, request.param)
        await d1
        return d2,

    @pytest_twisted.inlineCallbacks
    def test_succeed(foo):
        x = yield foo[0]
        print('+++', x)
        if x == "web":
            raise RuntimeError("baz")
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 2, "failed": 1})


@skip_if_reactor_not("default")
def test_blockon_in_hook(testdir, cmd_opts):
    conftest_file = """
    import pytest_twisted as pt
    from twisted.internet import reactor, defer

    def pytest_configure(config):
        pt.init_default_reactor()
        d1, d2 = defer.Deferred(), defer.Deferred()
        reactor.callLater(0.01, d1.callback, 1)
        reactor.callLater(0.02, d2.callback, 1)
        pt.blockon(d1)
        pt.blockon(d2)
    """
    testdir.makeconftest(conftest_file)
    test_file = """
    from twisted.internet import reactor, defer

    def test_succeed():
        d = defer.Deferred()
        reactor.callLater(0.01, d.callback, 1)
        return d
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 1})


@skip_if_reactor_not("default")
def test_wrong_reactor(testdir, cmd_opts):
    conftest_file = """
    def pytest_addhooks():
        import twisted.internet.reactor
        twisted.internet.reactor = None
    """
    testdir.makeconftest(conftest_file)
    test_file = """
    def test_succeed():
        pass
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert "WrongReactorAlreadyInstalledError" in rr.stderr.str()


@skip_if_reactor_not("qt5reactor")
def test_blockon_in_hook_with_qt5reactor(testdir, cmd_opts):
    conftest_file = """
    import pytest_twisted as pt
    import pytestqt
    from twisted.internet import defer

    def pytest_configure(config):
        pt.init_qt5_reactor()
        d = defer.Deferred()

        from twisted.internet import reactor

        reactor.callLater(0.01, d.callback, 1)
        pt.blockon(d)
    """
    testdir.makeconftest(conftest_file)
    test_file = """
    from twisted.internet import reactor, defer

    def test_succeed():
        d = defer.Deferred()
        reactor.callLater(0.01, d.callback, 1)
        return d
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert_outcomes(rr, {"passed": 1})


@skip_if_reactor_not("qt5reactor")
def test_wrong_reactor_with_qt5reactor(testdir, cmd_opts):
    conftest_file = """
    def pytest_addhooks():
        import twisted.internet.default
        twisted.internet.default.install()
    """
    testdir.makeconftest(conftest_file)
    test_file = """
    def test_succeed():
        pass
    """
    testdir.makepyfile(test_file)
    rr = testdir.run(sys.executable, "-m", "pytest", "-v", *cmd_opts)
    assert "WrongReactorAlreadyInstalledError" in rr.stderr.str()


@skip_if_reactor_not("default")
def test_pytest_from_reactor_thread(testdir):
    test_file = """
    import pytest
    import pytest_twisted
    from twisted.internet import reactor, defer

    @pytest.fixture
    def fix():
        d = defer.Deferred()
        reactor.callLater(0.01, d.callback, 42)
        return pytest_twisted.blockon(d)

    def test_simple(fix):
        assert fix == 42

    @pytest_twisted.inlineCallbacks
    def test_fail():
        d = defer.Deferred()
        reactor.callLater(0.01, d.callback, 1)
        yield d
        assert False
    """
    testdir.makepyfile(test_file)
    runner_file = """
    import pytest

    from twisted.internet import reactor
    from twisted.internet.defer import inlineCallbacks
    from twisted.internet.threads import deferToThread

    codes = []

    @inlineCallbacks
    def main():
        try:
            codes.append((yield deferToThread(pytest.main, ['-k simple'])))
            codes.append((yield deferToThread(pytest.main, ['-k fail'])))
        finally:
            reactor.stop()

    if __name__ == '__main__':
        reactor.callLater(0, main)
        reactor.run()
        codes == [0, 1] or exit(1)
    """
    testdir.makepyfile(runner=runner_file)
    # check test file is ok in standalone mode:
    rr = testdir.run(sys.executable, "-m", "pytest", "-v")
    assert_outcomes(rr, {"passed": 1, "failed": 1})
    # test embedded mode:
    assert testdir.run(sys.executable, "runner.py").ret == 0
