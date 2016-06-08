
from nose.tools import *
from skytools.querybuilder import DList, CachedPlan, PlanCache

def test_dlist():
    root = DList()
    assert_true(root.empty())

    elem1 = DList()
    elem2 = DList()
    elem3 = DList()

    root.append(elem1)
    root.append(elem2)
    root.append(elem3)

    assert_false(root.empty())
    assert_false(elem1.empty())

    root.remove(elem2)
    root.remove(elem3)
    root.remove(elem1)

    assert_true(root.empty())
    assert_is_none(elem1.next)
    assert_is_none(elem2.next)
    assert_is_none(elem3.next)
    assert_is_none(elem1.prev)
    assert_is_none(elem2.prev)
    assert_is_none(elem3.prev)


def test_cached_plan():
    cache = PlanCache(3)

    p1 = cache.get_plan('sql1', ['text'])
    assert_is(p1, cache.get_plan('sql1', ['text']))

    p2 = cache.get_plan('sql1', ['int'])
    assert_is(p2, cache.get_plan('sql1', ['int']))
    assert_is_not(p1, p2)

    p3 = cache.get_plan('sql3', ['text'])
    assert_is(p3, cache.get_plan('sql3', ['text']))

    p4 = cache.get_plan('sql4', ['text'])
    assert_is(p4, cache.get_plan('sql4', ['text']))

    p1x = cache.get_plan('sql1', ['text'])
    assert_is_not(p1, p1x)

