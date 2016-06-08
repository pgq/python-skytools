
"""Database tools."""

from __future__ import division, absolute_import, print_function

import os

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import skytools

__all__ = [
    "fq_name_parts", "fq_name", "get_table_oid", "get_table_pkeys",
    "get_table_columns", "exists_schema", "exists_table", "exists_type",
    "exists_sequence", "exists_temp_table", "exists_view",
    "exists_function", "exists_language", "Snapshot", "magic_insert",
    "CopyPipe", "full_copy", "DBObject", "DBSchema", "DBTable", "DBFunction",
    "DBLanguage", "db_install", "installer_find_file", "installer_apply_file",
    "dbdict", "mk_insert_sql", "mk_update_sql", "mk_delete_sql",
]

class dbdict(dict):
    """Wrapper on actual dict that allows accessing dict keys as attributes.

    >>> row = dbdict(a=1, b=2)
    >>> row.a, row.b, row['a'], row['b']
    (1, 2, 1, 2)
    >>> row.c = 3; row['c']
    3
    >>> del row.c; row.c
    Traceback (most recent call last):
        ...
    AttributeError: c
    >>> row['c']
    Traceback (most recent call last):
        ...
    KeyError: 'c'
    >>> row.merge({'q': 4}); row.q
    4

    """
    # obj.foo access
    def __getattr__(self, k):
        "Return attribute."
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)
    def __setattr__(self, k, v):
        "Set attribute."
        self[k] = v
    def __delattr__(self, k):
        "Remove attribute."
        del self[k]
    def merge(self, other):
        for key in other:
            if key not in self:
                self[key] = other[key]

#
# Fully qualified table name
#

def fq_name_parts(tbl):
    """Return fully qualified name parts.

    >>> fq_name_parts('tbl')
    ['public', 'tbl']
    >>> fq_name_parts('foo.tbl')
    ['foo', 'tbl']
    >>> fq_name_parts('foo.tbl.baz')
    ['foo', 'tbl.baz']
    """

    tmp = tbl.split('.', 1)
    if len(tmp) == 1:
        return ['public', tbl]
    return tmp

def fq_name(tbl):
    """Return fully qualified name.

    >>> fq_name('tbl')
    'public.tbl'
    >>> fq_name('foo.tbl')
    'foo.tbl'
    >>> fq_name('foo.tbl.baz')
    'foo.tbl.baz'
    """
    return '.'.join(fq_name_parts(tbl))

#
# info about table
#
def get_table_oid(curs, table_name):
    """Find Postgres OID for table."""
    schema, name = fq_name_parts(table_name)
    q = """select c.oid from pg_namespace n, pg_class c
           where c.relnamespace = n.oid
             and n.nspname = %s and c.relname = %s"""
    curs.execute(q, [schema, name])
    res = curs.fetchall()
    if len(res) == 0:
        raise Exception('Table not found: '+table_name)
    return res[0][0]

def get_table_pkeys(curs, tbl):
    """Return list of pkey column names."""
    oid = get_table_oid(curs, tbl)
    q = "SELECT k.attname FROM pg_index i, pg_attribute k"\
        " WHERE i.indrelid = %s AND k.attrelid = i.indexrelid"\
        "   AND i.indisprimary AND k.attnum > 0 AND NOT k.attisdropped"\
        " ORDER BY k.attnum"
    curs.execute(q, [oid])
    return [row[0] for row in curs.fetchall()]

def get_table_columns(curs, tbl):
    """Return list of column names for table."""
    oid = get_table_oid(curs, tbl)
    q = "SELECT k.attname FROM pg_attribute k"\
        " WHERE k.attrelid = %s"\
        "   AND k.attnum > 0 AND NOT k.attisdropped"\
        " ORDER BY k.attnum"
    curs.execute(q, [oid])
    return [row[0] for row in curs.fetchall()]

#
# exist checks
#
def exists_schema(curs, schema):
    """Does schema exists?"""
    q = "select count(1) from pg_namespace where nspname = %s"
    curs.execute(q, [schema])
    res = curs.fetchone()
    return res[0]

def exists_table(curs, table_name):
    """Does table exists?"""
    schema, name = fq_name_parts(table_name)
    q = """select count(1) from pg_namespace n, pg_class c
           where c.relnamespace = n.oid and c.relkind = 'r'
             and n.nspname = %s and c.relname = %s"""
    curs.execute(q, [schema, name])
    res = curs.fetchone()
    return res[0]

def exists_sequence(curs, seq_name):
    """Does sequence exists?"""
    schema, name = fq_name_parts(seq_name)
    q = """select count(1) from pg_namespace n, pg_class c
           where c.relnamespace = n.oid and c.relkind = 'S'
             and n.nspname = %s and c.relname = %s"""
    curs.execute(q, [schema, name])
    res = curs.fetchone()
    return res[0]

def exists_view(curs, view_name):
    """Does view exists?"""
    schema, name = fq_name_parts(view_name)
    q = """select count(1) from pg_namespace n, pg_class c
           where c.relnamespace = n.oid and c.relkind = 'v'
             and n.nspname = %s and c.relname = %s"""
    curs.execute(q, [schema, name])
    res = curs.fetchone()
    return res[0]

def exists_type(curs, type_name):
    """Does type exists?"""
    schema, name = fq_name_parts(type_name)
    q = """select count(1) from pg_namespace n, pg_type t
           where t.typnamespace = n.oid
             and n.nspname = %s and t.typname = %s"""
    curs.execute(q, [schema, name])
    res = curs.fetchone()
    return res[0]

def exists_function(curs, function_name, nargs):
    """Does function exists?"""
    # this does not check arg types, so may match several functions
    schema, name = fq_name_parts(function_name)
    q = """select count(1) from pg_namespace n, pg_proc p
           where p.pronamespace = n.oid and p.pronargs = %s
             and n.nspname = %s and p.proname = %s"""
    curs.execute(q, [nargs, schema, name])
    res = curs.fetchone()

    # if unqualified function, check builtin functions too
    if not res[0] and function_name.find('.') < 0:
        name = "pg_catalog." + function_name
        return exists_function(curs, name, nargs)

    return res[0]

def exists_language(curs, lang_name):
    """Does PL exists?"""
    q = """select count(1) from pg_language
           where lanname = %s"""
    curs.execute(q, [lang_name])
    res = curs.fetchone()
    return res[0]

def exists_temp_table(curs, tbl):
    """Does temp table exists?"""
    # correct way, works only on 8.2
    q = "select 1 from pg_class where relname = %s and relnamespace = pg_my_temp_schema()"
    curs.execute(q, [tbl])
    tmp = curs.fetchall()
    return len(tmp) > 0

#
# Support for PostgreSQL snapshot
#

class Snapshot(object):
    """Represents a PostgreSQL snapshot.

    Example:
    >>> sn = Snapshot('11:20:11,12,15')
    >>> sn.contains(9)
    True
    >>> sn.contains(11)
    False
    >>> sn.contains(17)
    True
    >>> sn.contains(20)
    False
    >>> Snapshot(':')
    Traceback (most recent call last):
        ...
    ValueError: Unknown format for snapshot

    """

    def __init__(self, str_val):
        "Create snapshot from string."

        self.sn_str = str_val
        tmp = str_val.split(':')
        if len(tmp) != 3:
            raise ValueError('Unknown format for snapshot')
        self.xmin = int(tmp[0])
        self.xmax = int(tmp[1])
        self.txid_list = []
        if tmp[2] != "":
            for s in tmp[2].split(','):
                self.txid_list.append(int(s))

    def contains(self, txid):
        "Is txid visible in snapshot."

        txid = int(txid)

        if txid < self.xmin:
            return True
        if txid >= self.xmax:
            return False
        if txid in self.txid_list:
            return False
        return True

#
# Copy helpers
#

def _gen_dict_copy(tbl, row, fields, qfields):
    tmp = []
    for f in fields:
        v = row.get(f)
        tmp.append(skytools.quote_copy(v))
    return "\t".join(tmp)

def _gen_dict_insert(tbl, row, fields, qfields):
    tmp = []
    for f in fields:
        v = row.get(f)
        tmp.append(skytools.quote_literal(v))
    fmt = "insert into %s (%s) values (%s);"
    return fmt % (tbl, ",".join(qfields), ",".join(tmp))

def _gen_list_copy(tbl, row, fields, qfields):
    tmp = []
    for i in range(len(fields)):
        try:
            v = row[i]
        except IndexError:
            v = None
        tmp.append(skytools.quote_copy(v))
    return "\t".join(tmp)

def _gen_list_insert(tbl, row, fields, qfields):
    tmp = []
    for i in range(len(fields)):
        try:
            v = row[i]
        except IndexError:
            v = None
        tmp.append(skytools.quote_literal(v))
    fmt = "insert into %s (%s) values (%s);"
    return fmt % (tbl, ",".join(qfields), ",".join(tmp))

def magic_insert(curs, tablename, data, fields=None, use_insert=False, quoted_table=False):
    r"""Copy/insert a list of dict/list data to database.

    If curs is None, then the copy or insert statements are returned
    as string.  For list of dict the field list is optional, as its
    possible to guess them from dict keys.

    Example:
    >>> magic_insert(None, 'tbl', [[1, '1'], [2, '2']], ['col1', 'col2'])
    'COPY public.tbl (col1,col2) FROM STDIN;\n1\t1\n2\t2\n\\.\n'
    >>> magic_insert(None, 'tbl', [[1, '1'], [2, '2']], ['col1', 'col2'], use_insert=True)
    "insert into public.tbl (col1,col2) values ('1','1');\ninsert into public.tbl (col1,col2) values ('2','2');\n"
    >>> magic_insert(None, 'tbl', [], ['col1', 'col2'])
    >>> magic_insert(None, 'tbl."1"', [[1, '1'], [2, '2']], ['col1', 'col2'], quoted_table=True)
    'COPY tbl."1" (col1,col2) FROM STDIN;\n1\t1\n2\t2\n\\.\n'
    >>> magic_insert(None, 'tbl."1"', [[1, '1'], [2, '2']])
    Traceback (most recent call last):
        ...
    Exception: Non-dict data needs field list
    >>> magic_insert(None, 'a.tbl', [{'a':1}, {'a':2}])
    'COPY a.tbl (a) FROM STDIN;\n1\n2\n\\.\n'
    >>> magic_insert(None, 'a.tbl', [{'a':1}, {'a':2}], use_insert=True)
    "insert into a.tbl (a) values ('1');\ninsert into a.tbl (a) values ('2');\n"

    More fields than data:

    >>> magic_insert(None, 'tbl', [[1, 'a']], ['col1', 'col2', 'col3'])
    'COPY public.tbl (col1,col2,col3) FROM STDIN;\n1\ta\t\\N\n\\.\n'
    >>> magic_insert(None, 'tbl', [[1, 'a']], ['col1', 'col2', 'col3'], use_insert=True)
    "insert into public.tbl (col1,col2,col3) values ('1','a',null);\n"
    >>> magic_insert(None, 'tbl', [{'a':1}, {'b':2}], ['a', 'b'], use_insert=False)
    'COPY public.tbl (a,b) FROM STDIN;\n1\t\\N\n\\N\t2\n\\.\n'
    >>> magic_insert(None, 'tbl', [{'a':1}, {'b':2}], ['a', 'b'], use_insert=True)
    "insert into public.tbl (a,b) values ('1',null);\ninsert into public.tbl (a,b) values (null,'2');\n"

    """
    if len(data) == 0:
        return None

    # decide how to process
    if hasattr(data[0], 'keys'):
        if fields is None:
            fields = data[0].keys()
        if use_insert:
            row_func = _gen_dict_insert
        else:
            row_func = _gen_dict_copy
    else:
        if fields is None:
            raise Exception("Non-dict data needs field list")
        if use_insert:
            row_func = _gen_list_insert
        else:
            row_func = _gen_list_copy

    qfields = [skytools.quote_ident(f) for f in fields]
    if quoted_table:
        qtablename = tablename
    else:
        qtablename = skytools.quote_fqident(tablename)

    # init processing
    buf = StringIO()
    if curs is None and use_insert == 0:
        fmt = "COPY %s (%s) FROM STDIN;\n"
        buf.write(fmt % (qtablename, ",".join(qfields)))

    # process data
    for row in data:
        buf.write(row_func(qtablename, row, fields, qfields))
        buf.write("\n")

    # if user needs only string, return it
    if curs is None:
        if use_insert == 0:
            buf.write("\\.\n")
        return buf.getvalue()

    # do the actual copy/inserts
    if use_insert:
        curs.execute(buf.getvalue())
    else:
        buf.seek(0)
        hdr = "%s (%s)" % (qtablename, ",".join(qfields))
        curs.copy_from(buf, hdr)

#
# Full COPY of table from one db to another
#

class CopyPipe(object):
    "Splits one big COPY to chunks."

    def __init__(self, dstcurs, tablename=None, limit=512*1024, sql_from=None):
        self.tablename = tablename
        self.sql_from = sql_from
        self.dstcurs = dstcurs
        self.buf = StringIO()
        self.limit = limit
        #hook for new data, hook func should return new data
        #def write_hook(obj, data):
        #   return data
        self.write_hook = None
        #hook for flush, hook func result is discarded
        # def flush_hook(obj):
        #   return None
        self.flush_hook = None
        self.total_rows = 0
        self.total_bytes = 0

    def write(self, data):
        "New data from psycopg"
        if self.write_hook:
            data = self.write_hook(self, data)

        self.total_bytes += len(data)
        self.total_rows += data.count("\n")

        if self.buf.tell() >= self.limit:
            pos = data.find('\n')
            if pos >= 0:
                # split at newline
                p1 = data[:pos + 1]
                p2 = data[pos + 1:]
                self.buf.write(p1)
                self.flush()

                data = p2

        self.buf.write(data)

    def flush(self):
        "Send data out."

        if self.flush_hook:
            self.flush_hook(self)

        if self.buf.tell() <= 0:
            return

        self.buf.seek(0)
        if self.sql_from:
            self.dstcurs.copy_expert(self.sql_from, self.buf)
        else:
            self.dstcurs.copy_from(self.buf, self.tablename)
        self.buf.seek(0)
        self.buf.truncate()


def full_copy(tablename, src_curs, dst_curs, column_list=(), condition=None,
        dst_tablename=None, dst_column_list=None,
        write_hook=None, flush_hook=None):
    """COPY table from one db to another."""

    # default dst table and dst columns to source ones
    dst_tablename = dst_tablename or tablename
    dst_column_list = dst_column_list or column_list[:]
    if len(dst_column_list) != len(column_list):
        raise Exception('src and dst column lists must match in length')

    def build_qfields(cols):
        if cols:
            return ",".join([skytools.quote_ident(f) for f in cols])
        else:
            return "*"

    def build_statement(table, cols):
        qtable = skytools.quote_fqident(table)
        if cols:
            qfields = build_qfields(cols)
            return "%s (%s)" % (qtable, qfields)
        else:
            return qtable

    dst = build_statement(dst_tablename, dst_column_list)
    if condition:
        src = "(SELECT %s FROM %s WHERE %s)" % (build_qfields(column_list),
                                                skytools.quote_fqident(tablename),
                                                condition)
    else:
        src = build_statement(tablename, column_list)

    if hasattr(src_curs, 'copy_expert'):
        sql_to = "COPY %s TO stdout" % src
        sql_from = "COPY %s FROM stdin" % dst
        buf = CopyPipe(dst_curs, sql_from=sql_from)
        buf.write_hook = write_hook
        buf.flush_hook = flush_hook
        src_curs.copy_expert(sql_to, buf)
    else:
        if condition:
            # regular psycopg copy_to generates invalid sql for subselect copy
            raise Exception('copy_expert() is needed for conditional copy')
        buf = CopyPipe(dst_curs, dst)
        buf.write_hook = write_hook
        buf.flush_hook = flush_hook
        src_curs.copy_to(buf, src)
    buf.flush()

    return (buf.total_bytes, buf.total_rows)


#
# SQL installer
#

class DBObject(object):
    """Base class for installable DB objects."""
    name = None
    sql = None
    sql_file = None
    def __init__(self, name, sql=None, sql_file=None):
        """Generic dbobject init."""
        self.name = name
        self.sql = sql
        self.sql_file = sql_file

    def create(self, curs, log=None):
        """Create a dbobject."""
        if log:
            log.info('Installing %s' % self.name)
        if self.sql:
            sql = self.sql
        elif self.sql_file:
            fn = self.find_file()
            if log:
                log.info("  Reading from %s" % fn)
            sql = open(fn, "r").read()
        else:
            raise Exception('object not defined')
        for stmt in skytools.parse_statements(sql):
            #if log: log.debug(repr(stmt))
            curs.execute(stmt)

    def find_file(self):
        """Find install script file."""
        return installer_find_file(self.sql_file)

class DBSchema(DBObject):
    """Handles db schema."""
    def exists(self, curs):
        """Does schema exists."""
        return exists_schema(curs, self.name)

class DBTable(DBObject):
    """Handles db table."""
    def exists(self, curs):
        """Does table exists."""
        return exists_table(curs, self.name)

class DBFunction(DBObject):
    """Handles db function."""
    def __init__(self, name, nargs, sql=None, sql_file=None):
        """Function object - number of args is significant."""
        super(DBFunction, self).__init__(name, sql, sql_file)
        self.nargs = nargs
    def exists(self, curs):
        """Does function exists."""
        return exists_function(curs, self.name, self.nargs)

class DBLanguage(DBObject):
    """Handles db language."""
    def __init__(self, name):
        """PL object - creation happens with CREATE LANGUAGE."""
        super(DBLanguage, self).__init__(name, sql="create language %s" % name)
    def exists(self, curs):
        """Does PL exists."""
        return exists_language(curs, self.name)

def db_install(curs, obj_list, log=None):
    """Installs list of objects into db."""
    for obj in obj_list:
        if not obj.exists(curs):
            obj.create(curs, log)
        else:
            if log:
                log.info('%s is installed' % obj.name)

def installer_find_file(filename):
    """Find SQL script from pre-defined paths."""
    full_fn = None
    if filename[0] == "/":
        if os.path.isfile(filename):
            full_fn = filename
    else:
        from skytools.installer_config import sql_locations
        dir_list = sql_locations
        for fdir in dir_list:
            fn = os.path.join(fdir, filename)
            if os.path.isfile(fn):
                full_fn = fn
                break

    if not full_fn:
        raise Exception('File not found: '+filename)
    return full_fn

def installer_apply_file(db, filename, log):
    """Find SQL file and apply it to db, statement-by-statement."""
    fn = installer_find_file(filename)
    sql = open(fn, "r").read()
    if log:
        log.info("applying %s" % fn)
    curs = db.cursor()
    for stmt in skytools.parse_statements(sql):
        #log.debug(repr(stmt))
        curs.execute(stmt)

#
# Generate INSERT/UPDATE/DELETE statement
#

def mk_insert_sql(row, tbl, pkey_list=None, field_map=None):
    """Generate INSERT statement from dict data.

    >>> from collections import OrderedDict
    >>> row = OrderedDict([('id',1), ('data', None)])
    >>> mk_insert_sql(row, 'tbl')
    "insert into public.tbl (id, data) values ('1', null);"
    >>> mk_insert_sql(row, 'tbl', ['x'], OrderedDict([('id', 'id_'), ('data', 'data_')]))
    "insert into public.tbl (id_, data_) values ('1', null);"

    """

    col_list = []
    val_list = []
    if field_map:
        for src, dst in field_map.items():
            col_list.append(skytools.quote_ident(dst))
            val_list.append(skytools.quote_literal(row[src]))
    else:
        for c, v in row.items():
            col_list.append(skytools.quote_ident(c))
            val_list.append(skytools.quote_literal(v))
    col_str = ", ".join(col_list)
    val_str = ", ".join(val_list)
    return "insert into %s (%s) values (%s);" % (
                    skytools.quote_fqident(tbl), col_str, val_str)

def mk_update_sql(row, tbl, pkey_list, field_map=None):
    r"""Generate UPDATE statement from dict data.

    >>> mk_update_sql({'id': 0, 'id2': '2', 'data': 'str\\'}, 'Table', ['id', 'id2'])
    'update only public."Table" set data = E\'str\\\\\' where id = \'0\' and id2 = \'2\';'
    >>> mk_update_sql({'id': 0, 'id2': '2', 'data': 'str\\'}, 'Table', ['id', 'id2'],
    ...     {'id': '_id', 'id2': '_id2', 'data': '_data'})
    'update only public."Table" set _data = E\'str\\\\\' where _id = \'0\' and _id2 = \'2\';'
    >>> mk_update_sql({'id': 0, 'id2': '2', 'data': 'str\\'}, 'Table', [])
    Traceback (most recent call last):
        ...
    Exception: update needs pkeys

    """

    if len(pkey_list) < 1:
        raise Exception("update needs pkeys")
    set_list = []
    whe_list = []
    pkmap = {}
    for k in pkey_list:
        pkmap[k] = 1
        new_k = field_map and field_map[k] or k
        col = skytools.quote_ident(new_k)
        val = skytools.quote_literal(row[k])
        whe_list.append("%s = %s" % (col, val))

    if field_map:
        for src, dst in field_map.items():
            if src not in pkmap:
                col = skytools.quote_ident(dst)
                val = skytools.quote_literal(row[src])
                set_list.append("%s = %s" % (col, val))
    else:
        for col, val in row.items():
            if col not in pkmap:
                col = skytools.quote_ident(col)
                val = skytools.quote_literal(val)
                set_list.append("%s = %s" % (col, val))
    return "update only %s set %s where %s;" % (skytools.quote_fqident(tbl),
            ", ".join(set_list), " and ".join(whe_list))

def mk_delete_sql(row, tbl, pkey_list, field_map=None):
    """Generate DELETE statement from dict data.

    >>> mk_delete_sql({'a': 1, 'b':2, 'c':3}, 'tablename', ['a','b'])
    "delete from only public.tablename where a = '1' and b = '2';"
    >>> mk_delete_sql({'a': 1, 'b':2, 'c':3}, 'tablename', ['a','b'], {'a': 'aa', 'b':'bb'})
    "delete from only public.tablename where aa = '1' and bb = '2';"
    >>> mk_delete_sql({'a': 1, 'b':2, 'c':3}, 'tablename', [])
    Traceback (most recent call last):
        ...
    Exception: delete needs pkeys

    """

    if len(pkey_list) < 1:
        raise Exception("delete needs pkeys")
    whe_list = []
    for k in pkey_list:
        new_k = field_map and field_map[k] or k
        col = skytools.quote_ident(new_k)
        val = skytools.quote_literal(row[k])
        whe_list.append("%s = %s" % (col, val))
    whe_str = " and ".join(whe_list)
    return "delete from only %s where %s;" % (skytools.quote_fqident(tbl), whe_str)

