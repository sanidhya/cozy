import unittest

from cozy.solver import satisfy, valid, satisfiable
from cozy.typecheck import typecheck, retypecheck
from cozy.target_syntax import *
from cozy.syntax_tools import pprint, equal, implies, mk_lambda

zero = ENum(0).with_type(TInt())
one  = ENum(1).with_type(TInt())

class TestSolver(unittest.TestCase):

    def test_the_empty(self):
        x = EEmptyList().with_type(TBag(TInt()))
        assert satisfy(EBinOp(EUnaryOp("the", x).with_type(TMaybe(TInt())), "==", EJust(one)).with_type(TBool())) is None
        assert satisfy(EBinOp(EUnaryOp("the", x).with_type(TMaybe(TInt())), "==", EJust(zero)).with_type(TBool())) is None

    def test_the(self):
        x = ESingleton(zero).with_type(TBag(TInt()))
        assert satisfy(EBinOp(EUnaryOp("the", x).with_type(TMaybe(TInt())), "==", EJust(zero)).with_type(TBool())) is not None
        assert satisfy(EBinOp(EUnaryOp("the", x).with_type(TMaybe(TInt())), "==", EJust(one)).with_type(TBool())) is None

    def test_the_acts_like_first(self):
        x = EBinOp(ESingleton(zero).with_type(TBag(TInt())), "+", ESingleton(one).with_type(TBag(TInt()))).with_type(TBag(TInt()))
        assert satisfy(EBinOp(EUnaryOp("the", x).with_type(TMaybe(TInt())), "==", EJust(zero)).with_type(TBool())) is not None
        assert satisfy(EBinOp(EUnaryOp("the", x).with_type(TMaybe(TInt())), "==", EJust(one)).with_type(TBool())) is None

    def test_the(self):
        tgroup = TRecord((('name', TString()), ('description', TString()), ('rosterMode', TEnum(('NOBODY', 'ONLY_GROUP', 'EVERYBODY'))), ('groupList', TBag(TString())), ('members', TBag(TNative('org.xmpp.packet.JID'))), ('administrators', TBag(TNative('org.xmpp.packet.JID')))))
        groups = EVar('groups').with_type(TBag(THandle('groups', tgroup)))
        e = EUnaryOp('not', EBinOp(EUnaryOp('the', groups).with_type(TMaybe(THandle('groups', tgroup))), '==', EUnaryOp('the', EMap(EFilter(groups, ELambda(EVar('g').with_type(THandle('groups', tgroup)), EBinOp(EGetField(EGetField(EVar('g').with_type(THandle('groups', tgroup)), 'val').with_type(tgroup), 'name').with_type(TString()), '==', EVar('name').with_type(TString())).with_type(TBool()))).with_type(TBag(THandle('groups', tgroup))), ELambda(EVar('g').with_type(THandle('groups', tgroup)), EVar('g').with_type(THandle('groups', tgroup)))).with_type(TBag(THandle('groups', tgroup)))).with_type(TMaybe(THandle('groups', tgroup)))).with_type(TBool())).with_type(TBool())
        vars = [EVar('users').with_type(TBag(THandle('users', TRecord((('username', TString()), ('salt', TString()), ('storedKey', TString()), ('serverKey', TString()), ('iterations', TInt()), ('name', TString()), ('email', TString()), ('creationDate', TNative('java.util.Date')), ('modificationDate', TNative('java.util.Date'))))))), EVar('rosterItems').with_type(TBag(THandle('rosterItems', TRecord((('backendId', TLong()), ('user', TString()), ('target', TNative('org.xmpp.packet.JID')), ('nickname', TString()), ('askStatus', TNative('org.jivesoftware.openfire.roster.RosterItem.AskType')), ('recvStatus', TNative('org.jivesoftware.openfire.roster.RosterItem.RecvType'))))))), groups, EVar('name').with_type(TString())]
        errs = typecheck(e, env={ v.id:v.type for v in vars })
        assert not errs
        assert satisfy(e, vars=vars, validate_model=True) is not None

    def test_empty_sum(self):
        x = EVar("x").with_type(TInt())
        model = satisfy(equal(x, EUnaryOp("sum", EEmptyList().with_type(TBag(TInt()))).with_type(INT)))
        assert model is not None
        assert model[x.id] == 0

    def test_weird_map_get(self):
        employee_type = TRecord((('employee_name', TInt()), ('employer_id', TInt())))
        employer_type = TRecord((('employer_name', TInt()), ('employer_id', TInt())))
        s = EUnaryOp('sum', EMap(EMapGet(EMakeMap(EVar('employers').with_type(TBag(THandle('employers', employer_type))), ELambda(EVar('_var49').with_type(THandle('employers', employer_type)), EGetField(EGetField(EVar('_var49').with_type(THandle('employers', employer_type)), 'val').with_type(employer_type), 'employer_id').with_type(TInt())), ELambda(EVar('_var57').with_type(TBag(THandle('employers', employer_type))), EVar('_var57').with_type(TBag(THandle('employers', employer_type))))).with_type(TMap(TInt(), TBag(THandle('employers', employer_type)))), EVar('employer_name').with_type(TInt())).with_type(TBag(THandle('employers', employer_type))), ELambda(EVar('_var48').with_type(THandle('employers', employer_type)), EGetField(EGetField(EVar('_var48').with_type(THandle('employers', employer_type)), 'val').with_type(employer_type), 'employer_name').with_type(TInt()))).with_type(TBag(TInt()))).with_type(TInt())
        e = EMapGet(EMakeMap(EVar('employees').with_type(TBag(THandle('employees', employee_type))), ELambda(EVar('_var39').with_type(THandle('employees', employee_type)), EGetField(EGetField(EVar('_var39').with_type(THandle('employees', employee_type)), 'val').with_type(employee_type), 'employer_id').with_type(TInt())), ELambda(EVar('_var45').with_type(TBag(THandle('employees', employee_type))), EVar('_var45').with_type(TBag(THandle('employees', employee_type))))).with_type(TMap(TInt(), TBag(THandle('employees', employee_type)))), s).with_type(TBag(THandle('employees', employee_type)))
        satisfy(equal(e, EEmptyList().with_type(e.type)))

    def test_function_extraction(self):
        x = EVar("x").with_type(TNative("Foo"))
        e = ECall("f", [x]).with_type(TBool())
        model = satisfy(e)
        assert "x" in model
        assert "f" in model
        assert model["f"](model["x"]) is True

    def test_symbolic_maps(self):
        x = EVar("x").with_type(TMap(TInt(), TInt()))
        y = EVar("y").with_type(TMap(TInt(), TInt()))
        e = ENot(equal(x, y))
        model = satisfy(e, validate_model=True)

    def test_regression1(self):
        satisfy(
            EBinOp(EBinOp(EBinOp(EUnaryOp('unique', EMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var13').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var13').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt()))).with_type(TBag(TInt()))).with_type(TBool()), 'and', EUnaryOp('unique', EVar('ints').with_type(TBag(THandle('_HandleType12', TInt())))).with_type(TBool())).with_type(TBool()), 'and', EBinOp(EVar('_var1141').with_type(TMap(TInt(), TBag(TInt()))), '==', EMakeMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var22').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var22').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt())), ELambda(EVar('_var1138').with_type(TBag(THandle('_HandleType12', TInt()))), EMap(EVar('_var1138').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var22').with_type(THandle('_HandleType12', TInt())), ENum(1).with_type(TInt()))).with_type(TBag(TInt())))).with_type(TMap(TInt(), TBag(TInt())))).with_type(TBool())).with_type(TBool()), 'and', EBinOp(EUnaryOp('sum', EMap(EFilter(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var1168').with_type(THandle('_HandleType12', TInt())), EBinOp(EGetField(EVar('_var1168').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt()), '==', EVar('i').with_type(TInt())).with_type(TBool()))).with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var1730').with_type(TMaybe(THandle('_HandleType12', TInt()))), ENum(1).with_type(TInt()))).with_type(TBag(TInt()))).with_type(TInt()), '==', ENum(0).with_type(TInt())).with_type(TBool())).with_type(TBool()),
            vars=None,
            collection_depth=2,
            validate_model=True)

    def test_regression2(self):
        vars = [EVar('i').with_type(TInt()), EVar('_var1210').with_type(TMap(TInt(), TBag(TInt()))), EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), EVar('_var45').with_type(TInt()), EVar('_var31').with_type(TBag(THandle('_HandleType12', TInt())))]
        e = EBinOp(EBinOp(EBinOp(EBinOp(EBinOp(EUnaryOp('unique', EMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var13').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var13').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt()))).with_type(TBag(TInt()))).with_type(TBool()), 'and', EUnaryOp('unique', EVar('ints').with_type(TBag(THandle('_HandleType12', TInt())))).with_type(TBool())).with_type(TBool()), 'and', EBinOp(EVar('_var31').with_type(TBag(THandle('_HandleType12', TInt()))), '==', EVar('ints').with_type(TBag(THandle('_HandleType12', TInt())))).with_type(TBool())).with_type(TBool()), 'and', EBinOp(EVar('_var1210').with_type(TMap(TInt(), TBag(TInt()))), '==', EMakeMap(EVar('_var31').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var46').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var46').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt())), ELambda(EVar('_var1207').with_type(TBag(THandle('_HandleType12', TInt()))), EMap(EVar('_var1207').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var46').with_type(THandle('_HandleType12', TInt())), ENum(1).with_type(TInt()))).with_type(TBag(TInt())))).with_type(TMap(TInt(), TBag(TInt())))).with_type(TBool())).with_type(TBool()), 'and', EBinOp(EVar('_var45').with_type(TInt()), '==', EUnaryOp('sum', EMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var21').with_type(THandle('_HandleType12', TInt())), ENum(1).with_type(TInt()))).with_type(TBag(TInt()))).with_type(TInt())).with_type(TBool())).with_type(TBool()), 'and', EUnaryOp('not', EBinOp(EUnaryOp('not', EBinOp(ENum(0).with_type(TInt()), '==', EUnaryOp('sum', EMapGet(EVar('_var1210').with_type(TMap(TInt(), TBag(TInt()))), EVar('i').with_type(TInt())).with_type(TBag(TInt()))).with_type(TInt())).with_type(TBool())).with_type(TBool()), '==', EBool(True).with_type(TBool())).with_type(TBool())).with_type(TBool())).with_type(TBool())
        assert retypecheck(e, env={ v.id : v.type for v in vars })
        satisfy(e, vars=vars, collection_depth=2, validate_model=True)

    def test_regression3(self):
        e = EBinOp(EBinOp(EUnaryOp('unique', EMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var13').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var13').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt()))).with_type(TBag(TInt()))).with_type(TBool()), 'and', EUnaryOp('unique', EVar('ints').with_type(TBag(THandle('_HandleType12', TInt())))).with_type(TBool())).with_type(TBool()), 'and', EUnaryOp('not', EBinOp(EUnaryOp('not', EBinOp(ENum(0).with_type(TInt()), '==', EMapGet(EMakeMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var7926').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var7926').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt())), ELambda(EVar('_var7552').with_type(TBag(THandle('_HandleType12', TInt()))), EUnaryOp('sum', EMap(EVar('_var7552').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var7926').with_type(THandle('_HandleType12', TInt())), ENum(1).with_type(TInt()))).with_type(TBag(TInt()))).with_type(TInt()))).with_type(TMap(TInt(), TInt())), EVar('i').with_type(TInt())).with_type(TInt())).with_type(TBool())).with_type(TBool()), '==', EBinOp(ENum(0).with_type(TInt()), '<', EMapGet(EMakeMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var7926').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var7926').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt())), ELambda(EVar('_var7552').with_type(TBag(THandle('_HandleType12', TInt()))), EUnaryOp('sum', EMap(EVar('_var7552').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var7926').with_type(THandle('_HandleType12', TInt())), ENum(1).with_type(TInt()))).with_type(TBag(TInt()))).with_type(TInt()))).with_type(TMap(TInt(), TInt())), EVar('i').with_type(TInt())).with_type(TInt())).with_type(TBool())).with_type(TBool())).with_type(TBool())).with_type(TBool())
        print(pprint(e))
        assert retypecheck(e)
        satisfy(
            e,
            vars=[EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), EVar('i').with_type(TInt())],
            collection_depth=2,
            validate_model=True)

    def test_flatmap(self):
        satisfy(EUnaryOp('not', EBinOp(EUnaryOp('not', EBinOp(EUnaryOp('unique', EMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var13').with_type(THandle('_HandleType12', TInt())), EGetField(EVar('_var13').with_type(THandle('_HandleType12', TInt())), 'val').with_type(TInt()))).with_type(TBag(TInt()))).with_type(TBool()), 'and', EUnaryOp('unique', EVar('ints').with_type(TBag(THandle('_HandleType12', TInt())))).with_type(TBool())).with_type(TBool())).with_type(TBool()), 'or', EUnaryOp('unique', EFlatMap(EVar('ints').with_type(TBag(THandle('_HandleType12', TInt()))), ELambda(EVar('_var458').with_type(THandle('_HandleType12', TInt())), ESingleton(EVar('_var458').with_type(THandle('_HandleType12', TInt()))).with_type(TBag(THandle('_HandleType12', TInt()))))).with_type(TBag(THandle('_HandleType12', TInt())))).with_type(TBool())).with_type(TBool())).with_type(TBool()), vars=None, collection_depth=2, validate_model=True)

    def test_filter_true(self):
        xs = EVar("xs").with_type(TBag(THandle("X", INT)))
        e1 = EFilter(xs, mk_lambda(xs.type.t, lambda x: equal(EGetField(x, "val"), ENum(0).with_type(INT))))
        assert retypecheck(e1)
        e2 = EFilter(e1, mk_lambda(xs.type.t, lambda x: EBool(True)))
        assert retypecheck(e2)
        assert valid(equal(e1, e2))

    def test_make_record(self):
        t = TRecord((("f", INT), ("g", INT)))
        a = EVar("a").with_type(INT)
        b = EVar("b").with_type(INT)
        x = EMakeRecord((("f", a), ("g", b))).with_type(t)
        y = EMakeRecord((("f", b), ("g", a))).with_type(t)
        z = EMakeRecord((("g", b), ("f", a))).with_type(t)
        assert not valid(equal(x, y), validate_model=True)
        assert valid(equal(x, z), validate_model=True)

    def test_unary_minus(self):
        a = EVar("a").with_type(INT)
        assert satisfiable(ENot(equal(a, EUnaryOp("-", a).with_type(INT))), validate_model=True)

    def test_distinct(self):
        a = EVar("a").with_type(TBag(INT))
        assert satisfiable(ENot(equal(a, EUnaryOp("distinct", a).with_type(TBag(INT)))), validate_model=True)

    def test_unique_distinct(self):
        a = EVar("a").with_type(TBag(INT))
        assert valid(implies(EUnaryOp("unique", a).with_type(BOOL), equal(a, EUnaryOp("distinct", a).with_type(TBag(INT)))), validate_model=True)
