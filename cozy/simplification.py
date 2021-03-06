from cozy.target_syntax import *
from cozy.syntax_tools import BottomUpRewriter, alpha_equivalent, cse, compose, pprint
from cozy.evaluation import construct_value, eval
from cozy.solver import valid, satisfy

class _V(BottomUpRewriter):
    def __init__(self, debug=False):
        self.debug = debug
    def visit_EBinOp(self, e):
        if e.op == BOp.In:
            if isinstance(e.e2, EBinOp) and e.e2.op == "+":
                return self.visit(EAny([EIn(e.e1, e.e2.e1), EIn(e.e1, e.e2.e2)]))
            elif isinstance(e.e2, EUnaryOp) and e.e2.op == UOp.Distinct:
                return self.visit(EIn(e.e1, e.e2.e))
        elif e.op in ("==", "==="):
            e1 = self.visit(e.e1)
            e2 = self.visit(e.e2)
            if alpha_equivalent(e1, e2):
                return T
            if e.op == "==":
                while isinstance(e1, EWithAlteredValue): e1 = e1.handle
                while isinstance(e2, EWithAlteredValue): e2 = e2.handle
            e = EBinOp(e1, e.op, e2).with_type(e.type)
        if isinstance(e.e1, ECond):
            return self.visit(ECond(e.e1.cond,
                EBinOp(e.e1.then_branch, e.op, e.e2).with_type(e.type),
                EBinOp(e.e1.else_branch, e.op, e.e2).with_type(e.type)).with_type(e.type))
        if isinstance(e.e2, ECond):
            return self.visit(ECond(e.e2.cond,
                EBinOp(e.e1, e.op, e.e2.then_branch).with_type(e.type),
                EBinOp(e.e1, e.op, e.e2.else_branch).with_type(e.type)).with_type(e.type))
        return EBinOp(self.visit(e.e1), e.op, self.visit(e.e2)).with_type(e.type)
    def visit_ECond(self, e):
        cond = self.visit(e.cond)
        if cond == T:
            return self.visit(e.then_branch)
        elif cond == F:
            return self.visit(e.else_branch)
        elif alpha_equivalent(self.visit(e.then_branch), self.visit(e.else_branch)):
            return self.visit(e.then_branch)
        return ECond(cond, self.visit(e.then_branch), self.visit(e.else_branch)).with_type(e.type)
    def visit_EWithAlteredValue(self, e):
        t = e.type
        addr = self.visit(e.handle)
        val = self.visit(e.new_value)
        while isinstance(addr, EWithAlteredValue): addr = addr.handle
        if isinstance(addr, ECond):
            return self.visit(ECond(addr.cond,
                EWithAlteredValue(addr.then_branch, val).with_type(t),
                EWithAlteredValue(addr.else_branch, val).with_type(t)).with_type(t))
        return EWithAlteredValue(addr, val).with_type(t)
    def visit_EGetField(self, e):
        record = self.visit(e.e)
        if isinstance(record, ECond):
            return self.visit(ECond(record.cond,
                EGetField(record.then_branch, e.f).with_type(e.type),
                EGetField(record.else_branch, e.f).with_type(e.type)).with_type(e.type))
        if isinstance(record, EWithAlteredValue) and e.f == "val":
            return record.new_value
        if isinstance(record, EMakeRecord):
            return dict(record.fields)[e.f]
        return EGetField(record, e.f).with_type(e.type)
    def visit_EFilter(self, e):
        ee = self.visit(e.e)
        f = self.visit(e.p)
        if isinstance(ee, EBinOp) and ee.op == "+":
            return self.visit(EBinOp(EFilter(ee.e1, f).with_type(ee.e1.type), ee.op, EFilter(ee.e2, f).with_type(ee.e2.type)).with_type(e.type))
        elif isinstance(ee, ESingleton):
            return self.visit(ECond(
                f.apply_to(ee.e),
                ee,
                EEmptyList().with_type(e.type)).with_type(e.type))
        elif isinstance(ee, EMap):
            return self.visit(EMap(EFilter(ee.e, compose(f, ee.f)).with_type(ee.e.type), ee.f).with_type(e.type))
        return EFilter(ee, f).with_type(e.type)
    def visit_EMap(self, e):
        ee = self.visit(e.e)
        f = self.visit(e.f)
        if isinstance(ee, EBinOp) and ee.op == "+":
            return self.visit(EBinOp(EMap(ee.e1, f).with_type(e.type), ee.op, EMap(ee.e2, f).with_type(e.type)).with_type(e.type))
        elif isinstance(ee, ESingleton):
            return self.visit(ESingleton(f.apply_to(ee.e)).with_type(e.type))
        elif isinstance(ee, EMap):
            return self.visit(EMap(ee.e, compose(f, ee.f)).with_type(e.type))
        return EMap(ee, f).with_type(e.type)
    def visit_EArgMin(self, e):
        ee = self.visit(e.e)
        f = self.visit(e.f)
        argmin = type(e)
        if isinstance(ee, ESingleton):
            return ee.e
        elif isinstance(ee, EBinOp) and ee.op == "+":
            xs = ee.e1
            ys = ee.e2
            # A bit of trickery here since `argmin {...} (x+y)` produces an
            # expression of shape `argmin {...} (a+b)`.  If we aren't careful
            # we could get into an infinite loop.
            fallback = argmin(EBinOp(
                ESingleton(argmin(xs, f).with_type(e.type)).with_type(TBag(e.type)),
                "+",
                ESingleton(argmin(ys, f).with_type(e.type)).with_type(TBag(e.type))).with_type(TBag(e.type)), f).with_type(e.type)
            fallback._nosimpl = True
            res =   ECond(self.visit(EUnaryOp(UOp.Empty, xs).with_type(BOOL)), argmin(ys, f).with_type(e.type),
                    ECond(self.visit(EUnaryOp(UOp.Empty, ys).with_type(BOOL)), argmin(xs, f).with_type(e.type),
                        fallback).with_type(e.type)).with_type(e.type)
            return res
        return argmin(ee, f).with_type(e.type)
    def visit_EArgMax(self, e):
        return self.visit_EArgMin(e)
    def visit_EMapKeys(self, e):
        ee = self.visit(e.e)
        if isinstance(ee, EMakeMap2):
            return self.visit(EUnaryOp(UOp.Distinct, ee.e).with_type(e.type))
        return EMapKeys(ee).with_type(e.type)
    def visit_EUnaryOp(self, e):
        if isinstance(e.e, ECond):
            return self.visit(ECond(
                e.e.cond,
                EUnaryOp(e.op, e.e.then_branch).with_type(e.type),
                EUnaryOp(e.op, e.e.else_branch).with_type(e.type)).with_type(e.type))
        ee = self.visit(e.e)
        if e.op == UOp.Not:
            if isinstance(ee, EBool):
                return F if ee.val else T
        elif e.op in (UOp.Length, UOp.Sum):
            if isinstance(ee, EBinOp) and ee.op == "+":
                return self.visit(EBinOp(EUnaryOp(e.op, ee.e1).with_type(e.type), "+", EUnaryOp(e.op, ee.e2).with_type(e.type)).with_type(e.type))
            elif isinstance(ee, ESingleton):
                if e.op == UOp.Length:
                    return ONE
                elif e.op == UOp.Sum:
                    return ee.e
            elif isinstance(ee, EEmptyList):
                return ZERO
            elif isinstance(ee, EMap) and e.op == UOp.Length:
                return self.visit(EUnaryOp(e.op, ee.e).with_type(e.type))
        elif e.op in (UOp.Exists, UOp.Empty):
            if isinstance(ee, EMap) or (isinstance(ee, EUnaryOp) and ee.op == UOp.Distinct):
                return self.visit(EUnaryOp(e.op, ee.e).with_type(e.type))
            elif isinstance(ee, EBinOp) and ee.op == "+":
                if e.op == UOp.Exists:
                    return self.visit(EAny([
                        EUnaryOp(e.op, ee.e1).with_type(BOOL),
                        EUnaryOp(e.op, ee.e2).with_type(BOOL)]))
                elif e.op == UOp.Empty:
                    return self.visit(EAll([
                        EUnaryOp(e.op, ee.e1).with_type(BOOL),
                        EUnaryOp(e.op, ee.e2).with_type(BOOL)]))
            elif isinstance(ee, EEmptyList):
                return T if e.op == UOp.Empty else F
            elif isinstance(ee, ESingleton):
                return T if e.op == UOp.Exists else F
        return EUnaryOp(e.op, ee).with_type(e.type)
    def visit(self, e):
        if hasattr(e, "_nosimpl"): return e
        if isinstance(e, Exp) and not isinstance(e, ELambda): t = e.type
        new = super().visit(e)
        if isinstance(e, Exp) and not isinstance(e, ELambda): assert new.type == e.type, repr(e)
        if self.debug and isinstance(e, Exp) and not isinstance(e, ELambda):
            model = satisfy(ENot(EBinOp(e, "===", new).with_type(BOOL)))
            if model is not None:
                raise Exception("bad simplification: {} ---> {} (under model {!r}, got {!r} and {!r})".format(pprint(e), pprint(new), model, eval(e, model), eval(new, model)))
        return new

def simplify(e, validate=True, debug=False):
    try:
        visitor = _V(debug)
        orig = e
        e = visitor.visit(e)
        # e = cse(e)
        if validate and not valid(EBinOp(orig, "===", e).with_type(BOOL)):
            import sys
            print("simplify did something stupid!\nto reproduce:\nsimplify({e!r}, validate=True, debug=True)".format(e=orig), file=sys.stderr)
            return orig
        return e
    except:
        print("SIMPL FAILED")
        print(repr(e))
        raise
