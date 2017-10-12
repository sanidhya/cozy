"""
Various utilities for working with syntax trees.

    pprint(ast) -> str            prettyprint a syntax tree

"""

import collections
from contextlib import contextmanager
import sys
import itertools

from cozy import common
from cozy import syntax
from cozy import target_syntax
from cozy import pools

def fresh_var(type, hint="var"):
    return syntax.EVar(common.fresh_name(hint)).with_type(type)

def mk_lambda(t, l):
    v = fresh_var(t)
    return target_syntax.ELambda(v, l(v))

def compose(f1 : target_syntax.ELambda, f2 : target_syntax.ELambda) -> target_syntax.ELambda:
    return mk_lambda(f2.arg.type, lambda v: f1.apply_to(f2.apply_to(v)))

_SCALAR_TYPES = set((
    syntax.TInt,
    syntax.TLong,
    syntax.TBool,
    syntax.TString,
    syntax.TNative,
    syntax.THandle,
    syntax.TEnum))
def is_scalar(t : syntax.Type):
    if type(t) in _SCALAR_TYPES:
        return True
    if isinstance(t, syntax.TTuple):
        return all(is_scalar(tt) for tt in t.ts)
    if isinstance(t, syntax.TRecord):
        return all(is_scalar(tt) for (f, tt) in t.fields)
    return False

class BottomUpExplorer(common.Visitor):
    def visit_ADT(self, x):
        new_children = tuple(self.visit(child) for child in x.children())
        return self.join(x, new_children)
    def visit_list(self, l):
        return self.join(l, tuple(self.visit(x) for x in l))
    def visit_tuple(self, l):
        return self.join(l, tuple(self.visit(x) for x in l))
    def visit_dict(self, d):
        return self.join(d, tuple((self.visit(k), self.visit(v)) for (k,v) in d.items()))
    def visit_object(self, o):
        return self.join(o, ())
    def join(self, x, new_children):
        pass

class BottomUpRewriter(BottomUpExplorer):
    def join(self, x, new_children):
        if isinstance(x, common.ADT):
            out = type(x)(*new_children)
        elif type(x) in [list, tuple, dict]:
            out = type(x)(new_children)
        else:
            out = x
        if isinstance(x, syntax.Exp) and hasattr(x, "type"):
            out.type = x.type
        if isinstance(x, syntax.THandle) and hasattr(x, "value_type"):
            out.value_type = x.value_type
        return out

def strip_EStateVar(e : syntax.Exp):
    class V(BottomUpRewriter):
        def visit_EStateVar(self, e):
            return self.visit(e.e)
    return V().visit(e)

def deep_copy(ast):
    return BottomUpRewriter().visit(ast)

def shallow_copy(ast):
    return BottomUpRewriter().join(ast, ast.children())

def all_types(ast):
    class TypeCollector(BottomUpExplorer):
        def visit_Type(self, t):
            yield from super().visit_ADT(t)
            yield t
        def visit_object(self, o):
            return ()
        def join(self, t, children):
            return itertools.chain(*children)
    return common.unique(TypeCollector().visit(ast))

class PrettyPrinter(common.Visitor):
    def visit_Spec(self, spec):
        s = spec.name + ":\n"
        for name, t in spec.types:
            s += "  type {} = {}\n".format(name, self.visit(t))
        for name, t in spec.statevars:
            s += "  state {} : {}\n".format(name, self.visit(t))
        for e in spec.assumptions:
            s += "  assume {};\n".format(self.visit(e))
        for op in spec.methods:
            s += str(self.visit(op))
        return s

    def visit_TEnum(self, enum):
        return "enum {{ {} }}".format(", ".join(enum.cases))

    def visit_TNamed(self, named):
        return named.id

    def visit_TNative(self, t):
        return t.name

    def visit_TApp(self, app):
        return "{}<{}>".format(app.t, self.visit(app.args))

    def visit_TBag(self, s):
        return "Bag<{}>".format(self.visit(s.t))

    def visit_TSet(self, s):
        return "Set<{}>".format(self.visit(s.t))

    def visit_TMap(self, m):
        return "Map<{}, {}>".format(self.visit(m.k), self.visit(m.v))

    def visit_THeap(self, h):
        return "Heap<{}>".format(self.visit(h.t))

    def visit_TIntrusiveLinkedList(self, h):
        return "IntrusiveLinkedList<{}>".format(self.visit(h.t))

    def visit_TNativeSet(self, h):
        return "NativeSet<{}>".format(self.visit(h.t))

    def visit_TNativeList(self, h):
        return "NativeList<{}>".format(self.visit(h.t))

    def visit_THashMap(self, h):
        return "HashMap<{}, {}>".format(self.visit(h.k), self.visit(h.v))

    def visit_TInt(self, t):
        return "Int"

    def visit_TLong(self, t):
        return "Long"

    def visit_TBool(self, t):
        return "Bool"

    def visit_TString(self, t):
        return "String"

    def visit_TTuple(self, t):
        return "({})".format(", ".join(self.visit(tt) for tt in t.ts))

    def visit_TRecord(self, r):
        return "{{ {} }}".format(", ".join("{} : {}".format(f, self.visit(t)) for f, t in r.fields))

    def visit_THandle(self, t):
        return t.statevar

    def visit_ConcreteType(self, t):
        return t.prettyprint()

    def visit_Query(self, q):
        s = "  query {}({}):\n".format(q.name, ", ".join("{} : {}".format(name, self.visit(t)) for name, t in q.args))
        for e in q.assumptions:
            s += "    assume {};\n".format(self.visit(e))
        s += "    {}\n".format(self.visit(q.ret))
        return s

    def visit_Op(self, q):
        s = "  op {}({}):\n".format(q.name, ", ".join("{} : {}".format(name, self.visit(t)) for name, t in q.args))
        for e in q.assumptions:
            s += "    assume {};\n".format(self.visit(e))
        s += "{}\n".format(self.visit(q.body, "    "))
        return s

    def visit_EVar(self, e):
        return e.id

    def visit_EBool(self, e):
        return "true" if e.val else "false"

    def visit_EStr(self, e):
        return repr(e.val)

    def visit_ENum(self, e):
        return str(e.val)

    def visit_EEnumEntry(self, e):
        return e.name

    def visit_ENull(self, e):
        return "NULL"

    def visit_ELambda(self, e):
        return "(\\{} -> {})".format(e.arg.id, self.visit(e.body))

    def visit_EApp(self, e):
        return "{}({})".format(self.visit(e.f), self.visit(e.arg))

    def visit_EMapGet(self, e):
        return "{}[{}]".format(self.visit(e.map), self.visit(e.key))

    def visit_EMakeMap(self, e):
        return "MkMap({}, {}, {})".format(self.visit(e.e), self.visit(e.key), self.visit(e.value))

    def visit_EMap(self, e):
        return "Map {{{}}} ({})".format(self.visit(e.f), self.visit(e.e))

    def visit_EFilter(self, e):
        return "Filter {{{}}} ({})".format(self.visit(e.p), self.visit(e.e))

    def visit_EFlatMap(self, e):
        return "FlatMap({}, {})".format(self.visit(e.e), self.visit(e.f))

    def visit_EBinOp(self, e):
        return "({} {} {})".format(self.visit(e.e1), e.op, self.visit(e.e2))

    def visit_ECond(self, e):
        return "({} ? {} : {})".format(self.visit(e.cond), self.visit(e.then_branch), self.visit(e.else_branch))

    def visit_EUnaryOp(self, e):
        return "({} {})".format(e.op, self.visit(e.e))

    def visit_EArgMin(self, e):
        if e.f.body == e.f.arg:
            return "min {}".format(self.visit(e.e))
        else:
            return "argmin {{{}}} {}".format(self.visit(e.f), self.visit(e.e))

    def visit_EArgMax(self, e):
        if e.f.body == e.f.arg:
            return "max {}".format(self.visit(e.e))
        else:
            return "argmax {{{}}} {}".format(self.visit(e.f), self.visit(e.e))

    def visit_EGetField(self, e):
        return "({}).{}".format(self.visit(e.e), e.f)

    def visit_EMakeRecord(self, e):
        return "{{ {} }}".format(", ".join("{} : {}".format(name, self.visit(val)) for name, val in e.fields))

    def visit_EEmptyList(self, e):
        return "[]"

    def visit_ESingleton(self, e):
        return "[{}]".format(self.visit(e.e))

    def visit_EListComprehension(self, e):
        return "[{} | {}]".format(self.visit(e.e), ", ".join(self.visit(clause) for clause in e.clauses))

    def visit_EAlloc(self, e):
        return "new {}({})".format(self.visit(e.t), ", ".join(self.visit(arg) for arg in e.args))

    def visit_ECall(self, e):
        return "{}({})".format(e.func, ", ".join(self.visit(arg) for arg in e.args))

    def visit_ETuple(self, e):
        return "({})".format(", ".join(self.visit(e) for e in e.es))

    def visit_ETupleGet(self, e):
        return "({}).{}".format(self.visit(e.e), e.n)

    def visit_ELet(self, e):
        return "let {} = {} in {}".format(e.f.arg.id, self.visit(e.e), self.visit(e.f.body))

    def visit_CPull(self, c):
        return "{} <- {}".format(c.id, self.visit(c.e))

    def visit_CCond(self, c):
        return self.visit(c.e)

    def visit_ADT(self, e, *args, **kwargs):
        return "{}({})".format(type(e).__name__, ", ".join(self.visit(x) for x in e.children()))

    def visit_object(self, e, *args, **kwargs):
        print("Warning: implement prettyprinting for {}".format(type(e).__name__), file=sys.stderr)
        return repr(e)

    def visit_SNoOp(self, s, indent=""):
        return "{}pass".format(indent)

    def visit_SCall(self, s, indent=""):
        return "{}{}.{}({})".format(indent, self.visit(s.target), s.func, ", ".join(self.visit(arg) for arg in s.args))

    def visit_SAssign(self, s, indent=""):
        return "{}{} = {}".format(indent, self.visit(s.lhs), self.visit(s.rhs))

    def visit_SDecl(self, s, indent=""):
        return "{}var {} : {} = {}".format(indent, s.id, self.visit(s.val.type), self.visit(s.val))

    def visit_SDel(self, s, indent=""):
        return "{}del {}".format(indent, self.visit(s.e))

    def visit_SSeq(self, s, indent=""):
        return "{}\n{}".format(self.visit(s.s1, indent), self.visit(s.s2, indent))

    def visit_SMapUpdate(self, s, indent=""):
        return "{indent}with {} as {}:\n{}".format(
            self.visit(target_syntax.EMapGet(s.map, s.key)),
            s.val_var.id,
            self.visit(s.change, indent + "  "),
            indent=indent)

    def visit_SMapPut(self, s, indent=""):
        return "{indent}{} = {}".format(
            self.visit(target_syntax.EMapGet(s.map, s.key)),
            self.visit(s.value),
            indent=indent)

    def visit_SMapDel(self, s, indent=""):
        return "{indent}del {}".format(
            self.visit(target_syntax.EMapGet(s.map, s.key)),
            indent=indent)

    def visit_SForEach(self, s, indent=""):
        return "{}for {} in {}:\n{}".format(indent, s.id.id, self.visit(s.iter), self.visit(s.body, indent + "  "))

    def visit_SIf(self, s, indent=""):
        if isinstance(s.else_branch, syntax.SNoOp):
            return "{indent}if {}:\n{}".format(self.visit(s.cond), self.visit(s.then_branch, indent + "  "), indent=indent)
        return "{indent}if {}:\n{}\n{indent}else:\n{}".format(self.visit(s.cond), self.visit(s.then_branch, indent + "  "), self.visit(s.else_branch, indent + "  "), indent=indent)

_PRETTYPRINTER = PrettyPrinter()
def pprint(ast):
    return _PRETTYPRINTER.visit(ast)

def free_funcs(e : syntax.Exp) -> dict:
    res = collections.OrderedDict()
    for x in all_exps(e):
        if isinstance(x, syntax.ECall):
            t = target_syntax.TFunc(tuple(arg.type for arg in x.args), x.type)
            if x.func in res:
                assert res[x.func] == t
            else:
                res[x.func] = t
    return res

def free_vars(exp, counts=False):
    res = collections.OrderedDict()
    bound = collections.defaultdict(int)

    class Unbind(object):
        def __init__(self, var):
            self.var = var
        def exec(self):
            bound[self.var] -= 1

    stk = [exp]
    while stk:
        x = stk[-1]
        del stk[-1]
        if isinstance(x, Unbind):
            x.exec()
        elif isinstance(x, syntax.EVar):
            if not bound[x]:
                res[x] = res.get(x, 0) + 1
        elif isinstance(x, target_syntax.ELambda):
            bound[x.arg] += 1
            stk.append(Unbind(x.arg))
            stk.append(x.body)
        elif isinstance(x, syntax.EListComprehension):
            raise NotImplementedError()
        elif isinstance(x, syntax.Method):
            args = [syntax.EVar(a).with_type(t) for (a, t) in x.args]
            for a in args:
                bound[a] += 1
            stk.extend(Unbind(a) for a in args)
            if isinstance(x, syntax.Query):
                stk.extend(reversed(x.assumptions))
                stk.append(x.ret)
            else:
                raise NotImplementedError()
        elif isinstance(x, common.ADT):
            stk.extend(reversed(x.children()))
        elif isinstance(x, list) or isinstance(x, tuple):
            stk.extend(reversed(x))
        elif isinstance(x, str) or isinstance(x, int):
            continue
        else:
            raise NotImplementedError(repr(x))

    if not counts:
        res = common.OrderedSet(res.keys())
    return res

def all_exps(e):
    class V(BottomUpExplorer):
        def join(self, x, children):
            for child in children:
                yield from child
            if isinstance(x, syntax.Exp):
                yield x
    return V().visit(e)

class FragmentEnumerator(common.Visitor):
    # This visitor's methods use a weird pattern:
    #     yield (lambda r: ...)(r)
    # This is because lambdas are capture-by-reference in Python! Since r is
    # overwritten at each loop iteration, that's a problem. Defining a fresh
    # function and immediately calling it is a simple way to force
    # capture-by-value for r instead.
    def __init__(self, pre_visit=None, post_visit=None):
        if not pre_visit:
            pre_visit = lambda obj: True
        if not post_visit:
            post_visit = lambda obj: None
        self.pre_visit = pre_visit
        self.post_visit = post_visit
        self.bound = collections.OrderedDict()
        self.assumptions = []

    def EDeepIn(self, x, bag):
        arg = syntax.EVar("_fragarg").with_type(x.type)
        return syntax.EUnaryOp(syntax.UOp.Any,
            target_syntax.EMap(bag, target_syntax.ELambda(arg,
                syntax.EBinOp(arg, "===", x).with_type(syntax.BOOL))).with_type(syntax.BOOL_BAG)).with_type(syntax.BOOL)

    def currently_bound(self):
        return common.OrderedSet(self.bound.keys())

    def current_assumptions(self):
        return self.assumptions

    @contextmanager
    @common.typechecked
    def push_assumptions(self, new_assumptions : [syntax.Exp] = []):
        old_assumptions = self.assumptions
        self.assumptions = self.assumptions + new_assumptions
        yield
        self.assumptions = old_assumptions

    @contextmanager
    @common.typechecked
    def intro_vars(self, vars : [syntax.EVar], source):
        vars = common.OrderedSet(vars)
        old_assumptions = self.assumptions
        self.assumptions = [a for a in self.assumptions if not (free_vars(a) & vars)]
        with common.extend_multi(self.bound, [(v, source) for v in vars]):
            yield
        self.assumptions = old_assumptions

    def visit_assumptions_seq(self, assumptions, i=0):
        if i >= len(assumptions):
            return
        for info in self.visit(assumptions[i]):
            yield (lambda i, a, x, r, bound: (a, x, lambda x: tuple(assumptions[:i]) + (x,) + tuple(assumptions[i:]), bound))(i, *info)
        self.assumptions.append(assumptions[i])
        yield from self.visit_assumptions_seq(assumptions, i+1)

    def recurse_with_assumptions_about_bound_var(self, e : target_syntax.ELambda, assume : [syntax.Exp]):
        if self.pre_visit(e):
            yield (self.current_assumptions(), e, common.identity_func, self.currently_bound())
            with self.intro_vars([e.arg], e):
                with self.push_assumptions(assume):
                    for (a, x, r, bound) in self.visit(e.body):
                        yield (lambda r, x, a, bound: (a, x, lambda x: target_syntax.ELambda(e.arg, r(x)), bound))(r, x, a, bound)
            self.post_visit(e)

    def visit_ELambda(self, obj):
        # raise NotImplementedError(obj)
        return self.recurse_with_assumptions_about_bound_var(obj, [])

    def visit_EStateVar(self, e):
        """
        A very tricky case: the set of bound variables gets cleared for its
        children. Consider

            Filter {\v -> EStateVar(v)} C

        The `v` in the EStateVar is *different* from the `v` bound by the filter
        predicate, since this expression is conceptually equivalent to

            state s = v
            Filter {\v -> s} C
        """
        yield (self.current_assumptions(), e, common.identity_func, self.currently_bound())
        orig_bound = self.bound
        self.bound = collections.OrderedDict()
        t = e.type
        for (a, x, r, bound) in self.visit(e.e):
            yield (lambda r: (a, x, lambda x: target_syntax.EStateVar(r(x)).with_type(t), bound))(r)
        self.bound = orig_bound

    def visit_EFilter(self, e):
        yield (self.current_assumptions(), e, common.identity_func, self.currently_bound())
        t = e.type
        for (a, x, r, bound) in self.visit(e.e):
            yield (lambda r: (a, x, lambda x: target_syntax.EFilter(r(x), e.p).with_type(t), bound))(r)
        for (a, x, r, bound) in self.recurse_with_assumptions_about_bound_var(e.p, [self.EDeepIn(e.p.arg, e.e)] if e.p.arg not in free_vars(e.e) else []):
            yield (lambda r: (a, x, lambda x: target_syntax.EFilter(e.e, r(x)).with_type(t), bound))(r)

    def visit_EMap(self, e):
        yield (self.current_assumptions(), e, common.identity_func, self.currently_bound())
        t = e.type
        for (a, x, r, bound) in self.visit(e.e):
            yield (lambda r: (a, x, lambda x: target_syntax.EMap(r(x), e.f).with_type(t), bound))(r)
        for (a, x, r, bound) in self.recurse_with_assumptions_about_bound_var(e.f, [self.EDeepIn(e.f.arg, e.e)] if e.f.arg not in free_vars(e.e) else []):
            yield (lambda r: (a, x, lambda x: target_syntax.EMap(e.e, r(x)).with_type(t), bound))(r)

    def visit_EFlatMap(self, e):
        yield (self.current_assumptions(), e, common.identity_func, self.currently_bound())
        t = e.type
        for (a, x, r, bound) in self.visit(e.e):
            yield (lambda r: (a, x, lambda x: target_syntax.EFlatMap(r(x), e.f).with_type(t), bound))(r)
        for (a, x, r, bound) in self.recurse_with_assumptions_about_bound_var(e.f, [self.EDeepIn(e.f.arg, e.e)] if e.f.arg not in free_vars(e.e) else []):
            yield (lambda r: (a, x, lambda x: target_syntax.EFlatMap(e.e, r(x)).with_type(t), bound))(r)

    def visit_EMakeMap2(self, e):
        yield (self.current_assumptions(), e, common.identity_func, self.currently_bound())
        t = e.type
        for (a, x, r, bound) in self.visit(e.e):
            yield (lambda r: (a, x, lambda x: target_syntax.EMakeMap2(r(x), e.value).with_type(t), bound))(r)
        for (a, x, r, bound) in self.recurse_with_assumptions_about_bound_var(e.value, [self.EDeepIn(e.value.arg, e.e)] if e.value.arg not in free_vars(e.e) else []):
            yield (lambda r: (a, x, lambda x: target_syntax.EMakeMap2(e.e, r(x)).with_type(t), bound))(r)

    def visit_ECond(self, e):
        yield (self.current_assumptions(), e, common.identity_func, self.currently_bound())
        for info in self.visit(e.cond):
            yield (lambda a, x, r, bound: (a, x, lambda x: syntax.ECond(r(x), e.then_branch, e.else_branch).with_type(e.type), bound))(*info)
        with self.push_assumptions([e.cond]):
            for info in self.visit(e.then_branch):
                yield (lambda a, x, r, bound: (a, x, lambda x: syntax.ECond(e.cond, r(x), e.else_branch).with_type(e.type), bound))(*info)
        with self.push_assumptions([syntax.ENot(e.cond)]):
            for info in self.visit(e.else_branch):
                yield (lambda a, x, r, bound: (a, x, lambda x: syntax.ECond(e.cond, e.then_branch, r(x)).with_type(e.type), bound))(*info)

    def rebuild(self, obj, new_children):
        res = type(obj)(*new_children)
        if isinstance(obj, syntax.Exp) and hasattr(obj, "type"):
            res = res.with_type(obj.type)
        return res

    def visit_Spec(self, s):
        yield (self.current_assumptions(), s, common.identity_func, self.currently_bound())
        with self.intro_vars([syntax.EVar(v).with_type(t) for (v, t) in s.statevars], s):
            with self.push_assumptions():
                for info in self.visit_assumptions_seq(s.assumptions):
                    yield (lambda a, x, r, bound: (a, x, lambda x: syntax.Spec(s.name, s.types, s.extern_funcs, s.statevars, r(x), s.methods, s.header, s.footer), bound))(*info)
                for info in self.visit(s.methods):
                    yield (lambda a, x, r, bound: (a, x, lambda x: syntax.Spec(s.name, s.types, s.extern_funcs, s.statevars, s.assumptions, ms, s.header, s.footer), bound))(*info)

    def visit_Op(self, m):
        yield (self.current_assumptions(), m, common.identity_func, self.currently_bound())
        with self.intro_vars([syntax.EVar(v).with_type(t) for (v, t) in m.args], m):
            with self.push_assumptions():
                for info in self.visit_assumptions_seq(m.assumptions):
                    yield (lambda a, x, r, bound: (a, x, lambda x: syntax.Op(m.name, m.args, r(x), m.body), bound))(*info)
                for info in self.visit(m.body):
                    yield (lambda a, x, r, bound: (a, x, lambda x: syntax.Op(m.name, m.args, m.assumptions, r(x)), bound))(*info)

    def visit_Query(self, q):
        yield (self.current_assumptions(), q, common.identity_func, self.currently_bound())
        with self.intro_vars([syntax.EVar(v).with_type(t) for (v, t) in q.args], q):
            with self.push_assumptions():
                for info in self.visit_assumptions_seq(q.assumptions):
                    yield (lambda a, x, r, bound: (a, x, lambda x: syntax.Query(q.name, q.args, r(x), q.ret), bound))(*info)
                for info in self.visit(q.ret):
                    yield (lambda a, x, r, bound: (a, x, lambda x: syntax.Query(q.name, q.args, q.assumptions, r(x)), bound))(*info)

    def visit_ADT(self, obj):
        yield (self.current_assumptions(), obj, common.identity_func, self.currently_bound())
        children = obj.children()
        for i in range(len(children)):
            for (a, x, r, bound) in self.visit(children[i]):
                yield (a, x, (lambda r, i: lambda x: self.rebuild(obj, (children[:i] + (r(x),) + children[i+1:])))(r, i), bound)

    def visit_list(self, l):
        return self.visit_tuple(tuple(l))

    def visit_tuple(self, t):
        yield (self.current_assumptions(), t, common.identity_func, self.currently_bound())
        for i in range(len(t)):
            for (a, x, r, bound) in self.visit(t[i]):
                yield (a, x, (lambda r, i: lambda x: t[:i] + (r(x),) + t[i+1:])(r, i), bound)

    def visit_object(self, obj):
        yield (self.current_assumptions(), obj, common.identity_func, self.currently_bound())

    def visit(self, obj):
        if self.pre_visit(obj):
            yield from super().visit(obj)
            self.post_visit(obj)
        else:
            return ()

def enumerate_fragments(e : syntax.Exp, pre_visit=None, post_visit=None, include_lambdas=False):
    """
    Yields tuples (a : [Exp], x : Exp, r : Exp->Exp, ctx : {EVar}) such that:
        x is a non-lambda subexpression of e
        a are true assumptions whenever x is evaluated on any input to e (NOTE:
            these assumptions may be conservative, but they are never wrong)
        r(x) == e (in general, r can be used to replace x with a new subexpr)
        ctx is the set of bound vars at x (i.e. in any potential replacement y,
            all free vars in y not in ctx will be free in r(y))

    Fragments are enumerated top-down (i.e. every expression comes before any
    of its subexpressions).
    """
    enumerator = FragmentEnumerator(pre_visit, post_visit)
    for info in enumerator.visit(e):
        (a, x, r, bound) = info
        if isinstance(x, syntax.Exp) and ((not isinstance(x, target_syntax.ELambda)) or include_lambdas):
            yield info

def enumerate_fragments_and_pools(e : syntax.Exp, pre_visit=None, post_visit=None, include_lambdas=False):
    """
    Like enumerate_fragments, but adds "pool" to the tuple depending on whether
    we are beneath an EStateVar.
    """
    sv_depth = 0
    def new_pre_visit(obj):
        nonlocal sv_depth
        if pre_visit is not None and not pre_visit(obj):
            return False
        if isinstance(obj, target_syntax.EStateVar):
            sv_depth += 1
        return True
    def new_post_visit(obj):
        nonlocal sv_depth
        if post_visit is not None:
            post_visit(obj)
        if isinstance(obj, target_syntax.EStateVar):
            sv_depth -= 1
    def pool(e):
        return pools.STATE_POOL if ((sv_depth - 1) if isinstance(e, target_syntax.EStateVar) else sv_depth) else pools.RUNTIME_POOL
    for (a, x, r, bound) in enumerate_fragments(e, new_pre_visit, new_post_visit, include_lambdas=include_lambdas):
        yield (a, x, r, bound, pool(x))

def replace(exp, old_exp, new_exp):
    class Replacer(BottomUpRewriter):
        def visit_ELambda(self, e):
            return target_syntax.ELambda(e.arg, self.visit(e.body))
        def visit(self, e):
            if e == old_exp:
                return new_exp
            return super().visit(e)
    return Replacer().visit(exp)

def subst(exp, replacements):
    """
    Performs capture-avoiding substitution.
    Input:
        exp             - an Exp
        replacements    - {str:Exp} replacement map for variables
    Output:
        exp with each var mapped to its replacement (if any) from replacements
    """

    allfvs = set()
    for val in replacements.values():
        allfvs |= {fv.id for fv in free_vars(val)}

    class Subst(common.Visitor):
        def visit_EVar(self, var):
            return replacements.get(var.id, var)
        def visit_EListComprehension(self, lcmp):
            return self.visit_lcmp(list(lcmp.clauses), 0, lcmp.e)
        def visit_lcmp(self, clauses, i, e):
            if i >= len(clauses):
                return syntax.EListComprehension(self.visit(e), tuple(clauses))
            c = clauses[i]
            if isinstance(c, syntax.CPull):
                if c.id in replacements:
                    raise NotImplementedError()
                if c.id in allfvs:
                    name = common.fresh_name()
                    r = { c.id : syntax.EVar(name) }
                    e = subst(e, r)
                    for j in range(i + 1, len(clauses)):
                        d = clauses[j]
                        if isinstance(d, syntax.CPull):
                            if any(v.id == d.id for r in replacements.values() for v in free_vars(r)):
                                raise NotImplementedError()
                            clauses[j] = syntax.CPull(d.id, subst(d.e, r))
                        elif isinstance(d, syntax.CCond):
                            clauses[j] = syntax.CCond(subst(d.e, r))
                else:
                    name = c.id
                clauses[i] = syntax.CPull(name, self.visit(c.e))
                return self.visit_lcmp(clauses, i + 1, e)
            elif isinstance(c, syntax.CCond):
                clauses[i] = syntax.CCond(self.visit(c.e))
                return self.visit_lcmp(clauses, i + 1, e)
        def visit_ELambda(self, e):
            m = replacements
            if e.arg.id in replacements:
                m = dict(m)
                del m[e.arg.id]
            arg = e.arg
            body = e.body
            while any(arg in free_vars(r) for r in replacements.values()):
                if hasattr(arg, "type"):
                    new_arg = fresh_var(arg.type)
                else:
                    new_arg = syntax.EVar(common.fresh_name())
                body = subst(body, { arg.id : new_arg })
                arg = new_arg
            return target_syntax.ELambda(arg, subst(body, m))
        def visit_ADT(self, e):
            children = e.children()
            children = tuple(self.visit(c) for c in children)
            return type(e)(*children)
        def visit_list(self, l):
            return [self.visit(x) for x in l]
        def visit_tuple(self, l):
            return tuple(self.visit(x) for x in l)
        def visit_dict(self, d):
            return {self.visit(k):self.visit(v) for (k,v) in d.items()}
        def visit_object(self, o):
            return o
        def visit_Type(self, t):
            return t
        def visit_Query(self, q):
            m = { name: repl for (name, repl) in replacements.items() if not any(n == name for (n, t) in q.args) }
            for (a, t) in q.args:
                for r in replacements.values():
                    if any(v.id == a for v in free_vars(r)):
                        raise NotImplementedError("need to rename query argument {} in {}".format(a, pprint(q)))
            return syntax.Query(
                q.name,
                q.visibility,
                q.args,
                [subst(a, m) for a in q.assumptions],
                subst(q.ret, m))
        def visit_Op(self, o):
            m = { name: repl for (name, repl) in replacements.items() if not any(n == name for (n, t) in o.args) }
            for (a, t) in o.args:
                for r in replacements.values():
                    if any(v.id == a for v in free_vars(r)):
                        raise NotImplementedError("need to rename op argument {} in {}".format(a, pprint(o)))
            return syntax.Op(
                o.name,
                o.args,
                [subst(a, m) for a in o.assumptions],
                subst(o.body, m))
        def visit(self, x, *args, **kwargs):
            res = super().visit(x, *args, **kwargs)
            if isinstance(res, syntax.Exp) and hasattr(x, "type") and not hasattr(res, "type"):
                res.type = x.type
            return res

    return Subst().visit(exp)

@common.typechecked
def qsubst(
        haystack : syntax.Exp,
        needle   : syntax.EVar,
        repl     : syntax.Exp):
    if repl.size() <= 1 or free_vars(haystack, counts=True).get(needle, 0) <= 1:
        return subst(haystack, { needle.id : repl })
    e = syntax.ELet(repl, target_syntax.ELambda(needle, haystack))
    if hasattr(haystack, "type"):
        e = e.with_type(haystack.type)
    return e

@common.typechecked
def alpha_equivalent(e1 : syntax.Exp, e2 : syntax.Exp) -> bool:
    """
    Equality on expression ASTs is syntactic equality; even variable names are
    compared. So,
        [x | x <- L] != [y | y <- L].
    However, alpha equivalence allows renaming of variables, so
        alpha_equivalent([x | x <- L], [y | y <- L]) == True.
    """
    class V(common.Visitor):
        def __init__(self):
            self.depth = 0
            self.remap_l = { } # maps e1 varnames ---> ids
            self.remap_r = { } # maps e2 varnames ---> ids

        @contextmanager
        @common.typechecked
        def unify(self, vs : [(syntax.EVar, syntax.EVar)], i : int = 0):
            if i >= len(vs):
                yield
            else:
                self.depth += 1
                v1, v2 = vs[i]
                with common.extend(self.remap_l, v1, self.depth):
                    with common.extend(self.remap_r, v2, self.depth):
                        with self.unify(vs, i + 1):
                            yield
                self.depth -= 1

        def visit_EVar(self, e1, e2):
            if not isinstance(e2, syntax.EVar):
                return False
            return self.remap_l.get(e1, e1) == self.remap_r.get(e2, e2)
        def visit_ETuple(self, e1, e2):
            if not isinstance(e2, syntax.ETuple):
                return False
            return all(self.visit(ee1, ee2) for (ee1, ee2) in zip(e1.es, e2.es))
        def visit_EMakeRecord(self, e1, e2):
            return (isinstance(e2, syntax.EMakeRecord) and
                all(k1 == k2 and self.visit(v1, v2) for ((k1, v1), (k2, v2)) in zip(e1.fields, e2.fields)))
        def visit_ELambda(self, e1, e2):
            if not isinstance(e2, target_syntax.ELambda):
                return False
            with self.unify([(e1.arg, e2.arg)]):
                return self.visit(e1.body, e2.body)
        def visit_EListComprehension(self, lcmp, other):
            if not isinstance(other, syntax.EListComprehension):
                return False
            if len(lcmp.clauses) != len(other.clauses):
                return False
            return self.visit_clauses(0, lcmp.clauses, other.clauses, lcmp.e, other.e)
        def visit_clauses(self, i, clauses1, clauses2, e1, e2):
            if i >= len(clauses1):
                return self.visit(e1, e2)
            c1 = clauses1[i]
            c2 = clauses2[i]
            if isinstance(c1, syntax.CPull):
                if not isinstance(c2, syntax.CPull):
                    return False
                with self.unify([(c1, c2)]):
                    return self.visit_clauses(i + 1, clauses1, clauses2, e1, e2)
            elif isinstance(c1, syntax.CCond):
                return self.visit(c1.e, c2.e) and self.visit_clauses(i + 1, clauses1, clauses2, e1, e2)
            else:
                raise NotImplementedError(pprint(c1))
        def visit_str(self, s1, s2):
            return s1 == s2
        def visit_int(self, i1, i2):
            return i1 == i2
        def visit_ECall(self, e1, e2):
            if not isinstance(e2, syntax.ECall):
                return False
            return e1.func == e2.func and len(e1.args) == len(e2.args) and all(self.visit(a1, a2) for (a1, a2) in zip(e1.args, e2.args))
        def visit_Exp(self, e1, e2):
            if type(e1) is not type(e2):
                return False
            return all(self.visit(x, y) for (x, y) in zip(e1.children(), e2.children()))
        def visit_Query(self, q1, q2):
            if type(q2) is not syntax.Query:
                return False
            if len(q1.args) != len(q2.args):
                return False
            with self.unify(list(zip([arg for (arg, t) in q1.args], [arg for (arg, t) in q2.args]))):
                # TODO: assumptions
                return self.visit(q1.ret, q2.ret)
        def visit_object(self, o, *args):
            raise NotImplementedError("{} ({})".format(type(o), repr(o)))

    return V().visit(e1, e2)

BOOL = syntax.TBool()

def implies(e1, e2):
    return syntax.EImplies(e1, e2)

def equal(e1, e2):
    return syntax.EEq(e1, e2)

@common.typechecked
def nnf(e : syntax.Exp, negate=False) -> syntax.Exp:
    """Convert a boolean expression to negation-normal-form (NNF)."""
    assert e.type == BOOL
    if isinstance(e, syntax.EUnaryOp) and e.op == "not":
        return nnf(e.e, negate=not negate)
    if isinstance(e, syntax.EBinOp) and e.op == "and":
        if negate:
            return syntax.EBinOp(nnf(e.e1, negate), "or", nnf(e.e2, negate)).with_type(BOOL)
        else:
            return syntax.EBinOp(nnf(e.e1), "and", nnf(e.e2)).with_type(BOOL)
    if isinstance(e, syntax.EBinOp) and e.op == "or":
        if negate:
            return syntax.EBinOp(nnf(e.e1, negate), "and", nnf(e.e2, negate)).with_type(BOOL)
        else:
            return syntax.EBinOp(nnf(e.e1), "or", nnf(e.e2)).with_type(BOOL)
    if isinstance(e, syntax.EBool):
        return syntax.EBool((not e.val) if negate else e.val).with_type(BOOL)
    if isinstance(e, syntax.EBinOp) and e.op == ">" and negate:
        return syntax.EBinOp(e.e1, "<=", e.e2).with_type(BOOL)
    if isinstance(e, syntax.EBinOp) and e.op == ">=" and negate:
        return syntax.EBinOp(e.e1, "<", e.e2).with_type(BOOL)
    if isinstance(e, syntax.EBinOp) and e.op == "<" and negate:
        return syntax.EBinOp(e.e1, ">=", e.e2).with_type(BOOL)
    if isinstance(e, syntax.EBinOp) and e.op == "<=" and negate:
        return syntax.EBinOp(e.e1, ">", e.e2).with_type(BOOL)
    return syntax.ENot(e) if negate else e

@common.typechecked
def dnf(e : syntax.Exp) -> [[syntax.Exp]]:
    """
    Convert a boolean expression to disjunction-normal-form (DNF). The input
    must already be in NNF.

    WARNING:
        This may result in an exponential blowup in the size of the expression.
    """
    assert e.type == BOOL
    if isinstance(e, syntax.EBinOp) and e.op == "or":
        return dnf(e.e1) + dnf(e.e2)
    if isinstance(e, syntax.EBinOp) and e.op == "and":
        cases1 = dnf(e.e1)
        cases2 = dnf(e.e2)
        return [c1 + c2 for c1 in cases1 for c2 in cases2]
    return [[e]]

def break_conj(e):
    if isinstance(e, syntax.EBinOp) and e.op == "and":
        yield from break_conj(e.e1)
        yield from break_conj(e.e2)
    else:
        yield e

class Aeq(object):
    def __init__(self, e : syntax.Exp):
        self.e = e
    def __hash__(self):
        res = 0
        q = [self.e]
        while q:
            x = q[-1]
            del q[-1]
            if isinstance(x, syntax.EVar):
                continue
            elif isinstance(x, common.ADT):
                res *= 31
                res += hash(type(x))
                res %= 2**64
                q.extend(x.children())
            elif isinstance(x, tuple) or isinstance(x, list):
                q.extend(x)
            else:
                res += hash(x)
                # raise NotImplementedError(repr(x))
        return res % (2**64)
    def __eq__(self, other):
        return isinstance(other, Aeq) and alpha_equivalent(self.e, other.e)
    def __ne__(self, other):
        return not (self == other)

def cse(e):
    """
    Common subexpression elimination. Replaces re-used expressions with ELet,
    e.g. "(x+1) + (x+1)" ---> "let a = x+1 in a+a".
    """
    def finish(e, avail):
        ravail = collections.OrderedDict([(v, k) for (k, v) in avail.items() if v is not None])
        counts = free_vars(e, counts=True)
        for var, value in reversed(ravail.items()):
            for (vv, ct) in free_vars(value, counts=True).items():
                counts[vv] = counts.get(vv, 0) + ct
        to_inline = common.OrderedSet(v for v in ravail if counts.get(v, 0) <= 1 or ravail[v].size() < 2)
        sub = { v : ravail[v] for v in to_inline }

        skip = { }
        class V(BottomUpRewriter):
            def visit_EVar(self, var):
                if var in sub and var not in skip:
                    return self.visit(sub[var])
                return var
            def visit_ELambda(self, lam):
                with common.extend(skip, lam.arg, True):
                    return target_syntax.ELambda(lam.arg, self.visit(lam.body))

        inliner = V()
        e = inliner.visit(e)

        for var, value in reversed(ravail.items()):
            if var in to_inline:
                continue
            value = inliner.visit(value)
            ee = syntax.ELet(value, target_syntax.ELambda(var, e))
            if hasattr(e, "type"):
                ee = ee.with_type(e.type)
            e = ee
        return e

    class V(BottomUpRewriter):
        def __init__(self):
            super().__init__()
            self.avail = collections.OrderedDict() # maps expressions --> variables
            self.avail_by_id = collections.OrderedDict() # maps ids -> variables
        def visit_Exp(self, e):
            if id(e) in self.avail_by_id:
                return self.avail_by_id[id(e)]
            ee = type(e)(*[self.visit(c) for c in e.children()])
            res = self.avail.get(ee)
            if res is not None:
                return res
            v = syntax.EVar(common.fresh_name("tmp"))
            if hasattr(e, "type"):
                ee = ee.with_type(e.type)
                v = v.with_type(e.type)
            self.avail[ee] = v
            self.avail_by_id[id(e)] = v
            return v
        def visit_ELambda(self, e):
            old_avail = self.avail
            old_avail_by_id = self.avail_by_id
            invalid = [e.arg]
            self.avail = collections.OrderedDict([(k, v) for (k, v) in self.avail.items() if k not in invalid])
            self.avail_by_id = collections.OrderedDict()
            body = self.visit(e.body)
            body = finish(body, self.avail)
            self.avail = old_avail # TODO: we can copy over exprs that don't use the arg
            self.avail_by_id = old_avail_by_id
            return target_syntax.ELambda(e.arg, body)

    v = V()
    res = v.visit(e)
    res = finish(res, v.avail)
    return res

@common.typechecked
def exp_wf(e : syntax.Exp, state_vars : [syntax.EVar], args : [syntax.EVar], pool = pools.RUNTIME_POOL):
    # if pool == STATE_POOL:
    #     assert not isinstance(e, EStateVar), "adding {} to state pool".format(pprint(e))
    #     assert not any(v in self.args for v in free_vars(e)), "bad vars: {}".format(pprint(e))
    # else:
    #     # state vars must be wrapped
    #     from cozy.syntax_tools import enumerate_fragments
    #     z = e
    #     dirty = True
    #     while dirty:
    #         dirty = False
    #         for (_, x, r, _) in enumerate_fragments(z):
    #             if isinstance(x, EStateVar):
    #                 from cozy.target_syntax import ZERO
    #                 z = r(ZERO)
    #                 dirty = True
    #                 break
    #     bad = find_one(free_vars(z), lambda v: not (v in self.binders or v in self.args))
    #     assert not bad, "state var `{}` not wrapped in: {!r}".format(bad.id, e)
    if pool == pools.STATE_POOL:
        assert strip_EStateVar(e) == e, "state exp has EStateVar inside: {}".format(pprint(e))
        assert not any(v in args for v in free_vars(e)), "bad vars: {}".format(pprint(e))
    elif pool == pools.RUNTIME_POOL:
        # state vars must be wrapped
        z = e
        dirty = True
        while dirty:
            dirty = False
            for (_, x, r, _) in enumerate_fragments(z):
                if isinstance(x, target_syntax.EStateVar):
                    assert exp_wf(x.e, state_vars, args, pools.STATE_POOL)
                    z = r(syntax.ZERO)
                    dirty = True
                    break
        bad = common.find_one(free_vars(z), lambda v: v in state_vars)
        assert not bad, "state var `{}` not wrapped in: {}".format(bad.id, pprint(e))
    return True
