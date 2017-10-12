"""
While the syntax module declares the core _input_ language, this module declares
additional syntax extensions that can appear in the _target_ language: the
primitives the tool can output and use during synthesis.
"""

from cozy.syntax import *
from cozy.common import declare_case, typechecked, fresh_name
from cozy.opts import Option

enforce_estatevar_wf = Option("enforce-well-formed-state-var-boundaries", bool, False)

# Misc
TRef       = declare_case(Type, "TRef", ["t"])
EEnumToInt = declare_case(Exp, "EEnumToInt", ["e"])
EBoolToInt = declare_case(Exp, "EBoolToInt", ["e"])
EStm       = declare_case(Exp, "EStm", ["stm", "e"])

# State var barrier: sub-expression should be maintained as a fresh state var
EStateVar  = declare_case(Exp, "EStateVar", ["e"])

class IllegalStateVarBoundary(Exception):
    pass
old = EStateVar.__init__
def f(self, e):
    if enforce_estatevar_wf.value:
        from cozy.syntax_tools import free_vars, pprint
        if not all(not v.id.startswith("_") for v in free_vars(e)):
            raise IllegalStateVarBoundary(pprint(e))
    old(self, e)
EStateVar.__init__ = f

def EIsSingleton(e):
    arg = EVar(fresh_name()).with_type(e.type.t)
    return EBinOp(EUnaryOp(UOp.Sum, EMap(e, ELambda(arg, ONE)).with_type(TBag(INT))).with_type(INT), "<=", ONE).with_type(BOOL)

# Fixed-length vectors
TVector    = declare_case(Type, "TVector", ["t", "n"])
EVectorGet = declare_case(Exp, "EVectorGet", ["e", "i"])

# Iterators
SWhile   = declare_case(Stm, "SWhile", ["e", "body"])

# Fake go-to
SEscapableBlock = declare_case(Stm, "SEscapableBlock", ["label", "body"])
SEscapeBlock    = declare_case(Stm, "SEscapeBlock", ["label"])

# Bag transformations
EFilter  = declare_case(Exp, "EFilter",  ["e", "p"])
EMap     = declare_case(Exp, "EMap",     ["e", "f"])
EFlatMap = declare_case(Exp, "EFlatMap", ["e", "f"])

# Handle transformations
EWithAlteredValue = declare_case(Exp, "EWithAlteredValue", ["handle", "new_value"])

# Maps
EMakeMap   = declare_case(Exp, "EMakeMap", ["e", "key", "value"])
EMakeMap2  = declare_case(Exp, "EMakeMap2", ["e", "value"])
EMapGet    = declare_case(Exp, "EMapGet", ["map", "key"])
EMapKeys   = declare_case(Exp, "EMapKeys", ["e"])
SMapPut    = declare_case(Stm, "SMapPut", ["map", "key", "value"])
SMapDel    = declare_case(Stm, "SMapDel", ["map", "key"])
SMapUpdate = declare_case(Stm, "SMapUpdate", ["map", "key", "val_var", "change"])
