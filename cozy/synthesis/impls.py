"""
Code relating to implementations.

Implementations are almost exactly like Spec objects, but they have
concretization functions relating them to their underlying specifications and
they store various other information to aid synthesis.
"""

import itertools
from collections import OrderedDict, defaultdict

import igraph

from cozy.common import fresh_name, find_one, typechecked, OrderedSet
from cozy.syntax import *
from cozy.target_syntax import EFilter, EDeepIn, EStateVar
from cozy.syntax_tools import subst, free_vars, fresh_var, alpha_equivalent, all_exps, BottomUpRewriter, BottomUpExplorer, pprint, replace, shallow_copy, tease_apart, wrap_naked_statevars
from cozy.handle_tools import reachable_handles_at_method, implicit_handle_assumptions_for_method
import cozy.incrementalization as inc
from cozy.opts import Option
from cozy.simplification import simplify

from .misc import rewrite_ret, queries_equivalent

dedup_queries = Option("deduplicate-subqueries", bool, True)

def _queries_used_by(thing):
    qs = set()
    class V(BottomUpExplorer):
        def visit_ECall(self, e):
            qs.add(e.func)
    V().visit(thing)
    return qs

def safe_feedback_arc_set(g, method):
    """
    Compute the feedback arc set for directed graph `g`.

    This function works around a potential segfault in igraph:
    https://github.com/igraph/igraph/issues/858
    """

    assert g.is_directed()

    # No verts? No problem!
    if g.vcount() == 0:
        return []

    orig_g = g
    g = g.copy()

    # Add a "terminal" node with an edge from every vertex.
    # This should not affect the feedback arc set.
    new_vertex_id = g.vcount()
    g.add_vertices(1)
    g.add_edges([(v, new_vertex_id) for v in range(new_vertex_id)])

    edge_ids = g.feedback_arc_set(method=method)

    # I assume the edge ids are the same between g and its copy?
    # Let's do a little bit of checking just in case.
    g.delete_vertices([new_vertex_id])
    to_check = [g.es[e].source for e in edge_ids]
    d1 = orig_g.degree(to_check)
    d2 = g.degree(to_check)
    assert d1 == d2, "{!r} vs {!r}".format(d1, d2)

    return edge_ids

class Implementation(object):

    @typechecked
    def __init__(self,
            spec : Spec,
            concrete_state : [(EVar, Exp)],
            query_specs : [Query],
            query_impls : OrderedDict,
            updates : defaultdict,
            handle_updates : defaultdict):
        self.spec = spec
        self.concrete_state = concrete_state
        self.query_specs = query_specs
        self.query_impls = query_impls
        self.updates = updates # maps (concrete_var_name, op_name) to stm
        self.handle_updates = handle_updates # maps (handle_type, op_name) to stm

    def add_query(self, q : Query):
        """
        Given a query in terms of abstract state, add an initial concrete
        implementation.
        """
        self.query_specs.append(q)
        fvs = free_vars(q)
        # initial rep
        qargs = set(EVar(a).with_type(t) for (a, t) in q.args)
        rep, ret = tease_apart(wrap_naked_statevars(q.ret, self.abstract_state))
        self.set_impl(q, rep, ret)

    @property
    def op_specs(self):
        return [ m for m in self.spec.methods if isinstance(m, Op) ]

    @property
    def abstract_state(self):
        return [EVar(name).with_type(t) for (name, t) in self.spec.statevars]

    def _add_subquery(self, sub_q : Query, used_by : Stm) -> Stm:
        print("Adding new query {}...".format(sub_q.name))
        # orig_ret = sub_q.ret
        # print("rewritng ret for {}".format(pprint(orig_ret)))
        sub_q = shallow_copy(sub_q)
        sub_q.assumptions += tuple(
            implicit_handle_assumptions_for_method(
                reachable_handles_at_method(self.spec, sub_q),
                sub_q))
        sub_q.ret = simplify(sub_q.ret)
        # sub_q = rewrite_ret(sub_q, simplify)
        # if sub_q.ret != orig_ret:
        #     print("rewrote ret")
        #     print(" --> {}".format(pprint(sub_q.ret)))

        qq = find_one(self.query_specs, lambda qq: dedup_queries.value and queries_equivalent(qq, sub_q))
        if qq is not None:
            print("########### subgoal {} is equivalent to {}".format(sub_q.name, qq.name))
            arg_reorder = [[x[0] for x in sub_q.args].index(a) for (a, t) in qq.args]
            class Repl(BottomUpRewriter):
                def visit_ECall(self, e):
                    args = tuple(self.visit(a) for a in e.args)
                    if e.func == sub_q.name:
                        args = tuple(args[idx] for idx in arg_reorder)
                        return ECall(qq.name, args).with_type(e.type)
                    else:
                        return ECall(e.func, args).with_type(e.type)
            used_by = Repl().visit(used_by)
        else:
            self.add_query(sub_q)
        return used_by

    def _setup_handle_updates(self):
        """
        This method creates update code for handle objects modified by each op.
        Must be called once after all user-specified queries have been added.
        """
        for op in self.op_specs:
            handles = reachable_handles_at_method(self.spec, op)
            # print("-"*60)
            for t, bag in handles.items():
                # print("  {} : {}".format(pprint(t), pprint(bag)))
                h = fresh_var(t)
                delta = inc.delta_form(self.spec.statevars + op.args + [(h.id, h.type)], op)
                lval = EGetField(h, "val").with_type(t.value_type)
                new_val = simplify(subst(lval, delta))

                # get set of modified handles
                modified_handles = Query(
                    fresh_name("modified_handles"),
                    Visibility.Internal, [], op.assumptions,
                    EFilter(EUnaryOp(UOp.Distinct, bag).with_type(bag.type), ELambda(h, ENot(EEq(lval, new_val)))).with_type(bag.type),
                    "[{}] modified handles of type {}".format(op.name, pprint(t)))
                query_vars = [v for v in free_vars(modified_handles) if v not in self.abstract_state]
                modified_handles.args = [(arg.id, arg.type) for arg in query_vars]

                # modify each one
                (state_update_stm, subqueries) = inc.sketch_update(
                    lval,
                    lval,
                    new_val,
                    self.abstract_state,
                    list(op.assumptions) + [EDeepIn(h, bag), EIn(h, modified_handles.ret)])
                # print("  got {} subqueries".format(len(subqueries)))
                # print("  to update {} in {}, use\n{}".format(pprint(t), op.name, pprint(state_update_stm)))
                for sub_q in subqueries:
                    sub_q.docstring = "[{}] {}".format(op.name, sub_q.docstring)
                    state_update_stm = self._add_subquery(sub_q=sub_q, used_by=state_update_stm)
                if state_update_stm != SNoOp():
                    state_update_stm = SForEach(h, ECall(modified_handles.name, query_vars).with_type(bag.type), state_update_stm)
                    state_update_stm = self._add_subquery(sub_q=modified_handles, used_by=state_update_stm)
                self.handle_updates[(t, op.name)] = state_update_stm

    def set_impl(self, q : Query, rep : [(EVar, Exp)], ret : Exp):
        to_remove = set()
        from cozy.solver import valid
        for (v, e) in rep:
            aeq = find_one(vv for (vv, ee) in self.concrete_state if e.type == ee.type and valid(EImplies(EAll(self.spec.assumptions), EEq(e, ee))))
            # aeq = find_one(vv for (vv, ee) in self.concrete_state if e.type == ee.type and alpha_equivalent(e, ee))
            if aeq is not None:
                print("########### state var {} is equivalent to {}".format(v.id, aeq.id))
                ret = subst(ret, { v.id : aeq })
                to_remove.add(v)
        rep = [ x for x in rep if x[0] not in to_remove ]

        self.concrete_state.extend(rep)
        self.query_impls[q.name] = rewrite_ret(q, lambda prev: ret, keep_assumptions=False)
        op_deltas = { op.name : inc.delta_form(self.spec.statevars, op) for op in self.op_specs }

        for op in self.op_specs:
            # print("###### INCREMENTALIZING: {}".format(op.name))
            delta = op_deltas[op.name]
            for new_member, projection in rep:
                (state_update_stm, subqueries) = inc.sketch_update(
                    new_member,
                    projection,
                    subst(projection, delta),
                    self.abstract_state,
                    list(op.assumptions))
                for sub_q in subqueries:
                    sub_q.docstring = "[{}] {}".format(op.name, sub_q.docstring)
                    state_update_stm = self._add_subquery(sub_q=sub_q, used_by=state_update_stm)
                self.updates[(new_member, op.name)] = state_update_stm

    @property
    def code(self) -> Spec:

        state_read_by_query = {
            query_name : free_vars(query)
            for query_name, query in self.query_impls.items() }

        def queries_used_by(stm):
            for e in all_exps(stm):
                if isinstance(e, ECall) and e.func in [q.name for q in self.query_specs]:
                    yield e.func

        # prevent read-after-write by lifting reads before writes.

        # list of SDecls
        temps = defaultdict(list)
        updates = dict(self.updates)

        for operator in self.op_specs:
            # Compute order constraints between statements:
            #   v1 -> v2 means that the update code for v1 should (if possible)
            #   appear before the update code for v2
            #   (i.e. the update code for v1 reads v2)
            g = igraph.Graph().as_directed()
            g.add_vertices(len(self.concrete_state))
            for (i, (v1, _)) in enumerate(self.concrete_state):
                v1_update_code = self.updates[(v1, operator.name)]
                v1_queries = list(queries_used_by(v1_update_code))
                for (j, (v2, _)) in enumerate(self.concrete_state):
                    # if v1_update_code reads v2...
                    if any(v2 in state_read_by_query[q] for q in v1_queries):
                        # then v1->v2
                        g.add_edges([(i, j)])

            # Find the minimum set of edges we need to break (see "feedback arc
            # set problem")
            edges_to_break = safe_feedback_arc_set(g, method="ip")
            g.delete_edges(edges_to_break)
            ordered_concrete_state = [self.concrete_state[i] for i in g.topological_sorting(mode="OUT")]

            # Lift auxiliary declarations as needed
            things_updated = []
            for v, _ in ordered_concrete_state:
                things_updated.append(v)
                stm = updates[(v, operator.name)]

                for e in all_exps(stm):
                    if isinstance(e, ECall) and e.func in [q.name for q in self.query_specs]:
                        problems = set(things_updated) & state_read_by_query[e.func]

                        if problems:
                            name = fresh_name()
                            temps[operator.name].append(SDecl(name, e))
                            stm = replace(stm, e, EVar(name).with_type(e.type))
                            updates[(v, operator.name)] = stm

        # construct new op implementations
        new_ops = []
        for op in self.op_specs:

            stms = [ updates[(v, op.name)] for (v, _) in ordered_concrete_state ]
            stms.extend(hup for ((t, op_name), hup) in self.handle_updates.items() if op.name == op_name)
            new_stms = seq(temps[op.name] + stms)
            new_ops.append(Op(
                op.name,
                op.args,
                [],
                new_stms,
                op.docstring))

        # assemble final result
        return Spec(
            self.spec.name,
            self.spec.types,
            self.spec.extern_funcs,
            [(v.id, e.type) for (v, e) in self.concrete_state],
            [],
            list(self.query_impls.values()) + new_ops,
            self.spec.header,
            self.spec.footer,
            self.spec.docstring)

    @property
    def concretization_functions(self) -> { str : Exp }:
        state_var_exps = OrderedDict()
        for (v, e) in self.concrete_state:
            state_var_exps[v.id] = e
        return state_var_exps

    def cleanup(self):
        """
        Remove unused state, queries, and updates.
        """

        # sort of like mark-and-sweep
        queries_to_keep = OrderedSet(q.name for q in self.query_specs if q.visibility == Visibility.Public)
        state_vars_to_keep = OrderedSet()
        changed = True
        while changed:
            changed = False
            for qname in list(queries_to_keep):
                if qname in self.query_impls:
                    for sv in free_vars(self.query_impls[qname]):
                        if sv not in state_vars_to_keep:
                            state_vars_to_keep.add(sv)
                            changed = True
                    for e in all_exps(self.query_impls[qname].ret):
                        if isinstance(e, ECall):
                            if e.func not in queries_to_keep:
                                queries_to_keep.add(e.func)
                                changed = True
            for op in self.op_specs:
                for ((ht, op_name), code) in self.handle_updates.items():
                    if op.name == op_name:
                        for qname in _queries_used_by(code):
                            if qname not in queries_to_keep:
                                queries_to_keep.add(qname)
                                changed = True

                for sv in state_vars_to_keep:
                    for qname in _queries_used_by(self.updates[(sv, op.name)]):
                        if qname not in queries_to_keep:
                            queries_to_keep.add(qname)
                            changed = True

        # remove old specs
        for q in list(self.query_specs):
            if q.name not in queries_to_keep:
                self.query_specs.remove(q)

        # remove old implementations
        for qname in list(self.query_impls.keys()):
            if qname not in queries_to_keep:
                del self.query_impls[qname]

        # remove old state vars
        self.concrete_state = [ v for v in self.concrete_state if any(v[0] in free_vars(q) for q in self.query_impls.values()) ]

        # remove old method implementations
        for k in list(self.updates.keys()):
            v, op_name = k
            if v not in [var for (var, exp) in self.concrete_state]:
                del self.updates[k]

@typechecked
def construct_initial_implementation(spec : Spec) -> Implementation:
    """
    Takes a typechecked specification as input, returns an initial
    implementation.
    """

    impl = Implementation(spec, [], [], OrderedDict(), defaultdict(SNoOp), defaultdict(SNoOp))
    for m in spec.methods:
        if isinstance(m, Query):
            impl.add_query(m)
    impl._setup_handle_updates()
    impl.cleanup()

    # print(pprint(impl.code))
    # raise NotImplementedError()

    return impl
