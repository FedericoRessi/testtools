# Copyright (c) 2008 Jonathan M. Lange. See LICENSE for details.

"""Test case related stuff."""

__metaclass__ = type
__all__ = [
    'change_test_id',
    'TestCase',
    'skip',
    'skipIf',
    'skipUnless',
    ]

from copy import deepcopy
try:
    from functools import wraps
except ImportError:
    wraps = None
import sys
import unittest

from testtools import content
from testtools.testresult import ExtendedToOriginalDecorator


class TestSkipped(Exception):
    """Raised within TestCase.run() when a test is skipped."""


try:
    # Try to use the same exceptions python 2.7 does.
    from unittest.case import _ExpectedFailure, _UnexpectedSuccess
except ImportError:
    # Oops, not available, make our own.
    class _UnexpectedSuccess(Exception):
        """An unexpected success was raised.

        Note that this exception is private plumbing in testtools' testcase
        module.
        """

    class _ExpectedFailure(Exception):
        """An expected failure occured.

        Note that this exception is private plumbing in testtools' testcase
        module.
        """

class TestCase(unittest.TestCase):
    """Extensions to the basic TestCase."""

    skipException = TestSkipped

    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        self._cleanups = []
        self._last_unique_id = 0
        self.__setup_called = False
        self.__teardown_callled = False
        self.__details = {}

    def __eq__(self, other):
        eq = getattr(unittest.TestCase, '__eq__', None)
        if eq is not None and not unittest.TestCase.__eq__(self, other):
            return False
        return self.__dict__ == other.__dict__

    def addDetail(self, name, content_object):
        """Add a detail to be reported with this test's outcome.

        For more details see pydoc testtools.TestResult.

        :param name: The name to give this detail.
        :param content_object: The content object for this detail. See
            testtools.content for more detail.
        """
        self.__details[name] = content_object

    def getDetails(self):
        """Get the details dict that will be reported with this test's outcome.

        For more details see pydoc testtools.TestResult.
        """
        return self.__details

    def shortDescription(self):
        return self.id()

    def skip(self, reason):
        """Cause this test to be skipped.

        This raises self.skipException(reason). skipException is raised
        to permit a skip to be triggered at any point (during setUp or the
        testMethod itself). The run() method catches skipException and
        translates that into a call to the result objects addSkip method.

        :param reason: The reason why the test is being skipped. This must
            support being cast into a unicode string for reporting.
        """
        raise self.skipException(reason)

    def _formatTypes(self, classOrIterable):
        """Format a class or a bunch of classes for display in an error."""
        className = getattr(classOrIterable, '__name__', None)
        if className is None:
            className = ', '.join(klass.__name__ for klass in classOrIterable)
        return className

    def _runCleanups(self, result):
        """Run the cleanups that have been added with addCleanup.

        See the docstring for addCleanup for more information.

        Returns True if all cleanups ran without error, False otherwise.
        """
        ok = True
        while self._cleanups:
            function, arguments, keywordArguments = self._cleanups.pop()
            try:
                function(*arguments, **keywordArguments)
            except KeyboardInterrupt:
                raise
            except:
                self._report_error(result)
                ok = False
        return ok

    def addCleanup(self, function, *arguments, **keywordArguments):
        """Add a cleanup function to be called before tearDown.

        Functions added with addCleanup will be called in reverse order of
        adding after the test method and before tearDown.

        If a function added with addCleanup raises an exception, the error
        will be recorded as a test error, and the next cleanup will then be
        run.

        Cleanup functions are always called before a test finishes running,
        even if setUp is aborted by an exception.
        """
        self._cleanups.append((function, arguments, keywordArguments))

    def _add_reason(self, reason):
        self.addDetail('reason', content.Content(
            content.ContentType('text', 'plain'),
            lambda:[reason.encode('utf8')]))

    def assertIn(self, needle, haystack):
        """Assert that needle is in haystack."""
        self.assertTrue(
            needle in haystack, '%r not in %r' % (needle, haystack))

    def assertIs(self, expected, observed):
        """Assert that `expected` is `observed`."""
        self.assertTrue(
            expected is observed, '%r is not %r' % (expected, observed))

    def assertIsNot(self, expected, observed):
        """Assert that `expected` is not `observed`."""
        self.assertTrue(
            expected is not observed, '%r is %r' % (expected, observed))

    def assertNotIn(self, needle, haystack):
        """Assert that needle is not in haystack."""
        self.assertTrue(
            needle not in haystack, '%r in %r' % (needle, haystack))

    def assertIsInstance(self, obj, klass):
        self.assertTrue(
            isinstance(obj, klass),
            '%r is not an instance of %s' % (obj, self._formatTypes(klass)))

    def assertRaises(self, excClass, callableObj, *args, **kwargs):
        """Fail unless an exception of class excClass is thrown
           by callableObj when invoked with arguments args and keyword
           arguments kwargs. If a different type of exception is
           thrown, it will not be caught, and the test case will be
           deemed to have suffered an error, exactly as for an
           unexpected exception.
        """
        try:
            ret = callableObj(*args, **kwargs)
        except excClass, excObject:
            return excObject
        else:
            excName = self._formatTypes(excClass)
            self.fail("%s not raised, %r returned instead." % (excName, ret))
    failUnlessRaises = assertRaises

    def assertThat(self, matchee, matcher):
        """Assert that matchee is matched by matcher.

        :param matchee: An object to match with matcher.
        :param matcher: An object meeting the testtools.Matcher protocol.
        :raises self.failureException: When matcher does not match thing.
        """
        if matcher.matches(matchee):
            return
        self.fail('Match failed. Matchee: "%s"\nMatcher: %s\nDifference: %s\n'
            % (matchee, matcher, matcher.describe_difference(matchee)))

    def expectFailure(self, reason, predicate, *args, **kwargs):
        """Check that a test fails in a particular way.

        If the test fails in the expected way, a KnownFailure is caused. If it
        succeeds an UnexpectedSuccess is caused.

        The expected use of expectFailure is as a barrier at the point in a
        test where the test would fail. For example:
        >>> def test_foo(self):
        >>>    self.expectFailure("1 should be 0", self.assertNotEqual, 1, 0)
        >>>    self.assertEqual(1, 0)

        If in the future 1 were to equal 0, the expectFailure call can simply
        be removed. This separation preserves the original intent of the test
        while it is in the expectFailure mode.
        """
        self._add_reason(reason)
        try:
            predicate(*args, **kwargs)
        except self.failureException:
            exc_info = sys.exc_info()
            self.addDetail('traceback',
                content.TracebackContent(exc_info, self))
            raise _ExpectedFailure(exc_info)
        else:
            raise _UnexpectedSuccess(reason)

    def getUniqueInteger(self):
        self._last_unique_id += 1
        return self._last_unique_id

    def getUniqueString(self):
        return '%s-%d' % (self.id(), self.getUniqueInteger())

    def _report_error(self, result):
        self._report_traceback()
        result.addError(self, details=self.getDetails())

    def _report_failure(self, result):
        self._report_traceback()
        result.addFailure(self, details=self.getDetails())

    def _report_skip(self, result, reason):
        self._add_reason(reason)
        result.addSkip(self, details=self.getDetails())

    def _report_traceback(self):
        self.addDetail('traceback',
            content.TracebackContent(sys.exc_info(), self))

    def run(self, result=None):
        if result is None:
            result = self.defaultTestResult()
        result = ExtendedToOriginalDecorator(result)
        result.startTest(self)
        absent_attr = object()
        # Python 2.5
        method_name = getattr(self, '_testMethodName', absent_attr)
        if method_name is absent_attr:
            # Python 2.4
            method_name = getattr(self, '_TestCase__testMethodName')
        testMethod = getattr(self, method_name)
        try:
            try:
                self.setUp()
                if not self.__setup_called:
                    raise ValueError("setup was not called")
            except KeyboardInterrupt:
                raise
            except self.skipException, e:
                self._report_skip(result, e.args[0])
                self._runCleanups(result)
                return
            except _ExpectedFailure:
                result.addExpectedFailure(self, details=self.getDetails())
                self._runCleanups(result)
                return
            except _UnexpectedSuccess:
                result.addUnexpectedSuccess(self, details=self.getDetails())
                self._runCleanups(result)
                return
            except:
                self._report_error(result)
                self._runCleanups(result)
                return

            ok = False
            try:
                testMethod()
                ok = True
            except self.skipException, e:
                self._report_skip(result, e.args[0])
            except _ExpectedFailure:
                result.addExpectedFailure(self, details=self.getDetails())
            except _UnexpectedSuccess:
                result.addUnexpectedSuccess(self, details=self.getDetails())
            except self.failureException:
                self._report_failure(result)
            except KeyboardInterrupt:
                raise
            except:
                self._report_error(result)

            cleanupsOk = self._runCleanups(result)
            try:
                self.tearDown()
                if not self.__teardown_callled:
                    raise ValueError("teardown was not called")
            except _ExpectedFailure:
                result.addExpectedFailure(self, details=self.getDetails())
                ok = False
            except _UnexpectedSuccess:
                result.addUnexpectedSuccess(self, details=self.getDetails())
                ok = False
            except KeyboardInterrupt:
                raise
            except:
                self._report_error(result)
                ok = False
            if ok and cleanupsOk:
                result.addSuccess(self, details=self.getDetails())
        finally:
            result.stopTest(self)
        return result

    def setUp(self):
        unittest.TestCase.setUp(self)
        self.__setup_called = True

    def tearDown(self):
        unittest.TestCase.tearDown(self)
        self.__teardown_callled = True


def clone_test_with_new_id(test, new_id):
    """Copy a TestCase, and give the copied test a new id."""
    newTest = deepcopy(test)
    newTest.id = lambda: new_id
    return newTest

def skip(reason):
    """A decorator to skip unit tests.

    This is just syntactic sugar so users don't have to change any of their
    unit tests in order to migrate to python 2.7, which provides the
    @unittest.skip decorator.
    """
    def decorator(test_item):
        if wraps is not None:
            @wraps(test_item)
            def skip_wrapper(*args, **kwargs):
                raise TestCase.skipException(reason)
        else:
            def skip_wrapper(test_item):
                test_item.skip(reason)
        return skip_wrapper
    return decorator


def skipIf(condition, reason):
    """Skip a test if the condition is true."""
    if condition:
        return skip(reason)
    def _id(obj):
        return obj
    return _id


def skipUnless(condition, reason):
    """Skip a test unless the condition is true."""
    if not condition:
        return skip(reason)
    def _id(obj):
        return obj
    return _id

