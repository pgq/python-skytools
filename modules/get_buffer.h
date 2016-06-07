
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
#if PY_MAJOR_VERSION < 3
	if (PyString_Check(obj) || PyUnicode_Check(obj)) {
		if (PyString_AsStringAndSize(obj, (char**)buf_p, &res) < 0)
			return -1;
		return res;
	}
#else /* python 3 */
	if (PyUnicode_Check(obj)) {
	  #if PY_VERSION_HEX >= 0x03030000
		*buf_p = (unsigned char *)PyUnicode_AsUTF8AndSize(obj, &res);
		return res;
	  #else
		/* convert to utf8 bytes */
		*tmp_obj_p = PyUnicode_AsUTF8String(obj);
		if (*tmp_obj_p == NULL)
			return -1;
		/* obj is now bytes */
		obj = *tmp_obj_p;
		if (PyBytes_AsStringAndSize(obj, (char**)buf_p, &res) < 0)
			return -1;
		return res;
	  #endif
	} else if (PyBytes_Check(obj)) {
		if (PyBytes_AsStringAndSize(obj, (char**)buf_p, &res) < 0)
			return -1;
		return res;
	}
#endif

#if PY_MAJOR_VERSION < 3
	{
		/* try to get buffer */
		PyBufferProcs *bfp = obj->ob_type->tp_as_buffer;
		if (bfp && bfp->bf_getsegcount && bfp->bf_getreadbuffer) {
			if (bfp->bf_getsegcount(obj, NULL) == 1)
				return bfp->bf_getreadbuffer(obj, 0, (void**)buf_p);
		}
	}
#endif
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
#if PY_VERSION_HEX >= 0x03000000 && PY_VERSION_HEX < 0x03030000
	if (str != NULL) {
		/*
		 * Immediately convert to utf8 obj,
		 * otherwise we dont have enough temp vars.
		 */
		obj = PyUnicode_AsUTF8String(str);
		Py_CLEAR(str);
		str = obj;
		obj = NULL;
	}
#endif
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

