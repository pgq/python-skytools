
/*
 * Get string data from Python object.
 */

static Py_ssize_t get_buffer(PyObject *obj, unsigned char **buf_p, PyObject **tmp_obj_p)
{
	PyObject *str = NULL;
	Py_ssize_t res;

	/* check for None */
	if (obj == Py_None) {
		PyErr_Format(PyExc_TypeError, "None is not allowed");
		return -1;
	}

	/* is string or unicode ? */
	if (PyUnicode_Check(obj)) {
		*buf_p = (unsigned char *)PyUnicode_AsUTF8AndSize(obj, &res);
		return res;
	} else if (PyBytes_Check(obj)) {
		if (PyBytes_AsStringAndSize(obj, (char**)buf_p, &res) < 0)
			return -1;
		return res;
	}

	/*
	 * Not a string-like object, run str() or it.
	 */

	/* are we in recursion? */
	if (tmp_obj_p == NULL) {
		PyErr_Format(PyExc_TypeError, "Cannot convert to string - get_buffer() recusively failed");
		return -1;
	}

	/* do str() then */
	str = PyObject_Str(obj);
	res = -1;
	if (str != NULL) {
		res = get_buffer(str, buf_p, NULL);
		if (res >= 0) {
			*tmp_obj_p = str;
		} else {
			Py_CLEAR(str);
		}
	}
	return res;
}

