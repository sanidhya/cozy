from itertools import chain

from cozy.common import typechecked
from cozy.target_syntax import *
from cozy.typecheck import is_collection
from cozy.solver import valid
from cozy.syntax_tools import pprint, subst, enumerate_fragments, cse, shallow_copy, mk_lambda
from cozy.handle_tools import reachable_handles_at_method
from cozy.incrementalization import delta_form
from cozy.opts import Option

invariant_preservation_check = Option("invariant-preservation-check", bool, True)

def EForall(e, p):
    return EUnaryOp(UOp.All, EMap(e, mk_lambda(e.type.t, p)).with_type(type(e.type)(BOOL))).with_type(BOOL)

@typechecked
def add_implicit_handle_assumptions(spec : Spec) -> Spec:
    """
    At the start of every method, for all reachable handles (i.e. those stored
    on the data structure plus those in arguments):
        If two different handles have the same address, then they have the same
        value.
    """
    spec = shallow_copy(spec)
    new_methods = []
    for m in spec.methods:
        handles = reachable_handles_at_method(spec, m)
        new_assumptions = []
        for t, bag in handles.items():
            print("handles of type {}: {}".format(pprint(t), pprint(bag)))
            new_assumptions.append(
                EForall(bag, lambda h1: EForall(bag, lambda h2:
                    EImplies(EEq(h1, h2),
                        EEq(EGetField(h1, "val").with_type(h1.type.value_type),
                            EGetField(h2, "val").with_type(h2.type.value_type))))))
            print("adding assumption to {}: {}".format(m.name, pprint(new_assumptions[-1])))
        m = shallow_copy(m)
        m.assumptions = list(m.assumptions) + new_assumptions
        new_methods.append(m)
    spec.methods = new_methods
    return spec

def check_ops_preserve_invariants(spec : Spec):
    if not invariant_preservation_check.value:
        return []
    res = []
    for m in spec.methods:
        if not isinstance(m, Op):
            continue
        remap = delta_form(spec.statevars, m)
        # print(m.name)
        # for id, e in remap.items():
        #     print("  {id} ---> {e}".format(id=id, e=pprint(e)))
        for a in spec.assumptions:
            a_post_delta = subst(a, remap)
            assumptions = list(m.assumptions) + list(spec.assumptions)
            if not valid(cse(EImplies(EAll(assumptions), a_post_delta))):
                res.append("{.name!r} may not preserve invariant {}".format(m, pprint(a)))
    return res

def check_the_wf(spec : Spec):
    res = []
    for (a, e, r, bound) in enumerate_fragments(spec):
        if isinstance(e, EUnaryOp) and e.op == UOp.The:
            if not valid(cse(EImplies(EAll(a), EAny([EIsSingleton(e.e), EEmpty(e.e)])))):
                res.append("at {}: `the` is illegal since its argument may not be singleton".format(pprint(e)))
    return res
