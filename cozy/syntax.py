"""
AST definitions.
"""

from cozy.common import ADT, declare_case, typechecked

Spec                = declare_case(ADT, "Spec", ["name", "types", "extern_funcs", "statevars", "assumptions", "methods", "header", "footer"])
ExternFunc          = declare_case(ADT, "ExternFunc", ["name", "args", "out_type", "body_string"])

class Visibility(object):
    Public   = "public"   # usable by clients
    Private  = "private"  # helper used by other queries
    Internal = "internal" # helper used by op definitions

class Method(ADT): pass
Op                  = declare_case(Method, "Op",    ["name", "args", "assumptions", "body"])
Query               = declare_case(Method, "Query", ["name", "visibility", "args", "assumptions", "ret"])

class Type(ADT): pass
TInt                = declare_case(Type, "TInt")
TLong               = declare_case(Type, "TLong")
TBool               = declare_case(Type, "TBool")
TString             = declare_case(Type, "TString")
TNative             = declare_case(Type, "TNative", ["name"])
THandle             = declare_case(Type, "THandle", ["statevar", "value_type"])
TBag                = declare_case(Type, "TBag",    ["t"])
TSet                = declare_case(Type, "TSet",    ["t"])
TMap                = declare_case(Type, "TMap",    ["k", "v"])
TNamed              = declare_case(Type, "TNamed",  ["id"])
TRecord             = declare_case(Type, "TRecord", ["fields"])
TApp                = declare_case(Type, "TApp",    ["t", "args"])
TEnum               = declare_case(Type, "TEnum",   ["cases"])
TTuple              = declare_case(Type, "TTuple",  ["ts"])

# Unary operators
class UOp(object):
    Sum       = "sum"
    Not       = "not"
    Distinct  = "distinct"
    AreUnique = "unique"
    All       = "all"
    Any       = "any"
    Exists    = "exists"
    Length    = "len"
    Empty     = "empty"
    The       = "the"

UOps = (UOp.Sum,
        UOp.Not,
        UOp.Distinct,
        UOp.AreUnique,
        UOp.All,
        UOp.Any,
        UOp.Exists,
        UOp.Length,
        UOp.Empty,
        UOp.The)

# Binary operators
class BOp(object):
    And = "and"
    Or  = "or"
    In  = "in"

BOps = (BOp.And,
        BOp.Or,
        BOp.In)

class Exp(ADT):
    def with_type(self, t):
        self.type = t
        return self
    # def __setattr__(self, name, val):
    #     if name == "type" and isinstance(self, EEnumEntry) and not isinstance(val, TEnum):
    #         raise Exception("set {}.type = {}".format(self, val))
    #     super().__setattr__(name, val)
    # def __getattr__(self, name):
    #     raise AttributeError("expression {} has no {} field".format(self, name))
    def __repr__(self):
        s = super().__repr__()
        if hasattr(self, "type"):
            s += ".with_type({})".format(repr(self.type))
        return s

EVar                = declare_case(Exp, "EVar",               ["id"])
EBool               = declare_case(Exp, "EBool",              ["val"])
ENum                = declare_case(Exp, "ENum",               ["val"])
EStr                = declare_case(Exp, "EStr",               ["val"])
ENative             = declare_case(Exp, "ENative",            ["e"])
EEnumEntry          = declare_case(Exp, "EEnumEntry",         ["name"])
ENull               = declare_case(Exp, "ENull")
ECond               = declare_case(Exp, "ECond",              ["cond", "then_branch", "else_branch"])
EBinOp              = declare_case(Exp, "EBinOp",             ["e1", "op", "e2"])
EUnaryOp            = declare_case(Exp, "EUnaryOp",           ["op", "e"])
EArgMin             = declare_case(Exp, "EArgMin",            ["e", "f"])
EArgMax             = declare_case(Exp, "EArgMax",            ["e", "f"])
EHandle             = declare_case(Exp, "EHandle",            ["addr", "value"])
EGetField           = declare_case(Exp, "EGetField",          ["e", "f"])
EMakeRecord         = declare_case(Exp, "EMakeRecord",        ["fields"])
EListComprehension  = declare_case(Exp, "EListComprehension", ["e", "clauses"])
EEmptyList          = declare_case(Exp, "EEmptyList")
ESingleton          = declare_case(Exp, "ESingleton",         ["e"])
ECall               = declare_case(Exp, "ECall",              ["func", "args"])
ETuple              = declare_case(Exp, "ETuple",             ["es"])
ETupleGet           = declare_case(Exp, "ETupleGet",          ["e", "n"])
ELet                = declare_case(Exp, "ELet",               ["e", "f"])

# Lambdas
TFunc = declare_case(Type, "TFunc", ["arg_types", "ret_type"])
class ELambda(Exp):
    @typechecked
    def __init__(self, arg : EVar, body : Exp):
        self.arg = arg
        self.body = body
    def apply_to(self, arg):
        from cozy.syntax_tools import subst
        return subst(self.body, { self.arg.id : arg })
    def children(self):
        return (self.arg, self.body)
    def __repr__(self):
        return "ELambda{}".format(repr(self.children()))

class ComprehensionClause(ADT): pass
CPull               = declare_case(ComprehensionClause, "CPull", ["id", "e"])
CCond               = declare_case(ComprehensionClause, "CCond", ["e"])

class Stm(ADT): pass
SNoOp               = declare_case(Stm, "SNoOp")
SSeq                = declare_case(Stm, "SSeq",     ["s1", "s2"])
SCall               = declare_case(Stm, "SCall",    ["target", "func", "args"])
SAssign             = declare_case(Stm, "SAssign",  ["lhs", "rhs"])
SDecl               = declare_case(Stm, "SDecl",    ["id", "val"])
SForEach            = declare_case(Stm, "SForEach", ["id", "iter", "body"])
SIf                 = declare_case(Stm, "SIf",      ["cond", "then_branch", "else_branch"])

# -----------------------------------------------------------------------------
# Various utilities

BOOL = TBool()
INT = TInt()
LONG = TLong()
STRING = TString()
BOOL_BAG = TBag(BOOL)
INT_BAG = TBag(INT)

T = EBool(True) .with_type(BOOL)
F = EBool(False).with_type(BOOL)
ZERO = ENum(0).with_type(INT)
ONE = ENum(1).with_type(INT)
NULL = ENull()

def seq(stms):
    stms = [s for s in stms if not isinstance(s, SNoOp)]
    if not stms:
        return SNoOp()
    elif len(stms) == 1:
        return stms[0]
    else:
        result = None
        for s in stms:
            result = s if result is None else SSeq(result, s)
        return result

def build_balanced_tree(t, op, es : [Exp], st=None, ed=None):
    """
    Create a balanced expression tree out of an associative binary operator.

    Many internal functions do not like deep, stick-shaped trees since those
    functions are recursive and Python has a small-ish maximum stack depth.
    """
    if st is None:
        st = 0
    if ed is None:
        ed = len(es)
    n = ed - st
    assert n > 0, "cannot create balanced tree out of empty list"
    if n == 1:
        return es[st]
    else:
        cut = st + (n // 2)
        return EBinOp(
            build_balanced_tree(t, op, es, st=st, ed=cut), op,
            build_balanced_tree(t, op, es, st=cut, ed=ed)).with_type(t)

def EAll(exps):
    exps = [ e for e in exps if e != T ]
    if any(e == F for e in exps):
        return F
    if not exps:
        return T
    return build_balanced_tree(BOOL, BOp.And, exps)

def EAny(exps):
    return ENot(EAll([ENot(e) for e in exps]))

def ENot(e):
    if isinstance(e, EUnaryOp) and e.op == "not":
        return e.e
    return EUnaryOp("not", e).with_type(BOOL)

def EIsSubset(e1, e2):
    return EBinOp(
        EBinOp(e1, "-", e2).with_type(e1.type), "==",
        EEmptyList().with_type(e1.type)).with_type(BOOL)

def EIsSingleton(e):
    return EEq(EUnaryOp(UOp.Length, e).with_type(INT), ONE)

def EEmpty(e):
    return EUnaryOp(UOp.Empty, e).with_type(BOOL)

def EEq(e1, e2):
    return EBinOp(e1, "==", e2).with_type(BOOL)

def EIn(e1, e2):
    return EBinOp(e1, BOp.In, e2).with_type(BOOL)

def EImplies(e1, e2):
    return EBinOp(ENot(e1), BOp.Or, e2).with_type(BOOL)
