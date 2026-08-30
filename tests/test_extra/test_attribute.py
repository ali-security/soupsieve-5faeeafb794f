"""Test attribute selectors."""
import threading
import time
import soupsieve as sv
from .. import util

# A selector that parses normally takes well under a millisecond, so a parse that is
# still running after this long is catastrophic backtracking, not slow hardware.
PARSE_TIMEOUT = 2.0
# Payload of an unterminated quoted value: the parser must reject it outright instead
# of backtracking through every way of splitting it into chunks.
PAYLOAD = 'x' * 300
# The unquoted value backtracks exponentially rather than polynomially, so a much shorter
# payload already demonstrates the denial of service. It is kept short deliberately: it still
# takes seconds unpatched, but it terminates, so a regression fails the assertions below
# instead of hanging the whole test session.
UNQUOTED_PAYLOAD = 'x' * 18


class TestAttribute(util.TestCase):
    """Test attribute selectors."""

    MARKUP = """
    <div id="div">
    <p id="0">Some text <span id="1"> in a paragraph</span>.</p>
    <a id="2" href="http://google.com">Link</a>
    <span id="3">Direct child</span>
    <pre id="pre">
    <span id="4">Child 1</span>
    <span id="5">Child 2</span>
    <span id="6">Child 3</span>
    </pre>
    </div>
    """

    def test_attribute_not_equal_no_quotes(self):
        """Test attribute with value that does not equal specified value (no quotes)."""

        # No quotes
        self.assert_selector(
            self.MARKUP,
            'body [id!=\\35]',
            ["div", "0", "1", "2", "3", "pre", "4", "6"],
            flags=util.HTML5
        )

    def test_attribute_not_equal_quotes(self):
        """Test attribute with value that does not equal specified value (quotes)."""

        # Quotes
        self.assert_selector(
            self.MARKUP,
            "body [id!='5']",
            ["div", "0", "1", "2", "3", "pre", "4", "6"],
            flags=util.HTML5
        )

    def test_attribute_not_equal_double_quotes(self):
        """Test attribute with value that does not equal specified value (double quotes)."""

        # Double quotes
        self.assert_selector(
            self.MARKUP,
            'body [id!="5"]',
            ["div", "0", "1", "2", "3", "pre", "4", "6"],
            flags=util.HTML5
        )

    def assert_fails_fast(self, callback):
        """Assert the callback fails with a syntax error instead of hanging on the selector."""

        # A worker thread is used instead of `signal.alarm` as alarms are not available on Windows.
        # The worker cannot be interrupted mid-backtrack, though: a regex holds the GIL for its
        # whole run, so `join` only returns once the parse has finished regardless of its timeout.
        # The elapsed time is therefore what proves the parse did not backtrack catastrophically --
        # `is_alive` on its own reports False after an arbitrarily long parse and would pass.
        outcome = []

        def parse():
            """Parse the selector, recording the outcome."""

            try:
                callback()
            except Exception as e:
                outcome.append(e)
            else:
                outcome.append(None)

        thread = threading.Thread(target=parse, daemon=True)
        start = time.perf_counter()
        thread.start()
        thread.join(PARSE_TIMEOUT)
        elapsed = time.perf_counter() - start

        self.assertFalse(
            thread.is_alive(),
            'Selector was still being parsed after {} seconds'.format(PARSE_TIMEOUT)
        )
        self.assertLess(
            elapsed,
            PARSE_TIMEOUT,
            'Selector took {:.2f} seconds to parse, indicating catastrophic backtracking'.format(elapsed)
        )
        self.assertIsInstance(outcome[0], sv.SelectorSyntaxError)

    def test_bad_attribute_unclosed_double_quote(self):
        """Test unclosed, double quoted attribute value fails for syntax error, not timeout error."""

        self.assert_fails_fast(lambda: sv.compile('[a="' + PAYLOAD))

    def test_bad_attribute_unclosed_single_quote(self):
        """Test unclosed, single quoted attribute value fails for syntax error, not timeout error."""

        self.assert_fails_fast(lambda: sv.compile("[a='" + PAYLOAD))

    def test_bad_attribute_unclosed_quote_closed_bracket(self):
        """Test unclosed quote in a closed attribute fails for syntax error, not timeout error."""

        self.assert_fails_fast(lambda: sv.compile('[a="' + PAYLOAD + ']'))

    def test_bad_attribute_unclosed_unquoted(self):
        """Test unterminated, unquoted attribute value fails for syntax error, not timeout error."""

        self.assert_fails_fast(lambda: sv.compile('[a=' + UNQUOTED_PAYLOAD))

    def test_bad_contains_unclosed_quote(self):
        """Test unclosed, quoted `:-soup-contains` value fails for syntax error, not timeout error."""

        self.assert_fails_fast(lambda: sv.compile(':-soup-contains("' + PAYLOAD))

    def test_bad_lang_unclosed_quote(self):
        """Test unclosed, quoted `:lang` value fails for syntax error, not timeout error."""

        self.assert_fails_fast(lambda: sv.compile(':lang("' + PAYLOAD))

    def test_bad_attribute_unclosed_quote_select(self):
        """Test unclosed, quoted attribute value fails for syntax error when selecting, not timeout error."""

        soup = self.soup('<div id="1"></div>', 'html.parser')
        self.assert_fails_fast(lambda: sv.select('[a="' + PAYLOAD, soup))
