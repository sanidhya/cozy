import os
import unittest

from cozy.target_syntax import *
from cozy.parse import parse
from cozy.typecheck import typecheck

class TestParser(unittest.TestCase):
    pass

files = [
    "agg",
    "basic",
    "clausedb",
    "func",
    "graph",
    "intset",
    "disjunction",
    "map",
    "nested-map",
    "in"]

for filename in files:
    def setup(filename):

        def f(self):
            with open(os.path.join("specs", filename + ".ds"), "r") as f:
                ast = parse(f.read())
            assert isinstance(ast, Spec)

            errs = typecheck(ast)
            for e in errs:
                print(e)
            assert not errs

        f.__name__ = "test_{}".format(filename.replace("-", "_"))
        setattr(TestParser, f.__name__, f)
    setup(filename)

class TestLen(unittest.TestCase):
    def test_parse_len_old(self):
        sample = """
        In:
            state foo : Bag<Int>
            query fooLen()
                sum [1 | _ <- foo]
        """
        parse(sample)

    def test_parse_len(self):
        sample = """
        In:
            state foo : Bag<Int>
            query fooLen()
                len foo
        """
        parse(sample)


class TestEnhancedModifications(unittest.TestCase):
    def test_parse_method_call_with_expr(self):
        sample = """
        Test:
            state foo : Bag<Int>
            op add2x(i : Int)
                foo.add(i * 2)
            op add3x(i : Int)
                foo.add(i + i + i)
        """
        parse(sample)
