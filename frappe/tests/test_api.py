import sys
import unittest
from contextlib import contextmanager
from random import choice
from typing import Dict, Optional

import requests
from semantic_version import Version

import frappe
from frappe.utils import get_site_url, get_test_client


@contextmanager
def suppress_stdout():
	"""Supress stdout for tests which expectedly make noise
	but that you don't need in tests"""
	sys.stdout = None
	try:
		yield
	finally:
		sys.stdout = sys.__stdout__


class FrappeAPITestCase(unittest.TestCase):
	SITE = frappe.local.site
	SITE_URL = get_site_url(SITE)
	RESOURCE_URL = f"{SITE_URL}/api/resource"
	TEST_CLIENT = get_test_client()

	@property
	def sid(self):
		if not getattr(self, "_sid", None):
			r = self.TEST_CLIENT.post("/api/method/login", data={
				"usr": "Administrator",
				"pwd": frappe.conf.admin_password or "admin",
			})
			self._sid = r.headers[2][1].split(";")[0].lstrip("sid=")
		return self._sid

	def get(self, path: str, params: Optional[Dict] = None):
		return self.TEST_CLIENT.get(path, data=params)

	def post(self, path, data):
		return self.TEST_CLIENT.post(path, data=frappe.as_json(data))

	def put(self, path, data):
		return self.TEST_CLIENT.put(path, data=frappe.as_json(data))

	def delete(self, path):
		return self.TEST_CLIENT.delete(path)


class TestResourceAPI(FrappeAPITestCase):
	DOCTYPE = "ToDo"
	GENERATED_DOCUMENTS = []

	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		for _ in range(10):
			doc = frappe.get_doc(
				{"doctype": "ToDo", "description": frappe.mock("paragraph")}
			).insert()
			cls.GENERATED_DOCUMENTS.append(doc.name)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in cls.GENERATED_DOCUMENTS:
			frappe.delete_doc_if_exists(cls.DOCTYPE, name)

	def setUp(self):
		frappe.set_user("Administrator")
		# commit to ensure consistency in session (postgres CI randomly fails)
		if frappe.conf.db_type == "postgres":
			frappe.db.commit()

	def test_unauthorized_call(self):
		# test 1: fetch documents without auth
		response = requests.get(f"{self.RESOURCE_URL}/{self.DOCTYPE}")
		self.assertEqual(response.status_code, 403)

	def test_get_list(self):
		# test 2: fetch documents without params
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid})
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(response.json, dict)
		self.assertIn("data", response.json)

	def test_get_list_limit(self):
		# test 3: fetch data with limit
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "limit": 2})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.json["data"]), 2)

	def test_get_list_dict(self):
		# test 4: fetch response as (not) dict
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "as_dict": True})
		json = frappe._dict(response.json)
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(json.data, list)
		self.assertIsInstance(json.data[0], dict)

		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "as_dict": False})
		json = frappe._dict(response.json)
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(json.data, list)
		self.assertIsInstance(json.data[0], list)

	def test_get_list_debug(self):
		# test 5: fetch response with debug
		with suppress_stdout():
			response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "debug": True})
		self.assertEqual(response.status_code, 200)
		self.assertIn("exc", response.json)
		self.assertIsInstance(response.json["exc"], str)
		self.assertIsInstance(eval(response.json["exc"]), list)

	def test_get_list_fields(self):
		# test 6: fetch response with fields
		response = self.get(f"/api/resource/{self.DOCTYPE}", {"sid": self.sid, "fields": '["description"]'})
		self.assertEqual(response.status_code, 200)
		json = frappe._dict(response.json)
		self.assertIn("description", json.data[0])

	def test_create_document(self):
		# test 7: POST method on /api/resource to create doc
		data = {"description": frappe.mock("paragraph"), "sid": self.sid}
		response = self.post(f"/api/resource/{self.DOCTYPE}", data)
		self.assertEqual(response.status_code, 200)
		docname = response.json["data"]["name"]
		self.assertIsInstance(docname, str)
		self.GENERATED_DOCUMENTS.append(docname)

	def test_update_document(self):
		# test 8: PUT method on /api/resource to update doc
		generated_desc = frappe.mock("paragraph")
		data = {"description": generated_desc, "sid": self.sid}
		random_doc = choice(self.GENERATED_DOCUMENTS)
		desc_before_update = frappe.db.get_value(self.DOCTYPE, random_doc, "description")

		response = self.put(f"/api/resource/{self.DOCTYPE}/{random_doc}", data=data)
		self.assertEqual(response.status_code, 200)
		self.assertNotEqual(response.json["data"]["description"], desc_before_update)
		self.assertEqual(response.json["data"]["description"], generated_desc)

	def test_delete_document(self):
		# test 9: DELETE method on /api/resource
		doc_to_delete = choice(self.GENERATED_DOCUMENTS)
		response = self.delete(f"/api/resource/{self.DOCTYPE}/{doc_to_delete}")
		self.assertEqual(response.status_code, 202)
		self.assertDictEqual(response.json, {"message": "ok"})
		self.GENERATED_DOCUMENTS.remove(doc_to_delete)

		non_existent_doc = frappe.generate_hash(length=12)
		with suppress_stdout():
			response = self.delete(f"/api/resource/{self.DOCTYPE}/{non_existent_doc}")
		self.assertEqual(response.status_code, 404)
		self.assertDictEqual(response.json, {})


class TestMethodAPI(FrappeAPITestCase):
	METHOD_PATH = "/api/method"

	def test_version(self):
		# test 1: test for /api/method/version
		response = self.get(f"{self.METHOD_PATH}/version")
		json = frappe._dict(response.json)

		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(json, dict)
		self.assertIsInstance(json.message, str)
		self.assertEqual(Version(json.message), Version(frappe.__version__))

	def test_ping(self):
		# test 2: test for /api/method/ping
		response = self.get(f"{self.METHOD_PATH}/ping")
		self.assertEqual(response.status_code, 200)
		self.assertIsInstance(response.json, dict)
		self.assertEqual(response.json['message'], "pong")
