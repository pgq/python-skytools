
from skytools.querybuilder import DList, PlanCache


def test_dlist():
    root = DList()
    assert root.empty() == True

    elem1 = DList()
    elem2 = DList()
    elem3 = DList()

    root.append(elem1)
    root.append(elem2)
    root.append(elem3)

    assert root.empty() == False
    assert elem1.empty() == False

    root.remove(elem2)
    root.remove(elem3)
    root.remove(elem1)

    assert root.empty() == True
    assert elem1.next is None
    assert elem2.next is None
    assert elem3.next is None
    assert elem1.prev is None
    assert elem2.prev is None
    assert elem3.prev is None


def test_cached_plan():
    cache = PlanCache(3)

    p1 = cache.get_plan('sql1', ['text'])
    assert p1 is cache.get_plan('sql1', ['text'])

    p2 = cache.get_plan('sql1', ['int'])
    assert p2 is cache.get_plan('sql1', ['int'])
    assert p1 is not p2

    p3 = cache.get_plan('sql3', ['text'])
    assert p3 is cache.get_plan('sql3', ['text'])

    p4 = cache.get_plan('sql4', ['text'])
    assert p4 is cache.get_plan('sql4', ['text'])

    p1x = cache.get_plan('sql1', ['text'])
    assert p1 is not p1x

